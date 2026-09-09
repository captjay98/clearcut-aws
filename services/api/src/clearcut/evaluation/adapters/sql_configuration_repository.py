"""Session-bound SQL adapter for the protected-configuration port.

Every method accepts an existing :class:`~sqlalchemy.ext.asyncio.AsyncSession`
and issues statements on it directly. None of them opens a transaction, commits,
or rolls back: they run inside the caller's unit of work so the lifecycle write
and the authoritative audit event that attests to it commit atomically.

Scope is the authenticated ``org_id`` alone: a protected configuration is
organization-owned, so there is no project path scope to apply and nothing here
is global. A binding that is absent or foreign surfaces as a typed
:class:`~clearcut.commanding.errors.CommandNotFoundError` with the same neutral
shape either way.

Two storage invariants shape the write statements
-------------------------------------------------
The organization holds at most one active binding, enforced by the partial unique
index ``uq_protected_configurations_one_active`` on ``(org_id) WHERE lifecycle =
'active'``. That constraint cannot be raced, so an activation must supersede the
incumbent active row *before* it promotes its target, in the same transaction.
:meth:`SqlProtectedConfigurationRepository.commit_activation` does exactly that,
in that order.

An active row is accountable: ``ck_protected_configurations_active_accountable``
requires both ``activated_by`` and ``activated_at``. Every statement here that
produces an active row sets both, from the accountable human trigger and the
command's single instant.

Lifecycle transitions are compare-and-swaps guarded on the expected source
stage, so a concurrent transition loses and is classified as a typed
stale-version conflict rather than silently overwriting a stage it never read.

Why this adapter owns the audit insert and the receipt
------------------------------------------------------
The governed-command kernel's SQL seams are project-shaped and neither can
express an organization-level command as they stand:

* ``governed_command_receipts`` declares ``project_id`` and ``item_id`` as NOT
  NULL with foreign keys onto ``projects`` and ``clearance_items``. A governed
  configuration command has neither, so no row can be written there without a
  schema change.
* :func:`clearcut.commanding.sql.insert_authoritative_audit` stringifies
  ``envelope.project_id`` unconditionally, so it cannot produce the null
  ``project_id`` an organization-owned audit row requires.

``authoritative_audit_events.project_id`` *is* nullable, and its composite
foreign key onto ``projects`` is not enforced when that component is null, which
is exactly what an organization-level event needs. So this adapter writes that one
row itself, using the identical column set and the same typed
:class:`~clearcut.commanding.domain.AuditPayload` redaction seam the kernel helper
uses, with ``project_id`` null. That audit row is also this operation's
accountable idempotency receipt: it carries the command identity (operation,
idempotency key, intent hash, expected/resulting version, result id) under a
reserved ``command`` key, and :meth:`find_prior_receipt` replays from it. This is
the same arrangement :mod:`clearcut.organizations.adapters.sql_settings_repository`
already uses for organization-owned settings.

That makes the receipt's uniqueness advisory rather than database-enforced. The
durable guards against a same-key double write are the lifecycle compare-and-swap
(a second validation or activation of the same binding loses the swap and
receives a typed stale-version conflict) and, for activation specifically, the
one-active-binding unique index. Drafting has no such guard, because a draft
creates a new inert row: two racing same-key drafts can each leave a draft row
behind. Neither governs anything, neither can activate without its own separate
human trigger, and both are visible in the list, so the outcome is redundant
rather than incorrect. An organization-scoped receipt table with the unique scope
constraint the project-scoped kernel table has would close it and is the right
follow-up; it needs a migration, which is owned elsewhere.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import sqlalchemy as sa
import uuid6
from clearcut.commanding.domain import AuditPayload, CommandEnvelope, PriorReceipt
from clearcut.commanding.errors import (
    CommandNotFoundError,
    CommandValidationError,
    StaleVersionConflictError,
)
from clearcut.evaluation.domain.configuration import (
    ActiveBindingState,
    ConfigurationBinding,
    ConfigurationLifecycle,
    NoActiveBinding,
    ProtectedConfiguration,
    parse_lifecycle,
    parse_validation_issues,
)
from clearcut.evaluation.ports.configuration_repository import (
    ConfigurationAuditEvent,
    OrganizationGovernanceScope,
)
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

# The reserved audit-payload key carrying command identity. The governance detail
# stays at the top level, so a reader of the payload sees what changed first and
# the replay machinery second.
_COMMAND_KEY = "command"

_CONFIGURATION_COLUMNS = (
    "id, org_id, lifecycle, policy_version, prompt_version, rationale, label, "
    "validation_issues, activated_by, activated_at, validated_by, validated_at, "
    "superseded_at, superseded_by, created_by, created_at"
)

_ORGANIZATION_EXISTS = sa.text("SELECT 1 FROM organizations WHERE id = :org_id")

_LIST_CONFIGURATIONS = sa.text(
    f"SELECT {_CONFIGURATION_COLUMNS} FROM protected_configurations "
    "WHERE org_id = :org_id ORDER BY created_at DESC, id DESC"
)

_LOAD_SCOPED = sa.text(
    f"SELECT {_CONFIGURATION_COLUMNS} FROM protected_configurations "
    "WHERE id = :config_id AND org_id = :org_id"
)

_LOAD_ACTIVE = sa.text(
    "SELECT policy_version, prompt_version FROM protected_configurations "
    "WHERE org_id = :org_id AND lifecycle = 'active'"
)

_CONFIGURATION_EXISTS = sa.text(
    "SELECT 1 FROM protected_configurations WHERE id = :config_id AND org_id = :org_id"
)

_INSERT_CONFIGURATION = sa.text(
    """
    INSERT INTO protected_configurations (
        id, org_id, lifecycle, policy_version, prompt_version, rationale, label,
        validation_issues, activated_by, activated_at, validated_by, validated_at,
        superseded_at, superseded_by, created_by, created_at
    ) VALUES (
        :id, :org_id, :lifecycle, :policy_version, :prompt_version, :rationale, :label,
        :validation_issues, :activated_by, :activated_at, :validated_by, :validated_at,
        NULL, NULL, :created_by, :created_at
    )
    """
).bindparams(sa.bindparam("validation_issues", type_=sa.JSON()))

# A clean validation advances the stage and records the accountable validator.
_MARK_VALIDATED = sa.text(
    """
    UPDATE protected_configurations
    SET lifecycle = 'validated',
        validated_by = :actor_id,
        validated_at = :occurred_at,
        validation_issues = :validation_issues
    WHERE id = :config_id
      AND org_id = :org_id
      AND lifecycle IN ('draft', 'validated')
    """
).bindparams(sa.bindparam("validation_issues", type_=sa.JSON()))

# A validation that found issues records them and holds the binding at draft, so
# an unfit binding cannot reach activation on the strength of a stale stage.
_MARK_VALIDATION_ISSUES = sa.text(
    """
    UPDATE protected_configurations
    SET lifecycle = 'draft',
        validated_by = NULL,
        validated_at = NULL,
        validation_issues = :validation_issues
    WHERE id = :config_id
      AND org_id = :org_id
      AND lifecycle IN ('draft', 'validated')
    """
).bindparams(sa.bindparam("validation_issues", type_=sa.JSON()))

# Supersede the incumbent before promoting the target: the partial unique index
# tolerates no statement boundary at which two rows are active.
_SUPERSEDE_ACTIVE = sa.text(
    """
    UPDATE protected_configurations
    SET lifecycle = 'superseded',
        superseded_at = :occurred_at,
        superseded_by = :config_id
    WHERE org_id = :org_id
      AND lifecycle = 'active'
      AND id <> :config_id
    """
)

_ACTIVATE_CONFIGURATION = sa.text(
    """
    UPDATE protected_configurations
    SET lifecycle = 'active',
        activated_by = :actor_id,
        activated_at = :occurred_at,
        superseded_at = NULL,
        superseded_by = NULL
    WHERE id = :config_id
      AND org_id = :org_id
      AND lifecycle = 'validated'
    """
)

# Organization-scoped governed event: no project component, which the nullable
# column and its unenforced-on-null composite foreign key both permit.
_AUDIT_INSERT = sa.text(
    """
    INSERT INTO authoritative_audit_events (
        id, org_id, project_id, actor_id, action, target_type,
        target_id, payload_redacted, occurred_at, correlation_id
    ) VALUES (
        :id, :org_id, NULL, :actor_id, :action, :target_type,
        :target_id, :payload, :occurred_at, :correlation_id
    )
    """
).bindparams(sa.bindparam("payload", type_=sa.JSON()))


def _payload_field_sql(dialect_name: str, field: str) -> str:
    """Return a trusted SQL fragment reading one command-identity field.

    The payload column is JSON on SQLite and JSONB on PostgreSQL, so the
    extraction differs by dialect. An unsupported dialect fails loudly rather
    than silently matching nothing, which would turn every replay into a second
    governed write.
    """
    if dialect_name == "postgresql":
        return f"payload_redacted -> '{_COMMAND_KEY}' ->> '{field}'"
    if dialect_name == "sqlite":
        return f"json_extract(payload_redacted, '$.{_COMMAND_KEY}.{field}')"
    raise RuntimeError(
        f"Unsupported database dialect for protected configuration receipts: {dialect_name}"
    )


class SqlProtectedConfigurationRepository:
    """SQL implementation of :class:`ProtectedConfigurationRepositoryPort`."""

    async def require_organization_scope(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
    ) -> OrganizationGovernanceScope:
        row = (await session.execute(_ORGANIZATION_EXISTS, {"org_id": str(org_id)})).first()
        if row is None:
            raise CommandNotFoundError()
        return OrganizationGovernanceScope(org_id=org_id)

    async def list_for_organization(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
    ) -> tuple[ProtectedConfiguration, ...]:
        rows = (
            (await session.execute(_LIST_CONFIGURATIONS, {"org_id": str(org_id)}))
            .mappings()
            .all()
        )
        return tuple(_project(row) for row in rows)

    async def load_scoped(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        config_id: UUID,
    ) -> ProtectedConfiguration:
        row = (
            (
                await session.execute(
                    _LOAD_SCOPED,
                    {"config_id": str(config_id), "org_id": str(org_id)},
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            # Absent and foreign are indistinguishable to the caller by design.
            raise CommandNotFoundError()
        return _project(row)

    async def load_active_binding(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
    ) -> ActiveBindingState:
        rows = (await session.execute(_LOAD_ACTIVE, {"org_id": str(org_id)})).mappings().all()
        if not rows:
            return NoActiveBinding()
        if len(rows) > 1:
            # The partial unique index makes this unreachable in a migrated
            # database. If it is ever reached the organization has no single
            # governing policy, which is a fail-closed condition rather than a
            # value to guess at.
            raise CommandValidationError(
                "The organization has more than one active policy and prompt binding."
            )
        return ConfigurationBinding(
            policy_version=str(rows[0]["policy_version"]),
            prompt_version=str(rows[0]["prompt_version"]),
        )

    async def insert_draft(
        self,
        session: AsyncSession,
        *,
        configuration: ProtectedConfiguration,
    ) -> None:
        if configuration.lifecycle is not ConfigurationLifecycle.DRAFT:
            raise CommandValidationError("A new binding must be inserted as a draft.")
        _require_aware(configuration.created_at)
        try:
            async with session.begin_nested():
                await session.execute(
                    _INSERT_CONFIGURATION,
                    {
                        "id": str(configuration.config_id),
                        "org_id": str(configuration.org_id),
                        "lifecycle": configuration.lifecycle.value,
                        "policy_version": configuration.policy_version,
                        "prompt_version": configuration.prompt_version,
                        "rationale": configuration.rationale,
                        "label": configuration.label,
                        "validation_issues": list(configuration.validation_issues),
                        # A draft governs nothing, so it names no activator and no
                        # validator. Those accountability columns stay empty until
                        # a human transition fills them.
                        "activated_by": None,
                        "activated_at": None,
                        "validated_by": None,
                        "validated_at": None,
                        "created_by": _optional_str(configuration.created_by),
                        "created_at": configuration.created_at,
                    },
                )
        except IntegrityError as error:
            # A concurrent writer committed this exact draft identity first. The
            # savepoint rollback discarded the losing insert; surfacing the typed
            # stale-version conflict routes the caller through the governed
            # template's re-read contract, which replays the durable winner.
            raise StaleVersionConflictError() from error

    async def seed_default_binding(
        self,
        session: AsyncSession,
        *,
        configuration: ProtectedConfiguration,
    ) -> None:
        _require_aware(configuration.created_at)
        if configuration.lifecycle is not ConfigurationLifecycle.ACTIVE:
            raise CommandValidationError("The seeded default binding must be active.")
        if configuration.activated_by is None or configuration.activated_at is None:
            # The database check constraint requires both on an active row. Failing
            # here keeps the reason legible instead of surfacing as a constraint
            # violation from inside organization creation.
            raise CommandValidationError(
                "The seeded default binding must record who activated it and when."
            )
        # No savepoint and no conflict handling: this runs inside organization
        # creation, so a failure here must abort the whole creation. An
        # organization that exists without a governing binding could never
        # complete a detection pass, which is precisely the state this seed exists
        # to prevent.
        await session.execute(
            _INSERT_CONFIGURATION,
            {
                "id": str(configuration.config_id),
                "org_id": str(configuration.org_id),
                "lifecycle": configuration.lifecycle.value,
                "policy_version": configuration.policy_version,
                "prompt_version": configuration.prompt_version,
                "rationale": configuration.rationale,
                "label": configuration.label,
                "validation_issues": list(configuration.validation_issues),
                "activated_by": str(configuration.activated_by),
                "activated_at": configuration.activated_at,
                "validated_by": _optional_str(configuration.validated_by),
                "validated_at": configuration.validated_at,
                "created_by": _optional_str(configuration.created_by),
                "created_at": configuration.created_at,
            },
        )

    async def commit_validation(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        config_id: UUID,
        actor_id: UUID,
        issues: tuple[str, ...],
        occurred_at: datetime,
    ) -> None:
        _require_aware(occurred_at)
        statement = _MARK_VALIDATED if not issues else _MARK_VALIDATION_ISSUES
        result = await session.execute(
            statement,
            {
                "config_id": str(config_id),
                "org_id": str(org_id),
                "actor_id": str(actor_id),
                "occurred_at": occurred_at,
                "validation_issues": list(issues),
            },
        )
        if cast(CursorResult[Any], result).rowcount != 1:
            await self._classify_transition_miss(session, org_id=org_id, config_id=config_id)

    async def commit_activation(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        config_id: UUID,
        actor_id: UUID,
        occurred_at: datetime,
    ) -> None:
        _require_aware(occurred_at)
        # Supersede the incumbent first. The partial unique index tolerates no
        # moment with two active rows, so this ordering is a correctness
        # requirement, not an optimisation.
        await session.execute(
            _SUPERSEDE_ACTIVE,
            {
                "org_id": str(org_id),
                "config_id": str(config_id),
                "occurred_at": occurred_at,
            },
        )
        result = await session.execute(
            _ACTIVATE_CONFIGURATION,
            {
                "config_id": str(config_id),
                "org_id": str(org_id),
                "actor_id": str(actor_id),
                "occurred_at": occurred_at,
            },
        )
        if cast(CursorResult[Any], result).rowcount != 1:
            await self._classify_transition_miss(session, org_id=org_id, config_id=config_id)

    async def find_prior_receipt(
        self,
        session: AsyncSession,
        envelope: CommandEnvelope,
        *,
        action: str,
    ) -> PriorReceipt | None:
        dialect_name = session.get_bind().dialect.name
        operation_sql = _payload_field_sql(dialect_name, "operation")
        key_sql = _payload_field_sql(dialect_name, "idempotencyKey")
        intent_sql = _payload_field_sql(dialect_name, "intentHash")
        expected_sql = _payload_field_sql(dialect_name, "expectedVersion")
        resulting_sql = _payload_field_sql(dialect_name, "resultingVersion")
        result_id_sql = _payload_field_sql(dialect_name, "resultId")
        row = (
            (
                await session.execute(
                    sa.text(
                        "SELECT target_id, occurred_at, "
                        f"{intent_sql} AS intent_hash, "
                        f"{expected_sql} AS expected_version, "
                        f"{resulting_sql} AS resulting_version, "
                        f"{result_id_sql} AS result_id "
                        "FROM authoritative_audit_events "
                        "WHERE org_id = :org_id "
                        "AND actor_id = :actor_id "
                        "AND action = :action "
                        f"AND {operation_sql} = :operation "
                        f"AND {key_sql} = :idempotency_key "
                        "ORDER BY occurred_at DESC "
                        "LIMIT 1"
                    ),
                    {
                        "org_id": str(envelope.org_id),
                        "actor_id": str(envelope.actor_id),
                        "action": action,
                        "operation": envelope.operation,
                        "idempotency_key": envelope.idempotency_key,
                    },
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        intent_hash = row["intent_hash"]
        if not isinstance(intent_hash, str) or not intent_hash:
            # A ledger row without a recorded digest cannot prove the prior intent
            # matched. Treating it as no prior command would let an idempotency key
            # reused for a different request through as a fresh write, so it fails
            # closed instead.
            raise CommandValidationError(
                "A prior governed configuration command is missing its recorded intent."
            )
        return PriorReceipt(
            item_id=_as_uuid(row["target_id"]),
            intent_hash=intent_hash,
            expected_version=int(row["expected_version"]),
            resulting_version=int(row["resulting_version"]),
            result_id=_as_uuid(row["result_id"]),
            occurred_at=_as_datetime(row["occurred_at"]),
        )

    async def append_audit_event(
        self,
        session: AsyncSession,
        envelope: CommandEnvelope,
        event: ConfigurationAuditEvent,
        *,
        correlation_id: UUID,
        occurred_at: datetime,
    ) -> None:
        _require_aware(occurred_at)
        # The governance detail is redacted through the typed seam first, then the
        # command identity is attached under its reserved key, then the whole
        # mapping passes through the seam again. The persisted payload therefore
        # never contains a value that skipped redaction.
        persisted = AuditPayload(
            {
                **dict(event.payload.as_redacted()),
                _COMMAND_KEY: {
                    "operation": envelope.operation,
                    "idempotencyKey": envelope.idempotency_key,
                    "intentHash": envelope.intent_hash,
                    "expectedVersion": event.expected_version,
                    "resultingVersion": event.resulting_version,
                    "resultId": str(event.result_id),
                },
            }
        )
        await session.execute(
            _AUDIT_INSERT,
            {
                "id": str(uuid6.uuid7()),
                "org_id": str(envelope.org_id),
                "actor_id": str(envelope.actor_id),
                "action": event.action,
                "target_type": event.target_type,
                "target_id": str(event.target_id),
                "payload": dict(persisted.as_redacted()),
                "occurred_at": occurred_at,
                "correlation_id": str(correlation_id),
            },
        )

    async def _classify_transition_miss(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        config_id: UUID,
    ) -> None:
        """Classify a lifecycle compare-and-swap miss by scoped existence.

        Never returns normally. A binding still visible in the organization scope
        moved to a stage the command did not read, which is a typed stale-version
        conflict; an absent or foreign binding keeps neutral not-found parity.
        """
        exists = (
            await session.execute(
                _CONFIGURATION_EXISTS,
                {"config_id": str(config_id), "org_id": str(org_id)},
            )
        ).first()
        if exists is not None:
            raise StaleVersionConflictError()
        raise CommandNotFoundError()


def _project(row: sa.RowMapping) -> ProtectedConfiguration:
    return ProtectedConfiguration(
        config_id=_as_uuid(row["id"]),
        org_id=_as_uuid(row["org_id"]),
        lifecycle=parse_lifecycle(str(row["lifecycle"])),
        policy_version=str(row["policy_version"]),
        prompt_version=str(row["prompt_version"]),
        created_at=_as_datetime(row["created_at"]),
        label=_as_optional_text(row["label"]),
        rationale=_as_optional_text(row["rationale"]),
        validation_issues=parse_validation_issues(row["validation_issues"]),
        activated_by=_as_optional_uuid(row["activated_by"]),
        activated_at=_as_optional_datetime(row["activated_at"]),
        validated_by=_as_optional_uuid(row["validated_by"]),
        validated_at=_as_optional_datetime(row["validated_at"]),
        superseded_at=_as_optional_datetime(row["superseded_at"]),
        superseded_by=_as_optional_uuid(row["superseded_by"]),
        created_by=_as_optional_uuid(row["created_by"]),
    )


def _require_aware(value: datetime) -> None:
    """Reject naive datetimes on the write path.

    The lifecycle columns store timezone-aware instants; a naive datetime is
    ambiguous and must not be silently coerced to UTC.
    """
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise CommandValidationError("The occurred_at timestamp must be timezone-aware.")


def _optional_str(value: UUID | None) -> str | None:
    return None if value is None else str(value)


def _as_uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _as_optional_uuid(value: Any) -> UUID | None:
    return None if value is None else _as_uuid(value)


def _as_optional_text(value: Any) -> str | None:
    return None if value is None else str(value)


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _as_optional_datetime(value: Any) -> datetime | None:
    return None if value is None else _as_datetime(value)


__all__ = ["SqlProtectedConfigurationRepository"]

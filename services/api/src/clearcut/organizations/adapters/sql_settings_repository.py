"""Session-bound SQL adapter for the organization-settings port.

Every statement runs on the caller-provided
:class:`~sqlalchemy.ext.asyncio.AsyncSession` and never opens, commits, or rolls
back its own transaction, so the settings write, the accountable command
receipt, and the authoritative audit event share one atomic unit of work.

Scope is the authenticated ``org_id`` alone: organization settings are
organization-owned, so there is no project path scope to apply and nothing here
is global. A missing organization surfaces as a typed
:class:`~clearcut.commanding.errors.CommandNotFoundError` with the same neutral
shape whether it is absent or foreign.

Why this adapter owns the audit insert
--------------------------------------
The governed-command kernel's SQL seams are project-shaped, and neither can
express an organization-level command as they stand:

* ``governed_command_receipts`` declares ``project_id`` and ``item_id`` as NOT
  NULL with foreign keys onto ``projects`` and ``clearance_items``. An
  organization command has neither, so no row can be written there without a
  schema change.
* :func:`clearcut.commanding.sql.insert_authoritative_audit` stringifies
  ``envelope.project_id`` unconditionally, so it cannot produce the null
  ``project_id`` that makes an organization-owned audit row correct.

``authoritative_audit_events.project_id`` *is* nullable, which is exactly what
an organization-level event needs. So this adapter writes that one row itself,
using the identical column set and the same typed
:class:`~clearcut.commanding.domain.AuditPayload` seam the kernel helper uses,
with ``project_id`` null. That single audit row is also the accountable
idempotency receipt for the operation: it carries the command identity
(operation, idempotency key, intent hash, expected/resulting version, result id)
under a reserved ``command`` key, and :meth:`find_prior_receipt` replays from it.

That makes the receipt's uniqueness advisory rather than database-enforced. The
durable guard against a same-key double write here is the version-guarded
compare-and-swap on ``organizations.version``: the loser of a concurrent race
fails the swap and receives a typed stale-version conflict rather than writing
twice. A dedicated organization-scoped receipt table (with the unique scope
constraint the project-scoped kernel table has) would restore the durable
guarantee and is the right follow-up; it needs a migration, which is owned
elsewhere.
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
from clearcut.organizations.ports.settings_repository import (
    MonitoringCadence,
    OrganizationAuditEvent,
    OrganizationSettings,
)
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

# The reserved audit-payload key that carries command identity. The domain detail
# (which fields changed, and their humanized before/after values) stays at the
# top level, so a reader of the payload sees the change first and the machinery
# second.
_COMMAND_KEY = "command"

_LOAD_SETTINGS = sa.text(
    """
    SELECT id, name, slug, jurisdiction, default_monitoring_cadence, version
    FROM organizations
    WHERE id = :org_id
    """
)

# slug is deliberately absent from the SET list: it is the organization's URL
# identity and is never writable through this port.
_UPDATE_SETTINGS = sa.text(
    """
    UPDATE organizations
    SET name = :name,
        jurisdiction = :jurisdiction,
        default_monitoring_cadence = :cadence,
        version = :resulting_version
    WHERE id = :org_id AND version = :expected_version
    """
)

_ORGANIZATION_EXISTS = sa.text("SELECT 1 FROM organizations WHERE id = :org_id")

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


def _idempotency_key_sql(dialect_name: str) -> str:
    """Return a trusted SQL fragment reading the receipt's idempotency key.

    The payload column is JSON on SQLite and JSONB on PostgreSQL, so the
    extraction differs by dialect. An unsupported dialect fails loudly rather
    than silently matching nothing, which would turn every replay into a second
    write.
    """
    if dialect_name == "postgresql":
        return f"payload_redacted -> '{_COMMAND_KEY}' ->> 'idempotencyKey'"
    if dialect_name == "sqlite":
        return f"json_extract(payload_redacted, '$.{_COMMAND_KEY}.idempotencyKey')"
    raise RuntimeError(f"Unsupported database dialect for organization receipts: {dialect_name}")


def _payload_field_sql(dialect_name: str, field: str) -> str:
    if dialect_name == "postgresql":
        return f"payload_redacted -> '{_COMMAND_KEY}' ->> '{field}'"
    if dialect_name == "sqlite":
        return f"json_extract(payload_redacted, '$.{_COMMAND_KEY}.{field}')"
    raise RuntimeError(f"Unsupported database dialect for organization receipts: {dialect_name}")


class SqlOrganizationSettingsRepository:
    """SQL implementation of :class:`OrganizationSettingsRepositoryPort`."""

    async def load_settings(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
    ) -> OrganizationSettings:
        row = (
            (await session.execute(_LOAD_SETTINGS, {"org_id": str(org_id)})).mappings().first()
        )
        if row is None:
            raise CommandNotFoundError()
        return OrganizationSettings(
            org_id=_as_uuid(row["id"]),
            name=str(row["name"]),
            slug=str(row["slug"]),
            jurisdiction=None if row["jurisdiction"] is None else str(row["jurisdiction"]),
            default_monitoring_cadence=_as_cadence(row["default_monitoring_cadence"]),
            version=int(row["version"]),
        )

    async def update_settings(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        name: str,
        jurisdiction: str | None,
        default_monitoring_cadence: MonitoringCadence,
        expected_version: int,
        resulting_version: int,
    ) -> None:
        result = await session.execute(
            _UPDATE_SETTINGS,
            {
                "org_id": str(org_id),
                "name": name,
                "jurisdiction": jurisdiction,
                "cadence": default_monitoring_cadence.value,
                "expected_version": expected_version,
                "resulting_version": resulting_version,
            },
        )
        # The version-guarded compare-and-swap must match exactly one row. Zero
        # rows means the organization moved between load and update: a
        # still-present organization is a stale-version conflict (409), while an
        # absent one keeps neutral not-found parity (404). The caller's
        # transaction must not commit settings against a version that changed
        # under it.
        if cast(CursorResult[Any], result).rowcount != 1:
            exists = (
                await session.execute(_ORGANIZATION_EXISTS, {"org_id": str(org_id)})
            ).first()
            if exists is None:
                raise CommandNotFoundError()
            raise StaleVersionConflictError()

    async def find_prior_receipt(
        self,
        session: AsyncSession,
        envelope: CommandEnvelope,
        *,
        action: str,
    ) -> PriorReceipt | None:
        dialect_name = session.get_bind().dialect.name
        key_sql = _idempotency_key_sql(dialect_name)
        intent_sql = _payload_field_sql(dialect_name, "intentHash")
        expected_sql = _payload_field_sql(dialect_name, "expectedVersion")
        resulting_sql = _payload_field_sql(dialect_name, "resultingVersion")
        result_id_sql = _payload_field_sql(dialect_name, "resultId")
        operation_sql = _payload_field_sql(dialect_name, "operation")
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
        return PriorReceipt(
            # The governed aggregate for this command is the organization itself.
            item_id=_as_uuid(row["target_id"]),
            intent_hash=str(row["intent_hash"]),
            expected_version=int(row["expected_version"]),
            resulting_version=int(row["resulting_version"]),
            result_id=_as_uuid(row["result_id"]),
            occurred_at=_as_datetime(row["occurred_at"]),
        )

    async def append_audit_event(
        self,
        session: AsyncSession,
        envelope: CommandEnvelope,
        event: OrganizationAuditEvent,
        *,
        correlation_id: UUID,
        occurred_at: datetime,
    ) -> None:
        _require_aware(occurred_at)
        # The domain detail is redacted through the typed seam first, then the
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


def _as_cadence(value: Any) -> MonitoringCadence:
    """Parse a stored cadence token, failing closed on an unknown value."""
    try:
        return MonitoringCadence(str(value))
    except ValueError as error:
        raise CommandValidationError(
            "The stored monitoring cadence is outside the canonical vocabulary."
        ) from error


def _require_aware(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise CommandValidationError("The occurred_at timestamp must be timezone-aware.")
    return value


def _as_uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


__all__ = ["SqlOrganizationSettingsRepository"]

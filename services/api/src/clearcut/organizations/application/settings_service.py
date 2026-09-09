"""Application service for reading and governing organization settings.

Reading is an ordinary organization-scoped query: any active member of the
authenticated organization may see the settings, and the delivery boundary has
already proven that membership.

Updating is a **governed mutation**. One accepted command changes exactly one
organization's operational settings and:

1. Loads the exact organization-scoped settings (typed not-found parity when it
   is not visible).
2. Derives capability from the server-provided role only, never from the client.
3. Validates the inputs: a blank or whitespace-only name is a typed validation
   error, and the slug is not an input at all.
4. Classifies the command through the shared governed-command kernel: an
   idempotent replay of a prior receipt returns the original result, a reused key
   carrying a different intent is a typed conflict, and a stale
   ``expectedVersion`` is a typed conflict.
5. For a fresh command, advances the settings under a version-guarded
   compare-and-swap, resolves the accountable receipt, and appends the
   authoritative audit event — all in the caller's single transaction, so any
   failure rolls the whole change back.

The transactional choreography is the shared
:func:`~clearcut.commanding.template.execute_governed_command`; this module
supplies only the settings specifics (capability, name validation, the write, and
the audit/projection shapes) as injected hooks.

Cadence vocabulary
------------------
The cadence is stored canonically as ``off | manual | daily | weekly`` and only
ever *displayed* through :func:`~clearcut.organizations.ports.settings_repository.cadence_label`.
The audit event follows the same rule: it records the humanized before/after
labels ("Weekly" -> "Daily"), not the stored tokens, because the ledger and the
surfaces must describe one change in one vocabulary. The payload names only the
fields that actually changed.

Deliberately absent: any evidence-retention duration. Evidence is kept until its
project is deleted, so there is no retention field to set here.

Only typed results or typed governed-command errors cross this boundary.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from clearcut.commanding.domain import AuditPayload, CommandEnvelope, PriorReceipt
from clearcut.commanding.errors import CommandForbiddenError, CommandValidationError
from clearcut.commanding.template import (
    GovernedCommandContext,
    execute_governed_command,
)
from clearcut.organizations.domain.capabilities import has_capability
from clearcut.organizations.ports.settings_repository import (
    MonitoringCadence,
    OrganizationAuditEvent,
    OrganizationSettings,
    OrganizationSettingsRepositoryPort,
    cadence_label,
)
from sqlalchemy.ext.asyncio import AsyncSession

# The governed operation name that scopes receipts for this command.
_OPERATION = "organization.settings.update"

# Capability, derived from the server-provided role only. ``member:manage`` is the
# existing organization-administration capability held by exactly Owner and Admin;
# no dedicated organization-settings capability exists in the role matrix, and
# inventing one is a protected, human-only change. ``governance:manage`` was the
# other candidate and was rejected: it is Owner-only and covers the protected
# rules (permissions, sign-off policy, categories, authority tiers), while these
# are operational settings Admin is meant to manage.
_SETTINGS_CAPABILITY = "member:manage"

_AUDIT_ACTION = "organization.settings.updated"
_AUDIT_TARGET_TYPE = "organization"

# The contract field names, reused verbatim as the audit vocabulary so the
# ledger, the API, and the surface all name one field the same way.
_NAME_FIELD = "name"
_JURISDICTION_FIELD = "jurisdiction"
_CADENCE_FIELD = "defaultMonitoringCadence"

_UNSET_DISPLAY = "Not set"


@dataclass(frozen=True)
class UpdateOrganizationSettingsCommand:
    """A validated request to update one organization's settings.

    ``org_id`` and ``actor_role`` are server-derived: the delivery boundary takes
    them from the authenticated request scope, never from the path or the body.
    The slug is absent by design — it is the URL identity and cannot be changed
    through this command.
    """

    org_id: UUID
    actor_id: UUID
    actor_role: str
    name: str
    jurisdiction: str | None
    default_monitoring_cadence: MonitoringCadence
    expected_version: int
    idempotency_key: str


class OrganizationSettingsService:
    """Coordinates organization-settings reads and one governed update."""

    def __init__(self, repository: OrganizationSettingsRepositoryPort) -> None:
        self._repository = repository

    async def read(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
    ) -> OrganizationSettings:
        """Return the settings for the authenticated organization.

        Any active member may read. Raises
        :class:`~clearcut.commanding.errors.CommandNotFoundError` when the
        organization is not visible in scope.
        """
        return await self._repository.load_settings(session, org_id=org_id)

    async def update(
        self,
        session: AsyncSession,
        command: UpdateOrganizationSettingsCommand,
    ) -> OrganizationSettings:
        """Apply one governed settings update inside the caller's transaction."""
        name = command.name.strip()
        if not name:
            raise CommandValidationError("An organization name is required.")
        jurisdiction = _normalize_optional(command.jurisdiction)

        # The intent is derived from the validated command server-side, so the
        # same key replayed with the same intent is an idempotent replay while the
        # same key carrying different values is a typed conflict. Canonical JSON
        # keeps the digest unambiguous regardless of field content.
        intent_hash = _intent_hash(
            operation=_OPERATION,
            org_id=command.org_id,
            name=name,
            jurisdiction=jurisdiction,
            cadence=command.default_monitoring_cadence,
            expected_version=command.expected_version,
        )

        # Build the typed envelope first: a malformed key or version is a typed
        # validation error before any storage is touched. The kernel envelope
        # carries a project field that an organization-owned command has no value
        # for; the organization stands in, and it is never written to any
        # project column (the authoritative audit row's project_id is null).
        envelope = CommandEnvelope(
            org_id=command.org_id,
            project_id=command.org_id,
            actor_id=command.actor_id,
            operation=_OPERATION,
            idempotency_key=command.idempotency_key,
            intent_hash=intent_hash,
            expected_version=command.expected_version,
        )

        async def load_item(
            session: AsyncSession,
            _envelope: CommandEnvelope,
        ) -> OrganizationSettings:
            return await self._repository.load_settings(session, org_id=command.org_id)

        def check_capability() -> None:
            if not has_capability(command.actor_role, _SETTINGS_CAPABILITY):
                raise CommandForbiddenError()

        def validate_domain(_settings: OrganizationSettings) -> None:
            # The name was validated before the envelope; the cadence vocabulary
            # is closed at the request boundary and again by the database check
            # constraint. Nothing about the loaded row can invalidate the command.
            return None

        async def lookup_receipt(
            session: AsyncSession,
            envelope: CommandEnvelope,
        ) -> PriorReceipt | None:
            return await self._repository.find_prior_receipt(
                session,
                envelope,
                action=_AUDIT_ACTION,
            )

        async def commit_provisional(
            session: AsyncSession,
            context: GovernedCommandContext[OrganizationSettings],
        ) -> None:
            await self._repository.update_settings(
                session,
                org_id=command.org_id,
                name=name,
                jurisdiction=jurisdiction,
                default_monitoring_cadence=command.default_monitoring_cadence,
                expected_version=context.item.version,
                resulting_version=context.resulting_version,
            )

        async def persist_receipt(
            session: AsyncSession,
            envelope: CommandEnvelope,
            _context: GovernedCommandContext[OrganizationSettings],
        ) -> PriorReceipt | None:
            # The accountable receipt for this organization-level command is the
            # authoritative audit row itself, which is appended below in the same
            # transaction. This step is the concurrent-duplicate reconciliation
            # the template expects: if another writer already committed this exact
            # key, return its receipt so the loser replays instead of writing
            # twice. The version-guarded compare-and-swap above is the durable
            # guard, so reaching here with a committed duplicate is rare.
            return await self._repository.find_prior_receipt(
                session,
                envelope,
                action=_AUDIT_ACTION,
            )

        def build_audit(
            context: GovernedCommandContext[OrganizationSettings],
        ) -> OrganizationAuditEvent:
            changes = _describe_changes(
                before=context.item,
                name=name,
                jurisdiction=jurisdiction,
                cadence=command.default_monitoring_cadence,
            )
            return OrganizationAuditEvent(
                action=_AUDIT_ACTION,
                target_type=_AUDIT_TARGET_TYPE,
                target_id=command.org_id,
                payload=AuditPayload(
                    {
                        "orgId": str(command.org_id),
                        "changedFields": list(changes.keys()),
                        "changes": {
                            field: {"before": change[0], "after": change[1]}
                            for field, change in changes.items()
                        },
                        "detail": _detail(changes),
                    }
                ),
                expected_version=context.item.version,
                resulting_version=context.resulting_version,
                result_id=context.result_id,
            )

        async def append_audit(session, envelope, audit, correlation_id, occurred_at) -> None:
            # The authoritative audit event is also this command's accountable
            # receipt, so it is the last write of the unit of work: any failure
            # here rolls back the settings change and the version advance too.
            await self._repository.append_audit_event(
                session,
                envelope,
                audit,
                correlation_id=correlation_id,
                occurred_at=occurred_at,
            )

        async def load_replay_result(
            session: AsyncSession,
            _envelope: CommandEnvelope,
            prior: PriorReceipt,
        ) -> OrganizationSettings:
            # The organization already reflects the prior command's write; the
            # replay reports it at the version that command produced.
            settings = await self._repository.load_settings(session, org_id=command.org_id)
            return OrganizationSettings(
                org_id=settings.org_id,
                name=settings.name,
                slug=settings.slug,
                jurisdiction=settings.jurisdiction,
                default_monitoring_cadence=settings.default_monitoring_cadence,
                version=prior.resulting_version,
            )

        def project_result(
            context: GovernedCommandContext[OrganizationSettings],
        ) -> OrganizationSettings:
            return OrganizationSettings(
                org_id=command.org_id,
                # The slug is carried through from storage, never from the client.
                slug=context.item.slug,
                name=name,
                jurisdiction=jurisdiction,
                default_monitoring_cadence=command.default_monitoring_cadence,
                version=context.resulting_version,
            )

        return await execute_governed_command(
            session,
            envelope,
            load_item=load_item,
            check_capability=check_capability,
            validate_domain=validate_domain,
            current_version=lambda settings: settings.version,
            lookup_receipt=lookup_receipt,
            commit_provisional=commit_provisional,
            persist_receipt=persist_receipt,
            build_audit=build_audit,
            append_audit=append_audit,
            load_replay_result=load_replay_result,
            project_result=project_result,
        )


def _normalize_optional(value: str | None) -> str | None:
    """Collapse an omitted or whitespace-only optional string to absence."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _intent_hash(
    *,
    operation: str,
    org_id: UUID,
    name: str,
    jurisdiction: str | None,
    cadence: MonitoringCadence,
    expected_version: int,
) -> str:
    canonical = json.dumps(
        [operation, str(org_id), name, jurisdiction, cadence.value, expected_version],
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _describe_changes(
    *,
    before: OrganizationSettings,
    name: str,
    jurisdiction: str | None,
    cadence: MonitoringCadence,
) -> dict[str, tuple[Any, Any]]:
    """Return the humanized before/after pair for changed fields only.

    Unchanged fields are absent from the result, so the audit entry cannot claim
    a change that did not happen. The cadence exits through its label map, so the
    ledger says "Weekly" where a surface says "Weekly", never ``weekly``.
    """
    changes: dict[str, tuple[Any, Any]] = {}
    if before.name != name:
        changes[_NAME_FIELD] = (before.name, name)
    if before.jurisdiction != jurisdiction:
        changes[_JURISDICTION_FIELD] = (before.jurisdiction, jurisdiction)
    if before.default_monitoring_cadence != cadence:
        changes[_CADENCE_FIELD] = (
            cadence_label(before.default_monitoring_cadence),
            cadence_label(cadence),
        )
    return changes


def _detail(changes: Mapping[str, tuple[Any, Any]]) -> str:
    """Render the changed fields the way every other receipt detail reads."""
    if not changes:
        return "no fields changed"
    return " · ".join(
        f"{field}: {_display(before)} → {_display(after)}"
        for field, (before, after) in changes.items()
    )


def _display(value: Any) -> str:
    if value is None:
        return _UNSET_DISPLAY
    return str(value)


__all__ = [
    "OrganizationSettingsService",
    "UpdateOrganizationSettingsCommand",
]

"""Application service for the governed clearance-item disposition slice.

One accepted command records exactly one human workflow disposition on an exact,
tenant-and-project-scoped clearance item. A disposition is a *workflow* signal
only: it never asserts a legal conclusion, never guarantees legal clearance, and
never changes the item's clearance ``status``. The service:

1. Loads the exact scoped item (typed not-found parity when it is not visible).
2. Derives capability from the server-provided role (never client-supplied);
   Owner, Admin, and Reviewer may set a disposition.
3. Validates the canonical :class:`ClearanceDisposition` value and the
   zero-evidence protection: the clearance-like ``verified`` outcome requires at
   least one cited evidence claim, while the other workflow dispositions
   (``pending``, ``ruled_out``, ``fixed_in_rewrite``, ``deferred``) remain
   allowed with zero claims so reviewers can move an unresolved item forward
   without fabricated evidence.
4. Classifies the command through the shared kernel: an idempotent replay of a
   prior receipt returns the original persisted result; a reused key with a
   different intent is a typed conflict; a stale expected version is a typed
   conflict.
5. For a fresh command, inserts the immutable disposition record, advances the
   item version and disposition with an optimistic compare-and-swap, writes the
   accountable idempotency receipt (reconciling a concurrent duplicate key into
   an idempotent replay), and appends the authoritative audit event through the
   typed :class:`~clearcut.commanding.domain.AuditPayload` seam — all in the
   caller's single transaction, so any failure rolls the whole disposition back.

The transactional choreography for steps 1 and 4-5 is the shared
:func:`~clearcut.commanding.template.execute_governed_command`; this module
supplies only the disposition specifics (capability, zero-evidence rule, the
disposition write that never mutates clearance status, and the audit/projection
shapes) as injected hooks. The module keeps its own ``lookup_command_receipt``
and ``insert_authoritative_audit`` references so the kernel SQL seams remain
patchable at this boundary.

Only typed results or typed governed-command errors cross the boundary; no
booleans, ``None`` sentinels, or raw dicts encode decisions, and the audit
payload is never assembled by string interpolation of caller input.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from clearcut.commanding.domain import AuditPayload, CommandEnvelope, PriorReceipt
from clearcut.commanding.errors import (
    CommandForbiddenError,
    CommandValidationError,
)
from clearcut.commanding.sql import (
    insert_authoritative_audit,
    lookup_command_receipt,
)
from clearcut.commanding.template import (
    GovernedAudit,
    GovernedCommandContext,
    execute_governed_command,
)
from clearcut.decisions.application.projection import project_decision
from clearcut.decisions.ports.repository import (
    DecisionRepositoryPort,
    PersistedDecision,
    ScopedItem,
)
from clearcut.organizations.domain.capabilities import has_capability
from sqlalchemy.ext.asyncio import AsyncSession

# The governed operation name that scopes idempotency receipts for this command.
_OPERATION = "decision.disposition.set"
_DISPOSITION_CAPABILITY = "item:disposition"
_AUDIT_TARGET_TYPE = "clearance_item"
_AUDIT_ACTION = "decision.disposition.set"


class ClearanceDisposition(StrEnum):
    """The canonical, contract-aligned clearance-disposition vocabulary.

    These are pre-clearance *workflow* dispositions; none guarantees legal
    clearance.
    """

    PENDING = "pending"
    VERIFIED = "verified"
    RULED_OUT = "ruled_out"
    FIXED_IN_REWRITE = "fixed_in_rewrite"
    DEFERRED = "deferred"


# Only the clearance-like ``verified`` disposition requires cited evidence; the
# other workflow dispositions are explicitly permitted with zero claims so a
# reviewer can advance an unresolved item without fabricated evidence. This keeps
# the unresolved-evidence protection intact: a disposition can never stand in for
# a clearance-like signal that is not grounded in a cited source.
_REQUIRES_CITED_EVIDENCE: frozenset[ClearanceDisposition] = frozenset(
    {ClearanceDisposition.VERIFIED}
)


@dataclass(frozen=True)
class SetDispositionCommand:
    """A validated request to set one clearance-item disposition.

    ``actor_role`` is the server-derived membership role; capability is never
    taken from the client. ``expected_version`` and ``intent_hash`` are the
    optimistic-concurrency and intent inputs the shared kernel validates.
    """

    org_id: UUID
    project_id: UUID
    item_id: UUID
    actor_id: UUID
    actor_role: str
    disposition: ClearanceDisposition
    rationale: str
    expected_version: int
    intent_hash: str
    idempotency_key: str


class SetDispositionService:
    """Coordinates one governed disposition within a single transaction."""

    def __init__(self, repository: DecisionRepositoryPort) -> None:
        self._repository = repository

    async def set_disposition(
        self,
        session: AsyncSession,
        command: SetDispositionCommand,
    ) -> PersistedDecision:
        rationale = command.rationale.strip()
        if not rationale:
            raise CommandValidationError("A non-empty rationale is required.")

        # Build the typed envelope first; malformed intent/version is a typed
        # validation error before any storage is touched.
        envelope = CommandEnvelope(
            org_id=command.org_id,
            project_id=command.project_id,
            actor_id=command.actor_id,
            operation=_OPERATION,
            idempotency_key=command.idempotency_key,
            intent_hash=command.intent_hash,
            expected_version=command.expected_version,
        )

        async def load_item(session: AsyncSession, envelope: CommandEnvelope) -> ScopedItem:
            # Load the exact scoped item (typed not-found parity on absence/foreign).
            return await self._repository.load_scoped_item(
                session,
                org_id=command.org_id,
                project_id=command.project_id,
                item_id=command.item_id,
            )

        def check_capability() -> None:
            # Capability is derived from the server-provided role only.
            if not has_capability(command.actor_role, _DISPOSITION_CAPABILITY):
                raise CommandForbiddenError()

        def validate_domain(item: ScopedItem) -> None:
            # Zero-evidence protection: a clearance-like ``verified`` disposition
            # requires at least one cited evidence claim and must not bypass it.
            if command.disposition in _REQUIRES_CITED_EVIDENCE and item.cited_claim_count < 1:
                raise CommandValidationError(
                    "A clearance-like disposition requires at least one cited evidence claim."
                )

        async def lookup_receipt(session: AsyncSession, envelope: CommandEnvelope):
            # Resolve the kernel seam through this module so tests that patch
            # ``lookup_command_receipt`` on the service module are honoured.
            return await lookup_command_receipt(session, envelope)

        async def commit_provisional(
            session: AsyncSession,
            context: GovernedCommandContext[ScopedItem],
        ) -> None:
            # Insert the immutable disposition record and advance the item's
            # version and disposition via a version-guarded compare-and-swap. A
            # disposition never mutates the clearance status, so the write can
            # never assert a legal conclusion.
            await self._repository.commit_disposition(
                session,
                decision_id=context.result_id,
                org_id=command.org_id,
                project_id=command.project_id,
                item_id=command.item_id,
                actor_id=command.actor_id,
                disposition_value=command.disposition.value,
                rationale=rationale,
                expected_version=context.item.version,
                resulting_version=context.resulting_version,
                occurred_at=context.occurred_at,
            )

        async def persist_receipt(
            session: AsyncSession,
            envelope: CommandEnvelope,
            context: GovernedCommandContext[ScopedItem],
        ):
            return await self._repository.persist_receipt_idempotent(
                session,
                envelope,
                item_id=command.item_id,
                resulting_version=context.resulting_version,
                result_id=context.result_id,
                occurred_at=context.occurred_at,
            )

        def build_audit(context: GovernedCommandContext[ScopedItem]) -> GovernedAudit:
            # The payload records the workflow disposition only; it never asserts
            # a legal conclusion and is built through the typed AuditPayload seam.
            return GovernedAudit(
                action=_AUDIT_ACTION,
                target_type=_AUDIT_TARGET_TYPE,
                target_id=command.item_id,
                payload=AuditPayload(
                    {
                        "decisionId": str(context.result_id),
                        "disposition": command.disposition.value,
                        "expectedVersion": context.item.version,
                        "resultingVersion": context.resulting_version,
                        "citedClaimCount": context.item.cited_claim_count,
                    }
                ),
            )

        async def append_audit(session, envelope, audit, correlation_id, occurred_at) -> None:
            # Resolve the kernel seam through this module so tests that patch
            # ``insert_authoritative_audit`` on the service module are honoured.
            await insert_authoritative_audit(
                session,
                envelope,
                action=audit.action,
                target_type=audit.target_type,
                target_id=audit.target_id,
                payload=audit.payload,
                correlation_id=correlation_id,
                occurred_at=occurred_at,
            )

        async def load_replay_result(
            session: AsyncSession,
            replay_envelope: CommandEnvelope,
            prior: PriorReceipt,
        ) -> PersistedDecision:
            item = await load_item(session, replay_envelope)
            return project_decision(
                item,
                decision_id=prior.result_id,
                resulting_version=prior.resulting_version,
                status=item.status,
                disposition_status=item.disposition_status,
            )

        def project_result(context: GovernedCommandContext[ScopedItem]) -> PersistedDecision:
            # A disposition never mutates the clearance status; project the
            # item's existing status so the response cannot imply a legal
            # conclusion, and carry the new disposition value forward.
            return project_decision(
                context.item,
                decision_id=context.result_id,
                resulting_version=context.resulting_version,
                status=context.item.status,
                disposition_status=command.disposition.value,
            )

        return await execute_governed_command(
            session,
            envelope,
            load_item=load_item,
            check_capability=check_capability,
            validate_domain=validate_domain,
            current_version=lambda item: item.version,
            lookup_receipt=lookup_receipt,
            commit_provisional=commit_provisional,
            persist_receipt=persist_receipt,
            build_audit=build_audit,
            append_audit=append_audit,
            load_replay_result=load_replay_result,
            project_result=project_result,
        )


__all__ = [
    "ClearanceDisposition",
    "SetDispositionCommand",
    "SetDispositionService",
]

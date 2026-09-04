"""Application service for the governed evidence-decision vertical slice.

One accepted command records exactly one human evidence decision on an exact,
tenant-and-project-scoped clearance item. The service:

1. Loads the exact scoped item (typed not-found parity when it is not visible).
2. Derives capability from the server-provided role (never client-supplied).
3. Validates the canonical decision value and the zero-evidence protection: a
   clearance-like (``accepted``) outcome requires at least one cited evidence
   claim, while escalation outcomes (``rejected``, ``further_review_required``)
   remain allowed with zero claims.
4. Classifies the command through the shared kernel: an idempotent replay of a
   prior receipt returns the original persisted result; a reused key with a
   different intent is a typed conflict; a stale expected version is a typed
   conflict.
5. For a fresh command, inserts the immutable decision, advances the item
   version/status with an optimistic compare-and-swap, writes the accountable
   idempotency receipt (reconciling a concurrent duplicate key into an
   idempotent replay), and appends the authoritative audit event — all in the
   caller's single transaction, so any failure rolls the whole decision back.

The transactional choreography for steps 1 and 4-5 is the shared
:func:`~clearcut.commanding.template.execute_governed_command`; this module
supplies only the evidence-decision specifics (capability, zero-evidence rule,
deterministic post-decision status, the decision write, and the audit/projection
shapes) as injected hooks. The module keeps its own ``lookup_command_receipt``
and ``insert_authoritative_audit`` references so the kernel SQL seams remain
patchable at this boundary.

The service never fabricates evidence and never emits a legal conclusion: the
recorded outcome is a reviewer's treatment of cited evidence for pre-clearance
workflow, not a legal-clearance guarantee. Only typed results or typed
governed-command errors cross the boundary.
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
_OPERATION = "decision.evidence.record"
_DECIDE_CAPABILITY = "item:decide"
_AUDIT_TARGET_TYPE = "clearance_item"
_AUDIT_ACTION = "decision.evidence.recorded"


class EvidenceDecisionValue(StrEnum):
    """The canonical, contract-aligned evidence decision vocabulary."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    FURTHER_REVIEW_REQUIRED = "further_review_required"


# Only a clearance-like accept outcome requires cited evidence; escalation
# outcomes are explicitly permitted with zero claims so reviewers can move an
# unresolved item forward without fabricated evidence.
_REQUIRES_CITED_EVIDENCE: frozenset[EvidenceDecisionValue] = frozenset(
    {EvidenceDecisionValue.ACCEPTED}
)

# Deterministic post-decision item status. Escalation outcomes keep the item in
# active human review; only an accepted outcome resolves it. No status implies a
# legal conclusion.
_STATUS_BY_DECISION: dict[EvidenceDecisionValue, str] = {
    EvidenceDecisionValue.ACCEPTED: "resolved",
    EvidenceDecisionValue.REJECTED: "in_review",
    EvidenceDecisionValue.FURTHER_REVIEW_REQUIRED: "in_review",
}


@dataclass(frozen=True)
class RecordEvidenceDecisionCommand:
    """A validated request to record one evidence decision.

    ``actor_role`` is the server-derived membership role; capability is never
    taken from the client. ``expected_version`` and ``intent_hash`` are the
    optimistic-concurrency and intent inputs the shared kernel validates.
    """

    org_id: UUID
    project_id: UUID
    item_id: UUID
    actor_id: UUID
    actor_role: str
    decision: EvidenceDecisionValue
    rationale: str
    expected_version: int
    intent_hash: str
    idempotency_key: str


class RecordEvidenceDecisionService:
    """Coordinates one governed evidence decision within a single transaction."""

    def __init__(self, repository: DecisionRepositoryPort) -> None:
        self._repository = repository

    async def record(
        self,
        session: AsyncSession,
        command: RecordEvidenceDecisionCommand,
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
        next_status = _STATUS_BY_DECISION[command.decision]

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
            if not has_capability(command.actor_role, _DECIDE_CAPABILITY):
                raise CommandForbiddenError()

        def validate_domain(item: ScopedItem) -> None:
            # Zero-evidence protection: a clearance-like accept requires cited claims.
            if command.decision in _REQUIRES_CITED_EVIDENCE and item.cited_claim_count < 1:
                raise CommandValidationError(
                    "A clearance-like decision requires at least one cited evidence claim."
                )

        async def lookup_receipt(session: AsyncSession, envelope: CommandEnvelope):
            # Resolve the kernel seam through this module so tests that patch
            # ``lookup_command_receipt`` on the service module are honoured.
            return await lookup_command_receipt(session, envelope)

        async def commit_provisional(
            session: AsyncSession,
            context: GovernedCommandContext[ScopedItem],
        ) -> None:
            # Insert the immutable decision and advance the item version/status
            # via a version-guarded compare-and-swap on the loaded version.
            await self._repository.commit_decision(
                session,
                decision_id=context.result_id,
                org_id=command.org_id,
                project_id=command.project_id,
                item_id=command.item_id,
                actor_id=command.actor_id,
                decision_value=command.decision.value,
                rationale=rationale,
                expected_version=context.item.version,
                resulting_version=context.resulting_version,
                next_status=next_status,
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
            # The payload records the sourced outcome only; it never asserts a
            # legal conclusion and is built through the typed AuditPayload seam.
            return GovernedAudit(
                action=_AUDIT_ACTION,
                target_type=_AUDIT_TARGET_TYPE,
                target_id=command.item_id,
                payload=AuditPayload(
                    {
                        "decisionId": str(context.result_id),
                        "decision": command.decision.value,
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
            return project_decision(
                context.item,
                decision_id=context.result_id,
                resulting_version=context.resulting_version,
                status=next_status,
                disposition_status=context.item.disposition_status,
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
    "EvidenceDecisionValue",
    "RecordEvidenceDecisionCommand",
    "RecordEvidenceDecisionService",
]

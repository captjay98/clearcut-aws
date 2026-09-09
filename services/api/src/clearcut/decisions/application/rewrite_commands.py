"""Application service for the governed rewrite-proposal lifecycle.

This module replaced an in-memory ``dict``-and-``list`` store that presented
itself as a production service: proposals lived in process memory, audit events
were appended to a Python list, and nothing survived a restart -- while the
shipped UI called the operations as if they persisted. Every operation here now
runs through the shared governed-command kernel against real tables, so the
proposal row, the idempotency receipt, and the authoritative audit event commit
in one transaction or not at all.

Four accountable human moves are supported: propose, approve, reject, withdraw.
Each one:

1. Reads the source of truth from authorized server records. The original text,
   the element, and the source script version come from the item's own bindings;
   a client cannot assert what passage it is rewriting, which version it belongs
   to, or who owns it.
2. Derives capability from the server-provided membership role, never from the
   request, and enforces maker-checker on approval: the proposer may not approve
   their own proposal. The existing capability policy is used unchanged --
   ``rewrite:propose`` to propose, ``rewrite:approve`` to approve or reject -- so
   no new approver role is invented. Withdrawal requires ``rewrite:propose`` and
   is restricted to the proposer, because withdrawing is the maker retracting
   their own suggestion rather than a checker acting on it.
3. Refuses illegal lifecycle moves with a typed error: a repeated approval, an
   approval after a rejection, and a withdrawal after materialization are all
   visible conflicts.
4. Refuses to approve a proposal whose source version is no longer the version
   the item is bound to. A stale proposal describes a passage that has moved on,
   and is surfaced as a conflict -- never silently rebased onto new text.

What approval deliberately does *not* do: it does not create a successor script
version and it does not start research. Materializing an approved rewrite into
the next immutable version, and re-checking the passages it changed, stay behind
the separate explicit ``startSelectiveRescan`` action, so approving can never
spend money on a paid provider. ``resulting_version_id`` is therefore ``None``
until that separate step binds it, and is reported only when present.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from clearcut.commanding.domain import AuditPayload, CommandEnvelope, PriorReceipt
from clearcut.commanding.errors import (
    CommandForbiddenError,
    CommandValidationError,
    StaleVersionConflictError,
)
from clearcut.commanding.sql import insert_authoritative_audit, lookup_command_receipt
from clearcut.commanding.template import (
    GovernedAudit,
    GovernedCommandContext,
    execute_governed_command,
)
from clearcut.decisions.domain.rewrites import (
    RewriteAction,
    RewriteProposal,
    assert_transition,
    result_status,
)
from clearcut.decisions.ports.rewrite_repository import (
    RewriteRepositoryPort,
    RewriteSource,
    ScopedRewriteProposal,
)
from clearcut.organizations.domain.capabilities import has_capability
from sqlalchemy.ext.asyncio import AsyncSession

_PROPOSE_OPERATION = "decision.rewrite.propose"
_PROPOSE_CAPABILITY = "rewrite:propose"
_APPROVE_CAPABILITY = "rewrite:approve"
_AUDIT_TARGET_TYPE = "rewrite_proposal"

_TRANSITION_OPERATION: dict[RewriteAction, str] = {
    RewriteAction.APPROVE: "decision.rewrite.approve",
    RewriteAction.REJECT: "decision.rewrite.reject",
    RewriteAction.WITHDRAW: "decision.rewrite.withdraw",
}

_TRANSITION_CAPABILITY: dict[RewriteAction, str] = {
    # Approving and rejecting are both checker moves on someone's suggestion, so
    # both use the existing rewrite:approve capability. Withdrawal is the maker
    # retracting their own proposal.
    RewriteAction.APPROVE: _APPROVE_CAPABILITY,
    RewriteAction.REJECT: _APPROVE_CAPABILITY,
    RewriteAction.WITHDRAW: _PROPOSE_CAPABILITY,
}

_TRANSITION_AUDIT_ACTION: dict[RewriteAction, str] = {
    RewriteAction.APPROVE: "rewrite.approved",
    RewriteAction.REJECT: "rewrite.rejected",
    RewriteAction.WITHDRAW: "rewrite.withdrawn",
}


def _intent_hash(*parts: str) -> str:
    """Derive the governed intent hash from the command's own meaning.

    The canonical contract for these operations carries no client-supplied intent
    hash, so the server derives one from the operation and its inputs. Two
    requests that mean the same thing under one idempotency key replay; two that
    mean different things collide as an intent conflict.
    """
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ProposeRewriteCommand:
    """A validated request to propose one rewrite on a scoped clearance item.

    ``actor_role`` and ``actor_email`` are server-derived from the authenticated
    session, never from the request body. There is no ``original_text``,
    ``element_id``, or ``source_version_id`` field: those are read from the item.
    """

    org_id: UUID
    project_id: UUID
    item_id: UUID
    actor_id: UUID
    actor_role: str
    actor_email: str
    proposed_text: str
    rationale: str
    idempotency_key: str


@dataclass(frozen=True)
class RewriteTransitionCommand:
    """A validated request to approve, reject, or withdraw one proposal."""

    org_id: UUID
    project_id: UUID
    proposal_id: UUID
    actor_id: UUID
    actor_role: str
    action: RewriteAction
    rationale: str | None
    idempotency_key: str


class RewriteCommandService:
    """Coordinates one governed rewrite-lifecycle command per transaction."""

    def __init__(self, repository: RewriteRepositoryPort) -> None:
        self._repository = repository

    async def list_proposals(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        actor_role: str,
    ) -> tuple[ScopedRewriteProposal, ...]:
        """Return the item's rewrite proposals for an authorized reader.

        Reading requires the same ``project:read`` capability every project
        surface requires; the scoped query is what keeps another tenant's
        proposals invisible.
        """
        if not has_capability(actor_role, "project:read"):
            raise CommandForbiddenError()
        return await self._repository.list_proposals(
            session,
            org_id=org_id,
            project_id=project_id,
            item_id=item_id,
        )

    async def propose(
        self,
        session: AsyncSession,
        command: ProposeRewriteCommand,
    ) -> ScopedRewriteProposal:
        proposed_text = command.proposed_text.strip()
        if not proposed_text:
            raise CommandValidationError("A non-empty proposed replacement is required.")

        # The source read is the not-found parity gate and the origin of every
        # piece of provenance this proposal will carry. It also supplies the
        # expected version, because the canonical operation has no client-supplied
        # one; the version-guarded write is what makes that safe.
        source = await self._repository.load_rewrite_source(
            session,
            org_id=command.org_id,
            project_id=command.project_id,
            item_id=command.item_id,
        )

        envelope = CommandEnvelope(
            org_id=command.org_id,
            project_id=command.project_id,
            actor_id=command.actor_id,
            operation=_PROPOSE_OPERATION,
            idempotency_key=command.idempotency_key,
            intent_hash=_intent_hash(
                _PROPOSE_OPERATION,
                str(command.item_id),
                str(source.source_version_id),
                proposed_text,
                command.rationale.strip(),
            ),
            expected_version=source.item_version,
        )

        async def load_item(
            _session: AsyncSession,
            _envelope: CommandEnvelope,
        ) -> RewriteSource:
            return source

        def check_capability() -> None:
            if not has_capability(command.actor_role, _PROPOSE_CAPABILITY):
                raise CommandForbiddenError()

        def validate_domain(item: RewriteSource) -> None:
            if proposed_text == item.original_text.strip():
                raise CommandValidationError(
                    "The proposed replacement is identical to the original passage."
                )

        async def lookup_receipt(
            session: AsyncSession,
            envelope: CommandEnvelope,
        ) -> PriorReceipt | None:
            return await lookup_command_receipt(session, envelope)

        def build_proposal(context: GovernedCommandContext[RewriteSource]) -> RewriteProposal:
            # The committed result identity is the proposal id, so a replay can
            # reproduce the exact proposal from its receipt.
            return RewriteProposal.create(
                proposal_id=context.result_id,
                org_id=command.org_id,
                project_id=command.project_id,
                item_id=command.item_id,
                source_version_id=context.item.source_version_id,
                proposer_id=command.actor_id,
                element_id=context.item.element_id,
                original_text=context.item.original_text,
                proposed_text=proposed_text,
                rationale=command.rationale,
                occurred_at=context.occurred_at,
            )

        async def commit_provisional(
            session: AsyncSession,
            context: GovernedCommandContext[RewriteSource],
        ) -> None:
            await self._repository.insert_proposal(
                session,
                proposal=build_proposal(context),
                expected_version=context.item.item_version,
                resulting_version=context.resulting_version,
            )

        async def persist_receipt(
            session: AsyncSession,
            envelope: CommandEnvelope,
            context: GovernedCommandContext[RewriteSource],
        ) -> PriorReceipt | None:
            return await self._repository.persist_receipt_idempotent(
                session,
                envelope,
                item_id=command.item_id,
                resulting_version=context.resulting_version,
                result_id=context.result_id,
                occurred_at=context.occurred_at,
            )

        def build_audit(context: GovernedCommandContext[RewriteSource]) -> GovernedAudit:
            return GovernedAudit(
                action="rewrite.proposed",
                target_type=_AUDIT_TARGET_TYPE,
                target_id=context.result_id,
                payload=AuditPayload(
                    {
                        "proposalId": str(context.result_id),
                        "itemId": str(command.item_id),
                        "sourceVersionId": str(context.item.source_version_id),
                        "elementId": str(context.item.element_id),
                        "expectedVersion": context.item.item_version,
                        "resultingVersion": context.resulting_version,
                    }
                ),
            )

        async def append_audit(
            session: AsyncSession,
            envelope: CommandEnvelope,
            audit: GovernedAudit,
            correlation_id: UUID,
            occurred_at: datetime,
        ) -> None:
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
            _envelope: CommandEnvelope,
            prior: PriorReceipt,
        ) -> ScopedRewriteProposal:
            # The prior receipt's result id *is* the committed proposal id.
            return await self._repository.load_scoped_proposal(
                session,
                org_id=command.org_id,
                project_id=command.project_id,
                proposal_id=prior.result_id,
            )

        def project_result(
            context: GovernedCommandContext[RewriteSource],
        ) -> ScopedRewriteProposal:
            proposal = build_proposal(context)
            return _project_new_proposal(
                proposal,
                proposer_email=command.actor_email or None,
                item_version=context.resulting_version,
                current_version_id=context.item.current_version_id,
            )

        return await execute_governed_command(
            session,
            envelope,
            load_item=load_item,
            check_capability=check_capability,
            validate_domain=validate_domain,
            current_version=lambda item: item.item_version,
            lookup_receipt=lookup_receipt,
            commit_provisional=commit_provisional,
            persist_receipt=persist_receipt,
            build_audit=build_audit,
            append_audit=append_audit,
            load_replay_result=load_replay_result,
            project_result=project_result,
        )

    async def transition(
        self,
        session: AsyncSession,
        command: RewriteTransitionCommand,
    ) -> ScopedRewriteProposal:
        action = command.action
        rationale = command.rationale.strip() if command.rationale is not None else None

        # Loading first is the not-found parity gate and supplies the item's
        # current version as the governed expected version.
        proposal = await self._repository.load_scoped_proposal(
            session,
            org_id=command.org_id,
            project_id=command.project_id,
            proposal_id=command.proposal_id,
        )
        operation = _TRANSITION_OPERATION[action]

        envelope = CommandEnvelope(
            org_id=command.org_id,
            project_id=command.project_id,
            actor_id=command.actor_id,
            operation=operation,
            idempotency_key=command.idempotency_key,
            intent_hash=_intent_hash(operation, str(command.proposal_id), rationale or ""),
            expected_version=proposal.item_version,
        )
        next_status = result_status(action)

        # Whether this exact command already committed once decides the outcome
        # before the state machine does. A retry of a committed approval is a
        # replay of that approval, not a second attempt at an approved proposal;
        # without this the lifecycle guard would turn every safe retry into a
        # conflict. The kernel's own classification below still separates a
        # matching-intent replay from a reused key with a different intent.
        already_committed = await lookup_command_receipt(session, envelope) is not None

        async def load_item(
            _session: AsyncSession,
            _envelope: CommandEnvelope,
        ) -> ScopedRewriteProposal:
            return proposal

        def check_capability() -> None:
            if not has_capability(command.actor_role, _TRANSITION_CAPABILITY[action]):
                raise CommandForbiddenError()
            if action is RewriteAction.APPROVE and proposal.proposer_id == command.actor_id:
                # Maker-checker: authority to change the script cannot be
                # self-granted, whatever the actor's role is.
                raise CommandForbiddenError(
                    "The proposer of a rewrite cannot approve their own proposal."
                )
            if action is RewriteAction.WITHDRAW and proposal.proposer_id != command.actor_id:
                raise CommandForbiddenError("Only the proposer of a rewrite can withdraw it.")

        def validate_domain(item: ScopedRewriteProposal) -> None:
            if already_committed:
                # A prior receipt owns this outcome; the kernel replays it.
                return
            # A closed state machine: an illegal move raises the typed
            # RewriteTransitionError, which the delivery boundary reports as a
            # lifecycle conflict rather than absorbing as a silent no-op.
            assert_transition(item.status, action)
            if (
                action is RewriteAction.APPROVE
                and item.source_version_id != item.current_version_id
            ):
                # The project has committed a newer script version since this
                # rewrite was written, so the passage was reviewed against
                # surroundings that no longer exist. Rebasing it silently would
                # approve text nobody reviewed.
                raise StaleVersionConflictError(
                    "This rewrite was proposed against an earlier script version; "
                    "re-propose it against the current version."
                )

        async def lookup_receipt(
            session: AsyncSession,
            envelope: CommandEnvelope,
        ) -> PriorReceipt | None:
            return await lookup_command_receipt(session, envelope)

        async def commit_provisional(
            session: AsyncSession,
            context: GovernedCommandContext[ScopedRewriteProposal],
        ) -> None:
            await self._repository.apply_transition(
                session,
                proposal_id=command.proposal_id,
                org_id=command.org_id,
                project_id=command.project_id,
                item_id=context.item.item_id,
                from_status=context.item.status,
                to_status=next_status,
                approver_id=(command.actor_id if action is not RewriteAction.WITHDRAW else None),
                rejection_reason=(rationale if action is RewriteAction.REJECT else None),
                expected_version=context.item.item_version,
                resulting_version=context.resulting_version,
                occurred_at=context.occurred_at,
            )

        async def persist_receipt(
            session: AsyncSession,
            envelope: CommandEnvelope,
            context: GovernedCommandContext[ScopedRewriteProposal],
        ) -> PriorReceipt | None:
            return await self._repository.persist_receipt_idempotent(
                session,
                envelope,
                item_id=context.item.item_id,
                resulting_version=context.resulting_version,
                result_id=context.result_id,
                occurred_at=context.occurred_at,
            )

        def build_audit(
            context: GovernedCommandContext[ScopedRewriteProposal],
        ) -> GovernedAudit:
            return GovernedAudit(
                action=_TRANSITION_AUDIT_ACTION[action],
                target_type=_AUDIT_TARGET_TYPE,
                target_id=command.proposal_id,
                payload=AuditPayload(
                    {
                        "proposalId": str(command.proposal_id),
                        "itemId": str(context.item.item_id),
                        "sourceVersionId": str(context.item.source_version_id),
                        "fromStatus": context.item.status.value,
                        "toStatus": next_status.value,
                        "expectedVersion": context.item.item_version,
                        "resultingVersion": context.resulting_version,
                    }
                ),
            )

        async def append_audit(
            session: AsyncSession,
            envelope: CommandEnvelope,
            audit: GovernedAudit,
            correlation_id: UUID,
            occurred_at: datetime,
        ) -> None:
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
            _envelope: CommandEnvelope,
            _prior: PriorReceipt,
        ) -> ScopedRewriteProposal:
            # A transition's committed state lives on the proposal itself, so the
            # replay re-reads the proposal rather than a separate result row.
            return await self._repository.load_scoped_proposal(
                session,
                org_id=command.org_id,
                project_id=command.project_id,
                proposal_id=command.proposal_id,
            )

        def project_result(
            context: GovernedCommandContext[ScopedRewriteProposal],
        ) -> ScopedRewriteProposal:
            return replace(
                context.item,
                status=next_status,
                approver_id=(command.actor_id if action is not RewriteAction.WITHDRAW else None),
                rejection_reason=(rationale if action is RewriteAction.REJECT else None),
                updated_at=context.occurred_at,
                item_version=context.resulting_version,
            )

        return await execute_governed_command(
            session,
            envelope,
            load_item=load_item,
            check_capability=check_capability,
            validate_domain=validate_domain,
            current_version=lambda item: item.item_version,
            lookup_receipt=lookup_receipt,
            commit_provisional=commit_provisional,
            persist_receipt=persist_receipt,
            build_audit=build_audit,
            append_audit=append_audit,
            load_replay_result=load_replay_result,
            project_result=project_result,
        )


def _project_new_proposal(
    proposal: RewriteProposal,
    *,
    proposer_email: str | None,
    item_version: int,
    current_version_id: UUID | None,
) -> ScopedRewriteProposal:
    return ScopedRewriteProposal(
        proposal_id=proposal.proposal_id,
        org_id=proposal.org_id,
        project_id=proposal.project_id,
        item_id=proposal.item_id,
        source_version_id=proposal.source_version_id,
        element_id=proposal.element_id,
        proposer_id=proposal.proposer_id,
        proposer_email=proposer_email,
        original_text=proposal.original_text,
        proposed_text=proposal.proposed_text,
        rationale=proposal.rationale,
        status=proposal.status,
        approver_id=proposal.approver_id,
        rejection_reason=proposal.rejection_reason,
        resulting_version_id=proposal.resulting_version_id,
        created_at=proposal.created_at,
        updated_at=proposal.updated_at,
        item_version=item_version,
        current_version_id=current_version_id,
    )


__all__ = [
    "ProposeRewriteCommand",
    "RewriteCommandService",
    "RewriteTransitionCommand",
]

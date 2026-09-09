"""Governed promotion and rollback for bounded learning candidates.

A learning candidate changes only query phrasing, retrieval/category examples, a
prompt refinement, or an organization preference. Moving one to ``promoted`` or
``rolled_back`` is a governed mutation with an accountable human trigger, so both
operations run through the shared command kernel
(:func:`~clearcut.commanding.template.execute_governed_command`): the stage
change and the immutable authoritative audit event commit in one transaction, and
the candidate's ``version`` column is the optimistic-concurrency guard.

What this service refuses, and why:

* **Not an Owner.** Promotion and rollback require ``governance:manage``, derived
  from the server-provided membership role, never from the client.
* **Protected scope.** A candidate whose declared scope or ``target_scope`` is one
  of the eight human-only scopes can never be promoted. This is the point of the
  feature: the loop touches nothing else -- no permissions, no rules, no
  categories.
* **Gates not met.** Promotion requires a fully passing regression suite (at
  least one case) and a canary pass rate at or above the threshold.
* **Illegal stage move.** Promotion is only reachable from ``canary``; rollback
  only from ``canary`` or ``promoted``. Anything else is a typed refusal, never a
  silent no-op.

Rollback is deliberately ungated beyond capability and the stage machine:
withdrawing a change must never depend on the evidence that justified it.

Every outcome crosses the boundary as a typed
:class:`LearningStageChange` or a typed governed-command error. Nothing returns a
bare ``bool``, and no stdlib ``PermissionError``/``ValueError`` escapes.

**Idempotency receipts.** The kernel's receipt table is project-scoped (it
carries a non-null ``project_id`` and a foreign key to a clearance item), so an
organization-owned learning candidate has no row it can legitimately write there,
and the schema offers no org-level receipt table. Rather than fabricate a project
id, the receipt seams below record typed absence, and duplicate protection comes
from two other guarantees that are sufficient for these operations: the stage
machine rejects a second promote or rollback outright, and the version-guarded
compare-and-swap turns a concurrent duplicate into a typed stale-version
conflict. Neither operation is additive, so a retry can never produce a second
change or a second audit event. This is a bounded, documented gap, not a silent
one.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from clearcut.commanding.domain import AuditPayload, CommandEnvelope, PriorReceipt
from clearcut.commanding.errors import CommandForbiddenError
from clearcut.commanding.template import (
    GovernedAudit,
    GovernedCommandContext,
    execute_governed_command,
)
from clearcut.evaluation.domain.learning import (
    LearningCandidate,
    LearningStage,
    assert_transition_allowed,
)
from clearcut.evaluation.ports.learning_repository import LearningRepositoryPort
from clearcut.organizations.domain.capabilities import has_capability
from sqlalchemy.ext.asyncio import AsyncSession

_PROMOTE_OPERATION = "learning.candidate.promote"
_ROLLBACK_OPERATION = "learning.candidate.rollback"
_GOVERNANCE_CAPABILITY = "governance:manage"
_AUDIT_TARGET_TYPE = "learning_candidate"
_PROMOTE_ACTION = "learning.candidate.promoted"
_ROLLBACK_ACTION = "learning.candidate.rolled_back"

# A learning candidate is organization-owned and belongs to no project, but the
# kernel envelope is project-shaped. This nil sentinel makes the absence explicit
# and is never persisted: the receipt seams record typed absence, and the audit
# adapter writes a null project_id.
_NO_PROJECT = UUID(int=0)


@dataclass(frozen=True)
class LearningStageChange:
    """The committed result of one governed stage change."""

    candidate_id: UUID
    stage: LearningStage
    version: int


@dataclass(frozen=True)
class PromoteLearningCandidateCommand:
    """A validated request to promote one candidate.

    ``actor_role`` is the server-derived membership role. ``expected_version`` is
    optional because the contract operation carries no request body: when a
    caller supplies it, it is enforced as an optimistic-concurrency guard; when
    it is omitted, the version loaded in this transaction is used and the
    compare-and-swap still rejects any concurrent interleaving.
    """

    org_id: UUID
    candidate_id: UUID
    actor_id: UUID
    actor_role: str
    expected_version: int | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True)
class RollbackLearningCandidateCommand:
    """A validated request to roll one candidate back."""

    org_id: UUID
    candidate_id: UUID
    actor_id: UUID
    actor_role: str
    reason: str | None = None
    expected_version: int | None = None
    idempotency_key: str | None = None


class LearningPipelineService:
    """Coordinates governed learning-candidate stage changes."""

    def __init__(self, repository: LearningRepositoryPort) -> None:
        self._repository = repository

    async def promote(
        self,
        session: AsyncSession,
        command: PromoteLearningCandidateCommand,
    ) -> LearningStageChange:
        """Promote the candidate, or raise a typed refusal.

        The protected-scope boundary and the regression/canary gates are enforced
        by the domain inside the transaction, so a refusal leaves no partial
        write and no audit event claiming a promotion that did not happen.
        """
        return await self._execute(
            session,
            org_id=command.org_id,
            candidate_id=command.candidate_id,
            actor_id=command.actor_id,
            actor_role=command.actor_role,
            operation=_PROMOTE_OPERATION,
            target_stage=LearningStage.PROMOTED,
            audit_action=_PROMOTE_ACTION,
            expected_version=command.expected_version,
            idempotency_key=command.idempotency_key,
            reason=None,
        )

    async def rollback(
        self,
        session: AsyncSession,
        command: RollbackLearningCandidateCommand,
    ) -> LearningStageChange:
        """Roll the candidate back from canary or promoted, recording who did it."""
        return await self._execute(
            session,
            org_id=command.org_id,
            candidate_id=command.candidate_id,
            actor_id=command.actor_id,
            actor_role=command.actor_role,
            operation=_ROLLBACK_OPERATION,
            target_stage=LearningStage.ROLLED_BACK,
            audit_action=_ROLLBACK_ACTION,
            expected_version=command.expected_version,
            idempotency_key=command.idempotency_key,
            reason=command.reason,
        )

    async def _execute(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        candidate_id: UUID,
        actor_id: UUID,
        actor_role: str,
        operation: str,
        target_stage: LearningStage,
        audit_action: str,
        expected_version: int | None,
        idempotency_key: str | None,
        reason: str | None,
    ) -> LearningStageChange:
        # Resolve the concurrency baseline first. A candidate that is not visible
        # in this organization is a neutral not-found before anything else is
        # considered, matching the kernel's load-then-capability ordering.
        loaded = await self._repository.load_candidate(
            session,
            org_id=org_id,
            candidate_id=candidate_id,
        )
        resolved_version = expected_version if expected_version is not None else loaded.version

        envelope = CommandEnvelope(
            org_id=org_id,
            project_id=_NO_PROJECT,
            actor_id=actor_id,
            operation=operation,
            idempotency_key=idempotency_key
            or _derived_idempotency_key(operation, candidate_id, resolved_version),
            intent_hash=_intent_hash(
                operation,
                candidate_id,
                target_stage,
                actor_id,
                resolved_version,
                reason,
            ),
            expected_version=resolved_version,
        )

        async def load_item(
            session: AsyncSession,
            envelope: CommandEnvelope,
        ) -> LearningCandidate:
            return await self._repository.load_candidate(
                session,
                org_id=org_id,
                candidate_id=candidate_id,
            )

        def check_capability() -> None:
            # Owner-only. Capability is derived from the server-provided role.
            if not has_capability(actor_role, _GOVERNANCE_CAPABILITY):
                raise CommandForbiddenError(
                    "Only an organization Owner may promote or roll back a learning candidate."
                )

        def validate_domain(candidate: LearningCandidate) -> None:
            # Protected-scope boundary and, for promotion, the evaluation gates,
            # then the stage machine. Raising here happens before any write is
            # attempted, so an illegal move leaves no trace and no audit event.
            if target_stage is LearningStage.PROMOTED:
                candidate.assert_bounded()
                candidate.assert_regression_gate()
            assert_transition_allowed(candidate.stage, target_stage)

        async def lookup_receipt(
            session: AsyncSession,
            envelope: CommandEnvelope,
        ) -> PriorReceipt | None:
            # See the module docstring: there is no organization-scoped receipt
            # table, so absence is the truthful answer. Duplicate protection comes
            # from the stage machine and the version-guarded compare-and-swap.
            return None

        async def commit_provisional(
            session: AsyncSession,
            context: GovernedCommandContext[LearningCandidate],
        ) -> None:
            next_state = _next_state(
                context.item,
                target_stage=target_stage,
                actor_id=actor_id,
                occurred_at=context.occurred_at,
                resulting_version=context.resulting_version,
                reason=reason,
            )
            await self._repository.commit_stage_change(
                session,
                candidate=next_state,
                expected_version=context.item.version,
            )

        async def persist_receipt(
            session: AsyncSession,
            envelope: CommandEnvelope,
            context: GovernedCommandContext[LearningCandidate],
        ) -> PriorReceipt | None:
            # No org-scoped receipt row to write; typed absence tells the kernel
            # there was no concurrent duplicate to reconcile.
            return None

        def build_audit(
            context: GovernedCommandContext[LearningCandidate],
        ) -> GovernedAudit:
            payload: dict[str, object] = {
                "fromStage": context.item.stage.value,
                "toStage": target_stage.value,
                "scope": context.item.scope.value,
                "targetScope": _target_scope(context.item),
                "canaryPassRate": context.item.canary_pass_rate,
                "regressionCasesPassed": context.item.regression_cases_passed,
                "regressionCasesTotal": context.item.regression_cases_total,
                "expectedVersion": context.item.version,
                "resultingVersion": context.resulting_version,
            }
            if reason is not None:
                payload["reason"] = reason
            return GovernedAudit(
                action=audit_action,
                target_type=_AUDIT_TARGET_TYPE,
                target_id=candidate_id,
                payload=AuditPayload(payload),
            )

        async def append_audit(
            session: AsyncSession,
            envelope: CommandEnvelope,
            audit: GovernedAudit,
            correlation_id: UUID,
            occurred_at: datetime,
        ) -> None:
            await self._repository.append_org_audit(
                session,
                org_id=org_id,
                actor_id=actor_id,
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
        ) -> LearningStageChange:
            # Unreachable while lookup_receipt reports absence; kept typed so the
            # seam stays correct if an org-scoped receipt table is introduced.
            candidate = await self._repository.load_candidate(
                session,
                org_id=org_id,
                candidate_id=candidate_id,
            )
            return LearningStageChange(
                candidate_id=candidate.candidate_id,
                stage=candidate.stage,
                version=candidate.version,
            )

        def project_result(
            context: GovernedCommandContext[LearningCandidate],
        ) -> LearningStageChange:
            return LearningStageChange(
                candidate_id=candidate_id,
                stage=target_stage,
                version=context.resulting_version,
            )

        return await execute_governed_command(
            session,
            envelope,
            load_item=load_item,
            check_capability=check_capability,
            validate_domain=validate_domain,
            current_version=lambda candidate: candidate.version,
            lookup_receipt=lookup_receipt,
            commit_provisional=commit_provisional,
            persist_receipt=persist_receipt,
            build_audit=build_audit,
            append_audit=append_audit,
            load_replay_result=load_replay_result,
            project_result=project_result,
        )


def _next_state(
    candidate: LearningCandidate,
    *,
    target_stage: LearningStage,
    actor_id: UUID,
    occurred_at: datetime,
    resulting_version: int,
    reason: str | None,
) -> LearningCandidate:
    """Apply the stage change in the domain, which owns every refusal."""
    if target_stage is LearningStage.PROMOTED:
        return candidate.promoted(
            actor_id=actor_id,
            occurred_at=occurred_at,
            resulting_version=resulting_version,
        )
    return candidate.rolled_back(
        actor_id=actor_id,
        occurred_at=occurred_at,
        resulting_version=resulting_version,
        reason=reason,
    )


def _target_scope(candidate: LearningCandidate) -> str:
    """The bounded scope this candidate changes, for the audit payload."""
    target = candidate.proposed_changes.get("target_scope")
    return str(target) if target is not None else candidate.scope.value


def _intent_hash(
    operation: str,
    candidate_id: UUID,
    target_stage: LearningStage,
    actor_id: UUID,
    expected_version: int,
    reason: str | None,
) -> str:
    """Derive the kernel's intent hash from the governed request's own inputs.

    The contract operations carry no client-supplied intent hash, so it is
    derived here from exactly the fields that define the intent. Two requests
    that mean the same thing hash the same; a different target stage, actor,
    version, or reason does not.
    """
    material = "|".join(
        (
            operation,
            str(candidate_id),
            target_stage.value,
            str(actor_id),
            str(expected_version),
            reason or "",
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _derived_idempotency_key(operation: str, candidate_id: UUID, expected_version: int) -> str:
    """A deterministic key for callers that send no ``Idempotency-Key`` header."""
    return f"{operation}:{candidate_id}:{expected_version}"


__all__ = [
    "LearningPipelineService",
    "LearningStageChange",
    "PromoteLearningCandidateCommand",
    "RollbackLearningCandidateCommand",
]

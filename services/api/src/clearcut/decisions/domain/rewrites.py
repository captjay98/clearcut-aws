"""Domain model and state machine for governed rewrite proposals.

A rewrite proposal is an accountable human suggestion to replace one passage of
an immutable script version. It is never applied silently: the lifecycle is a
closed state machine whose transitions are the only legal moves, and every move
is refused with a typed :class:`RewriteTransitionError` when the proposal is not
in a state that permits it. That is what makes a repeated approval, an
approval after a rejection, or a withdrawal after materialization a visible
conflict rather than a silently absorbed no-op.

``created_at`` and ``updated_at`` are required constructor inputs. They used to
carry ``datetime.now(UTC)`` defaults evaluated once at class-definition time, so
every proposal built without them shared the process-start instant; a timestamp
that lies about when a governed decision happened is worse than no default.

Materialization -- binding an approved proposal to the successor script version
it produced -- is a separate accountable step that also drives the explicit
``startSelectiveRescan`` action. Approval alone never creates a version and
never triggers paid research, so ``resulting_version_id`` stays ``None`` until
that step binds it.
"""

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID

import uuid6


class RewriteProposalStatus(StrEnum):
    DRAFT = "draft"
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    MATERIALIZED = "materialized"
    SUPERSEDED = "superseded"


class RewriteAction(StrEnum):
    """The governed lifecycle moves a human can trigger on a proposal."""

    APPROVE = "approve"
    REJECT = "reject"
    WITHDRAW = "withdraw"


# The closed transition table. A move that is not listed here for the current
# status is refused; there is no permissive default.
_ALLOWED_SOURCE_STATUSES: dict[RewriteAction, frozenset[RewriteProposalStatus]] = {
    RewriteAction.APPROVE: frozenset({RewriteProposalStatus.PROPOSED}),
    RewriteAction.REJECT: frozenset({RewriteProposalStatus.PROPOSED}),
    RewriteAction.WITHDRAW: frozenset({RewriteProposalStatus.PROPOSED}),
}

_RESULT_STATUS: dict[RewriteAction, RewriteProposalStatus] = {
    RewriteAction.APPROVE: RewriteProposalStatus.APPROVED,
    RewriteAction.REJECT: RewriteProposalStatus.REJECTED,
    RewriteAction.WITHDRAW: RewriteProposalStatus.WITHDRAWN,
}


class RewriteTransitionError(RuntimeError):
    """An attempted lifecycle move is not legal from the proposal's status.

    Carries the current status and the attempted action so the delivery boundary
    can explain the refusal without echoing any proposal content.
    """

    def __init__(self, *, current: RewriteProposalStatus, action: RewriteAction) -> None:
        self.current = current
        self.action = action
        self.message = (
            f"A rewrite proposal that is already {current.value} cannot be {action.value}d."
        )
        super().__init__(self.message)


def result_status(action: RewriteAction) -> RewriteProposalStatus:
    """Return the status a legal ``action`` moves a proposal into."""
    return _RESULT_STATUS[action]


def assert_transition(status: RewriteProposalStatus, action: RewriteAction) -> None:
    """Raise :class:`RewriteTransitionError` when ``action`` is illegal from ``status``.

    Exposed as a free function so a caller that has loaded a proposal's status
    from storage can check legality without rebuilding the whole aggregate.
    """
    if status not in _ALLOWED_SOURCE_STATUSES[action]:
        raise RewriteTransitionError(current=status, action=action)


@dataclass(frozen=True)
class RewriteProposal:
    proposal_id: UUID
    org_id: UUID
    project_id: UUID
    item_id: UUID
    source_version_id: UUID
    proposer_id: UUID
    element_id: UUID
    original_text: str
    proposed_text: str
    rationale: str
    status: RewriteProposalStatus
    created_at: datetime
    updated_at: datetime
    approver_id: UUID | None = None
    rejection_reason: str | None = None
    resulting_version_id: UUID | None = None

    @classmethod
    def create(
        cls,
        *,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        source_version_id: UUID,
        proposer_id: UUID,
        element_id: UUID,
        original_text: str,
        proposed_text: str,
        rationale: str,
        occurred_at: datetime,
        proposal_id: UUID | None = None,
    ) -> "RewriteProposal":
        """Build a freshly proposed rewrite.

        ``original_text``, ``element_id``, and ``source_version_id`` are always
        the server's own reading of the authorized record; this constructor is
        never handed client-supplied provenance.
        """
        return cls(
            proposal_id=proposal_id if proposal_id is not None else uuid6.uuid7(),
            org_id=org_id,
            project_id=project_id,
            item_id=item_id,
            source_version_id=source_version_id,
            proposer_id=proposer_id,
            element_id=element_id,
            original_text=original_text.strip(),
            proposed_text=proposed_text.strip(),
            rationale=rationale.strip(),
            status=RewriteProposalStatus.PROPOSED,
            created_at=occurred_at,
            updated_at=occurred_at,
        )

    def assert_can(self, action: RewriteAction) -> None:
        """Raise :class:`RewriteTransitionError` when ``action`` is not legal now."""
        assert_transition(self.status, action)

    def approve(self, approver_id: UUID, occurred_at: datetime) -> "RewriteProposal":
        self.assert_can(RewriteAction.APPROVE)
        return replace(
            self,
            status=RewriteProposalStatus.APPROVED,
            approver_id=approver_id,
            rejection_reason=None,
            updated_at=occurred_at,
        )

    def reject(
        self,
        rejecter_id: UUID,
        occurred_at: datetime,
        reason: str | None = None,
    ) -> "RewriteProposal":
        self.assert_can(RewriteAction.REJECT)
        return replace(
            self,
            status=RewriteProposalStatus.REJECTED,
            approver_id=rejecter_id,
            rejection_reason=reason.strip() if reason is not None else None,
            updated_at=occurred_at,
        )

    def withdraw(self, occurred_at: datetime) -> "RewriteProposal":
        self.assert_can(RewriteAction.WITHDRAW)
        return replace(
            self,
            status=RewriteProposalStatus.WITHDRAWN,
            approver_id=None,
            rejection_reason=None,
            updated_at=occurred_at,
        )


__all__ = [
    "RewriteAction",
    "RewriteProposal",
    "RewriteProposalStatus",
    "RewriteTransitionError",
    "assert_transition",
    "result_status",
]

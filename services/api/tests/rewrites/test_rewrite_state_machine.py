"""The rewrite lifecycle is a closed state machine, not a set of setters.

These are the pure-domain half of the rewrite tests: no storage, no HTTP. They
pin that every illegal move raises a typed
:class:`~clearcut.decisions.domain.rewrites.RewriteTransitionError` rather than
being absorbed, which is what makes a repeated approval a visible conflict at
the API boundary rather than a second silent success.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import uuid6
from clearcut.decisions.domain.rewrites import (
    RewriteAction,
    RewriteProposal,
    RewriteProposalStatus,
    RewriteTransitionError,
    assert_transition,
)

_NOW = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)


def _proposal(status: RewriteProposalStatus = RewriteProposalStatus.PROPOSED) -> RewriteProposal:
    return RewriteProposal(
        proposal_id=uuid6.uuid7(),
        org_id=uuid6.uuid7(),
        project_id=uuid6.uuid7(),
        item_id=uuid6.uuid7(),
        source_version_id=uuid6.uuid7(),
        proposer_id=uuid6.uuid7(),
        element_id=uuid6.uuid7(),
        original_text="Acme Corporation",
        proposed_text="Novus Corporation",
        rationale="Replace the identifiable mark.",
        status=status,
        created_at=_NOW,
        updated_at=_NOW,
    )


def test_create_records_the_supplied_instant_rather_than_a_class_default() -> None:
    """Timestamps must come from the command, not from module import time.

    The previous model defaulted ``created_at``/``updated_at`` to
    ``datetime.now(UTC)`` evaluated once when the class was defined, so every
    proposal built without them claimed the process-start instant.
    """
    first = RewriteProposal.create(
        org_id=uuid6.uuid7(),
        project_id=uuid6.uuid7(),
        item_id=uuid6.uuid7(),
        source_version_id=uuid6.uuid7(),
        proposer_id=uuid6.uuid7(),
        element_id=uuid6.uuid7(),
        original_text="  Acme Corporation  ",
        proposed_text="  Novus Corporation  ",
        rationale="  Replace the mark.  ",
        occurred_at=_NOW,
    )
    second = RewriteProposal.create(
        org_id=uuid6.uuid7(),
        project_id=uuid6.uuid7(),
        item_id=uuid6.uuid7(),
        source_version_id=uuid6.uuid7(),
        proposer_id=uuid6.uuid7(),
        element_id=uuid6.uuid7(),
        original_text="Acme Corporation",
        proposed_text="Novus Corporation",
        rationale="Replace the mark.",
        occurred_at=_NOW + timedelta(minutes=5),
    )

    assert first.created_at == _NOW
    assert first.updated_at == _NOW
    assert second.created_at == _NOW + timedelta(minutes=5)
    assert first.status is RewriteProposalStatus.PROPOSED
    # Text is normalized once, at the boundary.
    assert first.original_text == "Acme Corporation"
    assert first.proposed_text == "Novus Corporation"
    assert first.rationale == "Replace the mark."


def test_each_legal_move_is_allowed_exactly_once_from_proposed() -> None:
    approved = _proposal().approve(approver_id=uuid6.uuid7(), occurred_at=_NOW)
    rejected = _proposal().reject(
        rejecter_id=uuid6.uuid7(), occurred_at=_NOW, reason="Not a clean substitution."
    )
    withdrawn = _proposal().withdraw(occurred_at=_NOW)

    assert approved.status is RewriteProposalStatus.APPROVED
    assert approved.approver_id is not None
    assert rejected.status is RewriteProposalStatus.REJECTED
    assert rejected.rejection_reason == "Not a clean substitution."
    assert withdrawn.status is RewriteProposalStatus.WITHDRAWN
    # Withdrawal is the maker retracting, so it names no checker.
    assert withdrawn.approver_id is None
    # No move creates a resulting version: materialization is a separate step.
    assert (approved.resulting_version_id, rejected.resulting_version_id) == (None, None)


@pytest.mark.parametrize(
    ("status", "action"),
    [
        (RewriteProposalStatus.APPROVED, RewriteAction.APPROVE),
        (RewriteProposalStatus.REJECTED, RewriteAction.APPROVE),
        (RewriteProposalStatus.WITHDRAWN, RewriteAction.APPROVE),
        (RewriteProposalStatus.MATERIALIZED, RewriteAction.APPROVE),
        (RewriteProposalStatus.APPROVED, RewriteAction.REJECT),
        (RewriteProposalStatus.REJECTED, RewriteAction.REJECT),
        (RewriteProposalStatus.MATERIALIZED, RewriteAction.WITHDRAW),
        (RewriteProposalStatus.APPROVED, RewriteAction.WITHDRAW),
        (RewriteProposalStatus.WITHDRAWN, RewriteAction.WITHDRAW),
        (RewriteProposalStatus.SUPERSEDED, RewriteAction.APPROVE),
        (RewriteProposalStatus.DRAFT, RewriteAction.APPROVE),
    ],
)
def test_illegal_moves_raise_a_typed_transition_error(
    status: RewriteProposalStatus,
    action: RewriteAction,
) -> None:
    with pytest.raises(RewriteTransitionError) as raised:
        assert_transition(status, action)

    assert raised.value.current is status
    assert raised.value.action is action
    # The message explains the refusal without echoing any proposal content.
    assert status.value in raised.value.message
    assert "Acme" not in raised.value.message


def test_aggregate_methods_refuse_the_same_illegal_moves() -> None:
    approved = _proposal(RewriteProposalStatus.APPROVED)
    with pytest.raises(RewriteTransitionError):
        approved.approve(approver_id=uuid6.uuid7(), occurred_at=_NOW)
    with pytest.raises(RewriteTransitionError):
        approved.withdraw(occurred_at=_NOW)
    with pytest.raises(RewriteTransitionError):
        _proposal(RewriteProposalStatus.REJECTED).approve(
            approver_id=uuid6.uuid7(), occurred_at=_NOW
        )

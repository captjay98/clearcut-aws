"""A learning candidate can never reach a human-only protected scope.

Updated for the typed lifecycle: the boundary is enforced in the domain and
raises a typed forbidden error, so every caller (service, route, background
worker) inherits the same refusal instead of relying on a stdlib ``ValueError``
raised by one service method.
"""

from datetime import UTC, datetime

import pytest
import uuid6
from clearcut.evaluation.domain.learning import (
    PROTECTED_SCOPES,
    LearningCandidate,
    LearningScope,
    LearningStage,
    ProtectedScopeViolationError,
    UnboundedLearningScopeError,
)


def _canary_candidate(proposed_changes: dict[str, object]) -> LearningCandidate:
    return LearningCandidate(
        candidate_id=uuid6.uuid7(),
        org_id=uuid6.uuid7(),
        scope=LearningScope.PROMPT_REFINEMENT,
        proposed_changes=proposed_changes,
        canary_pass_rate=0.99,
        stage=LearningStage.CANARY,
        regression_cases_passed=10,
        regression_cases_total=10,
    )


@pytest.mark.parametrize("protected_scope", sorted(PROTECTED_SCOPES))
def test_learning_candidate_cannot_touch_protected_scopes(protected_scope: str) -> None:
    candidate = _canary_candidate({"target_scope": protected_scope, "diff": "remove disclaimers"})

    with pytest.raises(ProtectedScopeViolationError, match=protected_scope):
        candidate.assert_bounded()

    # The refusal holds on the promotion path itself, not just the check.
    with pytest.raises(ProtectedScopeViolationError):
        candidate.promoted(
            actor_id=uuid6.uuid7(),
            occurred_at=datetime.now(UTC),
            resulting_version=2,
        )


def test_an_unrecognized_target_scope_is_refused_as_unbounded() -> None:
    candidate = _canary_candidate({"target_scope": "detection_thresholds"})

    with pytest.raises(UnboundedLearningScopeError):
        candidate.assert_bounded()


def test_a_bounded_target_scope_is_accepted() -> None:
    candidate = _canary_candidate(
        {"target_scope": LearningScope.QUERY_PHRASING.value, "diff": "add 'registered status'"}
    )

    candidate.assert_bounded()

    promoted = candidate.promoted(
        actor_id=uuid6.uuid7(),
        occurred_at=datetime.now(UTC),
        resulting_version=2,
    )
    assert promoted.stage is LearningStage.PROMOTED

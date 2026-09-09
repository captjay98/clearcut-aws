"""The canary/regression gates and the stage machine, at the domain level.

Updated for the typed lifecycle: a below-threshold candidate is a typed refusal
rather than a ``False`` return, and rollback is a real stage transition that
records an accountable actor rather than the absence of a promotion.
"""

from datetime import UTC, datetime

import pytest
import uuid6
from clearcut.evaluation.domain.learning import (
    CANARY_PASS_RATE_THRESHOLD,
    LearningCandidate,
    LearningScope,
    LearningStage,
    LearningStageTransitionError,
    RegressionGateNotMetError,
)


def _candidate(
    *,
    canary_pass_rate: float,
    stage: LearningStage = LearningStage.CANARY,
    regression_passed: int = 20,
    regression_total: int = 20,
) -> LearningCandidate:
    return LearningCandidate(
        candidate_id=uuid6.uuid7(),
        org_id=uuid6.uuid7(),
        scope=LearningScope.QUERY_PHRASING,
        proposed_changes={
            "target_scope": LearningScope.QUERY_PHRASING.value,
            "keywords": ["registered", "status"],
        },
        canary_pass_rate=canary_pass_rate,
        stage=stage,
        regression_cases_passed=regression_passed,
        regression_cases_total=regression_total,
    )


def test_a_candidate_above_the_canary_threshold_promotes() -> None:
    candidate = _candidate(canary_pass_rate=0.98)
    actor_id = uuid6.uuid7()
    occurred_at = datetime.now(UTC)

    promoted = candidate.promoted(
        actor_id=actor_id,
        occurred_at=occurred_at,
        resulting_version=2,
    )

    assert promoted.stage is LearningStage.PROMOTED
    assert promoted.is_promoted is True
    assert promoted.promoted_by == actor_id
    assert promoted.promoted_at == occurred_at
    assert promoted.version == 2


def test_a_candidate_below_the_canary_threshold_is_refused() -> None:
    candidate = _candidate(canary_pass_rate=0.85)
    assert candidate.canary_pass_rate < CANARY_PASS_RATE_THRESHOLD

    with pytest.raises(RegressionGateNotMetError, match="canary"):
        candidate.promoted(
            actor_id=uuid6.uuid7(),
            occurred_at=datetime.now(UTC),
            resulting_version=2,
        )


def test_a_partially_failing_regression_suite_is_refused() -> None:
    candidate = _candidate(canary_pass_rate=0.99, regression_passed=18, regression_total=20)

    with pytest.raises(RegressionGateNotMetError, match="regression"):
        candidate.promoted(
            actor_id=uuid6.uuid7(),
            occurred_at=datetime.now(UTC),
            resulting_version=2,
        )


def test_a_candidate_with_no_regression_evidence_is_refused() -> None:
    candidate = _candidate(canary_pass_rate=1.0, regression_passed=0, regression_total=0)

    with pytest.raises(RegressionGateNotMetError):
        candidate.promoted(
            actor_id=uuid6.uuid7(),
            occurred_at=datetime.now(UTC),
            resulting_version=2,
        )


def test_rollback_from_canary_needs_no_gate_and_records_the_actor() -> None:
    candidate = _candidate(canary_pass_rate=0.10, regression_passed=0, regression_total=20)
    actor_id = uuid6.uuid7()

    rolled_back = candidate.rolled_back(
        actor_id=actor_id,
        occurred_at=datetime.now(UTC),
        resulting_version=2,
        reason="Weaker retrieval on period scripts.",
    )

    assert rolled_back.stage is LearningStage.ROLLED_BACK
    assert rolled_back.is_promoted is False
    assert rolled_back.rolled_back_by == actor_id
    assert rolled_back.rollback_reason == "Weaker retrieval on period scripts."


def test_the_lifecycle_runs_candidate_to_shadow_to_canary_to_promoted() -> None:
    candidate = _candidate(canary_pass_rate=0.99, stage=LearningStage.CANDIDATE)
    occurred_at = datetime.now(UTC)

    shadow = candidate.advanced_to(
        LearningStage.SHADOW, occurred_at=occurred_at, resulting_version=2
    )
    canary = shadow.advanced_to(LearningStage.CANARY, occurred_at=occurred_at, resulting_version=3)
    promoted = canary.promoted(actor_id=uuid6.uuid7(), occurred_at=occurred_at, resulting_version=4)

    assert [shadow.stage, canary.stage, promoted.stage] == [
        LearningStage.SHADOW,
        LearningStage.CANARY,
        LearningStage.PROMOTED,
    ]
    assert canary.canary_started_at == occurred_at


@pytest.mark.parametrize(
    "stage",
    [LearningStage.CANDIDATE, LearningStage.SHADOW, LearningStage.ROLLED_BACK],
)
def test_promotion_is_unreachable_outside_canary(stage: LearningStage) -> None:
    candidate = _candidate(canary_pass_rate=0.99, stage=stage)

    with pytest.raises(LearningStageTransitionError):
        candidate.promoted(
            actor_id=uuid6.uuid7(),
            occurred_at=datetime.now(UTC),
            resulting_version=2,
        )


def test_a_rolled_back_candidate_is_terminal() -> None:
    candidate = _candidate(canary_pass_rate=0.99, stage=LearningStage.ROLLED_BACK)

    with pytest.raises(LearningStageTransitionError):
        candidate.rolled_back(
            actor_id=uuid6.uuid7(),
            occurred_at=datetime.now(UTC),
            resulting_version=2,
        )


def test_created_at_is_stamped_per_instance_not_at_class_definition() -> None:
    # The old dataclass default was evaluated once at import, handing every
    # candidate the process start time. Two candidates built at different moments
    # must not share a timestamp.
    first = LearningCandidate.create(
        org_id=uuid6.uuid7(),
        scope=LearningScope.QUERY_PHRASING,
        proposed_changes={"target_scope": "query_phrasing"},
        canary_pass_rate=0.99,
    )
    second = LearningCandidate.create(
        org_id=uuid6.uuid7(),
        scope=LearningScope.QUERY_PHRASING,
        proposed_changes={"target_scope": "query_phrasing"},
        canary_pass_rate=0.99,
    )

    assert first.created_at != second.created_at
    assert first.created_at.tzinfo is not None
    assert first.stage is LearningStage.CANDIDATE

import uuid6
from clearcut.evaluation.application.learning_pipeline import LearningPipelineService
from clearcut.evaluation.domain.learning import LearningCandidate, LearningScope
from clearcut.organizations.domain.capabilities import Role


def test_canary_threshold_promotes_or_rolls_back():
    service = LearningPipelineService()
    org_id = uuid6.uuid7()

    # Pass rate above threshold (0.95) promotes
    c_good = LearningCandidate.create(
        org_id=org_id,
        scope=LearningScope.QUERY_PHRASING,
        proposed_changes={"domain": "trademark", "keywords": ["registered", "status"]},
        canary_pass_rate=0.98,
    )
    promoted = service.validate_and_promote_candidate(c_good, actor_role=Role.OWNER)
    assert promoted is True

    # Pass rate below threshold rolls back
    c_bad = LearningCandidate.create(
        org_id=org_id,
        scope=LearningScope.QUERY_PHRASING,
        proposed_changes={"domain": "trademark", "keywords": ["bad", "query"]},
        canary_pass_rate=0.85,
    )
    promoted_bad = service.validate_and_promote_candidate(c_bad, actor_role=Role.OWNER)
    assert promoted_bad is False

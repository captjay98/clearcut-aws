import pytest
import uuid6
from clearcut.evaluation.application.learning_pipeline import LearningPipelineService
from clearcut.evaluation.domain.learning import (
    LearningCandidate,
    LearningScope,
)
from clearcut.organizations.domain.capabilities import Role


def test_learning_candidate_cannot_touch_protected_scopes():
    service = LearningPipelineService()
    org_id = uuid6.uuid7()

    # Protected scopes like legal_boundary or permissions must be rejected
    candidate = LearningCandidate.create(
        org_id=org_id,
        scope=LearningScope.PROMPT_REFINEMENT,
        proposed_changes={"target_scope": "legal_boundary", "diff": "remove disclaimers"},
        canary_pass_rate=0.99,
    )

    with pytest.raises(ValueError, match="Protected scope"):
        service.validate_and_promote_candidate(candidate, actor_role=Role.OWNER)

from clearcut.evaluation.domain.learning import (
    PROTECTED_SCOPES,
    LearningCandidate,
)
from clearcut.organizations.domain.capabilities import Role, has_capability


class LearningPipelineService:
    def validate_and_promote_candidate(
        self,
        candidate: LearningCandidate,
        actor_role: Role,
    ) -> bool:
        if not has_capability(actor_role, "governance:manage"):
            raise PermissionError("Only organization Owners may promote learning candidates.")

        # 1. Protected scope boundary check
        target_scope = candidate.proposed_changes.get("target_scope")
        if target_scope in PROTECTED_SCOPES:
            raise ValueError(
                f"Protected scope '{target_scope}' cannot be modified by learning pipeline."
            )

        # 2. Canary evaluation gate (threshold: 0.95)
        return candidate.canary_pass_rate >= 0.95

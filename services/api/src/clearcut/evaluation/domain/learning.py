from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

import uuid6

PROTECTED_SCOPES = {
    "permissions",
    "sign_off",
    "categories",
    "authority_tiers",
    "evidence_schema",
    "blockers",
    "retention",
    "legal_boundary",
}


class LearningScope(StrEnum):
    QUERY_PHRASING = "query_phrasing"
    RETRIEVAL_EXAMPLES = "retrieval_examples"
    PROMPT_REFINEMENT = "prompt_refinement"
    ORG_PREFERENCES = "org_preferences"


@dataclass(frozen=True)
class LearningCandidate:
    candidate_id: UUID
    org_id: UUID
    scope: LearningScope
    proposed_changes: dict[str, Any]
    canary_pass_rate: float
    is_promoted: bool = False
    created_at: datetime = datetime.now(UTC)

    @classmethod
    def create(
        cls,
        org_id: UUID,
        scope: LearningScope,
        proposed_changes: dict[str, Any],
        canary_pass_rate: float,
    ) -> "LearningCandidate":
        return cls(
            candidate_id=uuid6.uuid7(),
            org_id=org_id,
            scope=scope,
            proposed_changes=proposed_changes,
            canary_pass_rate=canary_pass_rate,
            is_promoted=False,
            created_at=datetime.now(UTC),
        )

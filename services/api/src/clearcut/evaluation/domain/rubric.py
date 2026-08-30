from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

import uuid6


class JudgeDimension(StrEnum):
    DETECTION_RECALL = "detection_recall"
    CLAIM_GROUNDING = "claim_grounding"
    CITATION_PROVENANCE = "citation_provenance"
    SOURCE_AUTHORITY = "source_authority"
    CONFLICT_IDENTIFICATION = "conflict_identification"
    APPROPRIATE_UNCERTAINTY = "appropriate_uncertainty"
    REWRITE_USEFULNESS = "rewrite_usefulness"
    RESCAN_CORRECTNESS = "rescan_correctness"
    LEGAL_BOUNDARY = "legal_boundary"
    TOOL_EFFICIENCY = "tool_efficiency"


class DimensionStatus(StrEnum):
    SCORED = "scored"
    INCOMPLETE = "incomplete"
    NOT_APPLICABLE = "not_applicable"
    FAILED = "failed"


def get_stage_eligible_dimensions(stage: str) -> set[JudgeDimension]:
    if stage == "detection":
        return {
            JudgeDimension.DETECTION_RECALL,
            JudgeDimension.APPROPRIATE_UNCERTAINTY,
            JudgeDimension.LEGAL_BOUNDARY,
            JudgeDimension.TOOL_EFFICIENCY,
        }
    if stage == "research":
        return {
            JudgeDimension.DETECTION_RECALL,
            JudgeDimension.CLAIM_GROUNDING,
            JudgeDimension.CITATION_PROVENANCE,
            JudgeDimension.SOURCE_AUTHORITY,
            JudgeDimension.CONFLICT_IDENTIFICATION,
            JudgeDimension.APPROPRIATE_UNCERTAINTY,
            JudgeDimension.LEGAL_BOUNDARY,
            JudgeDimension.TOOL_EFFICIENCY,
        }
    # Final full clearance run
    return set(JudgeDimension)


@dataclass(frozen=True)
class JudgeVerdict:
    verdict_id: UUID
    dimension: JudgeDimension
    status: DimensionStatus
    score: float | None
    rationale: str
    created_at: datetime = datetime.now(UTC)

    @classmethod
    def create(
        cls,
        dimension: JudgeDimension,
        status: DimensionStatus,
        score: float | None,
        rationale: str,
    ) -> "JudgeVerdict":
        return cls(
            verdict_id=uuid6.uuid7(),
            dimension=dimension,
            status=status,
            score=score,
            rationale=rationale,
            created_at=datetime.now(UTC),
        )


@dataclass(frozen=True)
class AgentEvaluation:
    evaluation_id: UUID
    org_id: UUID
    project_id: UUID
    run_id: UUID
    stage: str
    headline_score: float | None
    scored_dimensions_count: int
    verdicts: tuple[JudgeVerdict, ...]
    blockers_count: int
    created_at: datetime = datetime.now(UTC)

    @classmethod
    def create(
        cls,
        org_id: UUID,
        project_id: UUID,
        run_id: UUID,
        stage: str,
        headline_score: float | None,
        scored_dimensions_count: int,
        verdicts: list[JudgeVerdict],
        blockers_count: int = 0,
    ) -> "AgentEvaluation":
        return cls(
            evaluation_id=uuid6.uuid7(),
            org_id=org_id,
            project_id=project_id,
            run_id=run_id,
            stage=stage,
            headline_score=headline_score,
            scored_dimensions_count=scored_dimensions_count,
            verdicts=tuple(verdicts),
            blockers_count=blockers_count,
            created_at=datetime.now(UTC),
        )

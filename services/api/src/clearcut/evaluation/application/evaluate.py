from uuid import UUID

from clearcut.detection.domain.candidates import CandidateItem
from clearcut.evaluation.domain.gates import GateResult, GateSeverity, run_deterministic_gates
from clearcut.evaluation.domain.rubric import (
    AgentEvaluation,
    DimensionStatus,
    JudgeVerdict,
)
from clearcut.evaluation.ports.judge import JudgePort


class EvaluationService:
    def __init__(self, judge: JudgePort) -> None:
        self.judge = judge
        self.evaluations: dict[UUID, AgentEvaluation] = {}

    def aggregate_evaluation(
        self,
        org_id: UUID,
        project_id: UUID,
        run_id: UUID,
        stage: str,
        verdicts: list[JudgeVerdict],
        blockers_count: int,
    ) -> AgentEvaluation:
        scored = [v for v in verdicts if v.status == DimensionStatus.SCORED and v.score is not None]
        scored_count = len(scored)

        headline: float | None = None
        if blockers_count > 0:
            headline = 0.0
        elif scored_count > 0:
            headline = sum(v.score for v in scored if v.score is not None) / scored_count

        evaluation = AgentEvaluation.create(
            org_id=org_id,
            project_id=project_id,
            run_id=run_id,
            stage=stage,
            headline_score=headline,
            scored_dimensions_count=scored_count,
            verdicts=verdicts,
            blockers_count=blockers_count,
        )
        self.evaluations[evaluation.evaluation_id] = evaluation
        return evaluation

    async def evaluate_detection_run(
        self,
        org_id: UUID,
        project_id: UUID,
        run_id: UUID,
        candidates: list[CandidateItem],
        element_texts: dict[UUID, str],
    ) -> tuple[list[GateResult], AgentEvaluation]:
        gate_results = run_deterministic_gates(candidates, element_texts)
        blockers = [g for g in gate_results if not g.passed and g.severity == GateSeverity.BLOCKER]

        verdicts = self.judge.evaluate_stage("detection", candidates, gate_results)
        evaluation = self.aggregate_evaluation(
            org_id=org_id,
            project_id=project_id,
            run_id=run_id,
            stage="detection",
            verdicts=verdicts,
            blockers_count=len(blockers),
        )

        return gate_results, evaluation

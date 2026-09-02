"""Evaluation orchestration with provider calls outside persistence transactions."""
from __future__ import annotations

from uuid import UUID

from clearcut.detection.domain.candidates import CandidateItem
from clearcut.evaluation.domain.gates import GateResult, GateSeverity, run_deterministic_gates
from clearcut.evaluation.domain.rubric import (
    AgentEvaluation,
    DimensionStatus,
    EvaluationStage,
    JudgeVerdict,
)
from clearcut.evaluation.ports.judge import (
    JudgeBindings,
    JudgeFailure,
    JudgePort,
    JudgeRequest,
    JudgeSafeError,
    ResearchEvidence,
    validate_judge_bindings,
)
from clearcut.evaluation.ports.repository import (
    EvaluationPersistenceError,
    EvaluationRepositoryPort,
    JudgeInvocationState,
)


class EvaluationExecutionError(RuntimeError):
    def __init__(self, error: JudgeSafeError) -> None:
        super().__init__(error.message)
        self.error = error


class EvaluationService:
    def __init__(
        self,
        judge: JudgePort,
        repository: EvaluationRepositoryPort | None = None,
    ) -> None:
        self.judge = judge
        self.repository = repository

    def aggregate_evaluation(
        self,
        org_id: UUID,
        project_id: UUID,
        run_id: UUID,
        stage: str,
        verdicts: list[JudgeVerdict],
        blockers_count: int,
    ) -> AgentEvaluation:
        scored = [
            verdict
            for verdict in verdicts
            if verdict.status == DimensionStatus.SCORED and verdict.score is not None
        ]
        scored_count = len(scored)

        headline: float | None = None
        if blockers_count > 0:
            headline = 0.0
        elif scored_count > 0:
            headline = sum(
                verdict.score for verdict in scored if verdict.score is not None
            ) / scored_count

        return AgentEvaluation.create(
            org_id=org_id,
            project_id=project_id,
            run_id=run_id,
            stage=stage,
            headline_score=headline,
            scored_dimensions_count=scored_count,
            verdicts=verdicts,
            blockers_count=blockers_count,
        )

    async def evaluate_detection_run(
        self,
        org_id: UUID,
        project_id: UUID,
        run_id: UUID,
        job_attempt_number: int,
        candidates: list[CandidateItem],
        element_texts: dict[UUID, str],
        bindings: JudgeBindings,
        gate_results: list[GateResult] | None = None,
    ) -> tuple[list[GateResult], AgentEvaluation]:
        if self.repository is None:
            raise RuntimeError(
                "Evaluation persistence must be configured before running a judge."
            )
        if job_attempt_number <= 0:
            raise EvaluationExecutionError(
                JudgeSafeError(
                    code="invalid_request",
                    message="A judge invocation requires a positive job attempt number.",
                    retryable=False,
                )
            )
        binding_error = validate_judge_bindings(bindings)
        if binding_error is not None:
            raise EvaluationExecutionError(binding_error)

        if gate_results is None:
            gate_results = run_deterministic_gates(candidates, element_texts)
        blockers = [
            gate
            for gate in gate_results
            if not gate.passed and gate.severity == GateSeverity.BLOCKER
        ]
        stage = EvaluationStage.DETECTION
        request = JudgeRequest(
            org_id=org_id,
            project_id=project_id,
            run_id=run_id,
            stage=stage,
            candidates=tuple(candidates),
            gate_results=tuple(gate_results),
            bindings=bindings,
        )
        prepared = await self.repository.prepare_invocation(
            org_id=org_id,
            project_id=project_id,
            run_id=run_id,
            job_attempt_number=job_attempt_number,
            stage=stage,
            bindings=bindings,
            requested_model=self.judge.requested_model,
        )
        if prepared.state is JudgeInvocationState.SUCCEEDED:
            if prepared.evaluation is None:
                raise EvaluationPersistenceError(
                    "A succeeded judge invocation has no persisted evaluation."
                )
            return gate_results, prepared.evaluation
        if prepared.state is JudgeInvocationState.FAILED:
            if prepared.error is None:
                raise EvaluationPersistenceError(
                    "A failed judge invocation has no persisted safe error."
                )
            raise EvaluationExecutionError(prepared.error)
        if prepared.state is JudgeInvocationState.PENDING:
            raise EvaluationExecutionError(
                JudgeSafeError(
                    code="judge_invocation_pending",
                    message=(
                        "This job attempt already has a pending judge invocation; "
                        "manual review or an explicit later job attempt is required."
                    ),
                    retryable=False,
                )
            )

        result = await self.judge.evaluate(request)
        if isinstance(result, JudgeFailure):
            if not result.attempts:
                raise EvaluationExecutionError(result.error)
            await self.repository.persist_failure(
                invocation_id=prepared.invocation_id,
                org_id=org_id,
                project_id=project_id,
                run_id=run_id,
                bindings=bindings,
                requested_model=result.requested_model,
                attempts=result.attempts,
            )
            raise EvaluationExecutionError(result.error)

        evaluation = self.aggregate_evaluation(
            org_id=org_id,
            project_id=project_id,
            run_id=run_id,
            stage=stage,
            verdicts=list(result.verdicts),
            blockers_count=len(blockers),
        )
        await self.repository.persist_success(
            invocation_id=prepared.invocation_id,
            evaluation=evaluation,
            critique=result.critique,
            bindings=bindings,
            metadata=result.metadata,
        )
        return gate_results, evaluation


    async def evaluate_research_run(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        run_id: UUID,
        job_attempt_number: int,
        evidence: tuple[ResearchEvidence, ...],
        gate_results: list[GateResult],
        bindings: JudgeBindings,
    ) -> AgentEvaluation:
        if self.repository is None:
            raise RuntimeError(
                "Evaluation persistence must be configured before running a judge."
            )
        if job_attempt_number <= 0:
            raise EvaluationExecutionError(
                JudgeSafeError(
                    code="invalid_request",
                    message="A judge invocation requires a positive job attempt number.",
                    retryable=False,
                )
            )
        binding_error = validate_judge_bindings(bindings)
        if binding_error is not None:
            raise EvaluationExecutionError(binding_error)

        blockers = [
            gate
            for gate in gate_results
            if not gate.passed and gate.severity == GateSeverity.BLOCKER
        ]
        stage = EvaluationStage.RESEARCH
        request = JudgeRequest(
            org_id=org_id,
            project_id=project_id,
            run_id=run_id,
            stage=stage,
            candidates=(),
            gate_results=tuple(gate_results),
            bindings=bindings,
            research_evidence=evidence,
        )
        prepared = await self.repository.prepare_invocation(
            org_id=org_id,
            project_id=project_id,
            run_id=run_id,
            job_attempt_number=job_attempt_number,
            stage=stage,
            bindings=bindings,
            requested_model=self.judge.requested_model,
        )
        if prepared.state is JudgeInvocationState.SUCCEEDED:
            if prepared.evaluation is None:
                raise EvaluationPersistenceError(
                    "A succeeded judge invocation has no persisted evaluation."
                )
            return prepared.evaluation
        if prepared.state is JudgeInvocationState.FAILED:
            if prepared.error is None:
                raise EvaluationPersistenceError(
                    "A failed judge invocation has no persisted safe error."
                )
            raise EvaluationExecutionError(prepared.error)
        if prepared.state is JudgeInvocationState.PENDING:
            raise EvaluationExecutionError(
                JudgeSafeError(
                    code="judge_invocation_pending",
                    message=(
                        "This job attempt already has a pending research judge "
                        "invocation; manual review is required."
                    ),
                    retryable=False,
                )
            )

        result = await self.judge.evaluate(request)
        if isinstance(result, JudgeFailure):
            if result.attempts:
                await self.repository.persist_failure(
                    invocation_id=prepared.invocation_id,
                    org_id=org_id,
                    project_id=project_id,
                    run_id=run_id,
                    bindings=bindings,
                    requested_model=result.requested_model,
                    attempts=result.attempts,
                )
            raise EvaluationExecutionError(result.error)

        evaluation = self.aggregate_evaluation(
            org_id=org_id,
            project_id=project_id,
            run_id=run_id,
            stage=stage,
            verdicts=list(result.verdicts),
            blockers_count=len(blockers),
        )
        await self.repository.persist_success(
            invocation_id=prepared.invocation_id,
            evaluation=evaluation,
            critique=result.critique,
            bindings=bindings,
            metadata=result.metadata,
        )
        return evaluation

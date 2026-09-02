from uuid import uuid4

import pytest
from clearcut.evaluation.application.evaluate import (
    EvaluationExecutionError,
    EvaluationService,
)
from clearcut.evaluation.domain.rubric import (
    AgentEvaluation,
    DimensionStatus,
    JudgeDimension,
    JudgeVerdict,
)
from clearcut.evaluation.ports.judge import (
    JudgeAttemptMetadata,
    JudgeBindings,
    JudgeFailure,
    JudgeInvocationMetadata,
    JudgeSafeError,
    JudgeSuccess,
    TokenUsage,
)
from clearcut.evaluation.ports.repository import (
    EvaluationPersistenceError,
    JudgeInvocationState,
    PreparedJudgeInvocation,
)


def _bindings() -> JudgeBindings:
    return JudgeBindings(
        rubric_version="rubric-v1",
        prompt_version="prompt-v1",
        policy_version="policy-v1",
        input_sha256="d" * 64,
    )


def _attempt(*, status: str, error: JudgeSafeError | None) -> JudgeAttemptMetadata:
    return JudgeAttemptMetadata(
        ordinal=1,
        status=status,
        returned_model=("gemini-3.1-pro-preview-20260815" if error is None else None),
        response_id="response-1" if error is None else None,
        usage=TokenUsage(input_tokens=10, output_tokens=10, total_tokens=20),
        latency_ms=20,
        error=error,
    )


def _success() -> JudgeSuccess:
    verdicts = tuple(
        JudgeVerdict.create(
            dimension=dimension,
            status=DimensionStatus.SCORED,
            score=90.0,
            rationale="Bounded test score.",
        )
        for dimension in JudgeDimension
    )
    attempt = _attempt(status="succeeded", error=None)
    return JudgeSuccess(
        verdicts=verdicts,
        critique="Bounded test critique.",
        metadata=JudgeInvocationMetadata(
            requested_model="gemini-3.1-pro-preview",
            returned_model="gemini-3.1-pro-preview-20260815",
            response_id="response-1",
            usage=attempt.usage,
            latency_ms=20,
            repair_count=0,
            attempts=(attempt,),
        ),
    )


class RecordingJudge:
    def __init__(self, result, events: list[str]) -> None:
        self.result = result
        self.events = events
        self.requested_model = (
            result.metadata.requested_model
            if isinstance(result, JudgeSuccess)
            else result.requested_model
        )

    async def evaluate(self, request):
        _ = request
        self.events.append("provider")
        return self.result


class RecordingRepository:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.successes = []
        self.failures = []

    async def prepare_invocation(self, **_kwargs):
        self.events.append("prepare")
        return PreparedJudgeInvocation(
            invocation_id=uuid4(),
            state=JudgeInvocationState.READY,
        )

    async def persist_success(self, **kwargs):
        self.events.append("persist_success")
        self.successes.append(kwargs)
        return kwargs["evaluation"]

    async def persist_failure(self, **kwargs):
        self.events.append("persist_failure")
        self.failures.append(kwargs)
        return (uuid4(),)


@pytest.mark.asyncio
async def test_evaluation_service_calls_provider_before_persisting_success() -> None:
    events: list[str] = []
    repository = RecordingRepository(events)
    service = EvaluationService(
        judge=RecordingJudge(_success(), events),
        repository=repository,
    )
    org_id, project_id, run_id = uuid4(), uuid4(), uuid4()

    _gates, evaluation = await service.evaluate_detection_run(
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        job_attempt_number=1,
        candidates=[],
        element_texts={},
        bindings=_bindings(),
    )

    assert events == ["prepare", "provider", "persist_success"]
    assert evaluation.run_id == run_id
    assert evaluation.headline_score == 90.0
    assert repository.successes[0]["metadata"].returned_model.endswith("20260815")
    assert not hasattr(service, "evaluations")


@pytest.mark.asyncio
async def test_evaluation_service_persists_safe_failure_after_provider_call() -> None:
    events: list[str] = []
    error = JudgeSafeError(
        code="provider_unavailable",
        message="The judge provider could not complete the request.",
        retryable=True,
    )
    failure = JudgeFailure(
        error=error,
        requested_model="gemini-3.1-pro-preview",
        attempts=(_attempt(status="failed", error=error),),
    )
    repository = RecordingRepository(events)
    service = EvaluationService(
        judge=RecordingJudge(failure, events),
        repository=repository,
    )

    with pytest.raises(EvaluationExecutionError) as raised:
        await service.evaluate_detection_run(
            org_id=uuid4(),
            project_id=uuid4(),
            run_id=uuid4(),
            job_attempt_number=1,
            candidates=[],
            element_texts={},
            bindings=_bindings(),
        )

    assert raised.value.error == error
    assert events == ["prepare", "provider", "persist_failure"]
    assert repository.failures[0]["attempts"] == failure.attempts



@pytest.mark.asyncio
async def test_evaluation_service_does_not_persist_failure_without_provider_attempt() -> None:
    events: list[str] = []
    error = JudgeSafeError(
        code="invalid_request",
        message="Judge invocation bindings are incomplete.",
        retryable=False,
    )
    failure = JudgeFailure(
        error=error,
        requested_model="gemini-3.1-pro-preview",
        attempts=(),
    )
    repository = RecordingRepository(events)
    service = EvaluationService(
        judge=RecordingJudge(failure, events),
        repository=repository,
    )

    with pytest.raises(EvaluationExecutionError) as raised:
        await service.evaluate_detection_run(
            org_id=uuid4(),
            project_id=uuid4(),
            run_id=uuid4(),
            job_attempt_number=1,
            candidates=[],
            element_texts={},
            bindings=JudgeBindings(
                rubric_version="",
                prompt_version="prompt-v1",
                policy_version="policy-v1",
                input_sha256="f" * 64,
            ),
        )

    assert raised.value.error == error
    assert events == []
    assert repository.failures == []



class PreparedInvocationRepository:
    def __init__(
        self,
        prepared: PreparedJudgeInvocation,
        events: list[str],
        *,
        fail_success_persistence: bool = False,
    ) -> None:
        self.prepared = prepared
        self.events = events
        self.fail_success_persistence = fail_success_persistence

    async def prepare_invocation(self, **_kwargs):
        self.events.append("prepare")
        if self.prepared.state is JudgeInvocationState.READY:
            self.prepared = PreparedJudgeInvocation(
                invocation_id=self.prepared.invocation_id,
                state=JudgeInvocationState.PENDING,
            )
            return PreparedJudgeInvocation(
                invocation_id=self.prepared.invocation_id,
                state=JudgeInvocationState.READY,
            )
        return self.prepared

    async def persist_success(self, **kwargs):
        self.events.append("persist_success")
        if self.fail_success_persistence:
            raise EvaluationPersistenceError("simulated post-provider persistence crash")
        self.prepared = PreparedJudgeInvocation(
            invocation_id=self.prepared.invocation_id,
            state=JudgeInvocationState.SUCCEEDED,
            evaluation=kwargs["evaluation"],
        )
        return kwargs["evaluation"]

    async def persist_failure(self, **_kwargs):
        self.events.append("persist_failure")
        return (uuid4(),)


def _persisted_evaluation(org_id, project_id, run_id) -> AgentEvaluation:
    return AgentEvaluation.create(
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        stage="detection",
        headline_score=90.0,
        scored_dimensions_count=10,
        verdicts=list(_success().verdicts),
        blockers_count=0,
    )


@pytest.mark.asyncio
async def test_evaluation_service_replays_terminal_success_without_provider_call() -> None:
    events: list[str] = []
    org_id, project_id, run_id = uuid4(), uuid4(), uuid4()
    existing = _persisted_evaluation(org_id, project_id, run_id)
    repository = PreparedInvocationRepository(
        PreparedJudgeInvocation(
            invocation_id=uuid4(),
            state=JudgeInvocationState.SUCCEEDED,
            evaluation=existing,
        ),
        events,
    )
    service = EvaluationService(
        judge=RecordingJudge(_success(), events),
        repository=repository,
    )

    _gates, evaluation = await service.evaluate_detection_run(
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        job_attempt_number=1,
        candidates=[],
        element_texts={},
        bindings=_bindings(),
    )

    assert evaluation == existing
    assert events == ["prepare"]


@pytest.mark.asyncio
async def test_evaluation_service_does_not_recall_provider_for_pending_invocation() -> None:
    events: list[str] = []
    repository = PreparedInvocationRepository(
        PreparedJudgeInvocation(
            invocation_id=uuid4(),
            state=JudgeInvocationState.PENDING,
        ),
        events,
    )
    service = EvaluationService(
        judge=RecordingJudge(_success(), events),
        repository=repository,
    )

    with pytest.raises(EvaluationExecutionError) as raised:
        await service.evaluate_detection_run(
            org_id=uuid4(),
            project_id=uuid4(),
            run_id=uuid4(),
            job_attempt_number=1,
            candidates=[],
            element_texts={},
            bindings=_bindings(),
        )

    assert raised.value.error.code == "judge_invocation_pending"
    assert raised.value.error.retryable is False
    assert events == ["prepare"]


@pytest.mark.asyncio
async def test_post_provider_persistence_crash_does_not_trigger_paid_replay() -> None:
    events: list[str] = []
    repository = PreparedInvocationRepository(
        PreparedJudgeInvocation(
            invocation_id=uuid4(),
            state=JudgeInvocationState.READY,
        ),
        events,
        fail_success_persistence=True,
    )
    judge = RecordingJudge(_success(), events)
    service = EvaluationService(judge=judge, repository=repository)
    arguments = {
        "org_id": uuid4(),
        "project_id": uuid4(),
        "run_id": uuid4(),
        "job_attempt_number": 1,
        "candidates": [],
        "element_texts": {},
        "bindings": _bindings(),
    }

    with pytest.raises(EvaluationPersistenceError):
        await service.evaluate_detection_run(**arguments)
    with pytest.raises(EvaluationExecutionError) as replay:
        await service.evaluate_detection_run(**arguments)

    assert replay.value.error.code == "judge_invocation_pending"
    assert events == ["prepare", "provider", "persist_success", "prepare"]

import json
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from clearcut.ai.model_roles import GeminiRole, ModelRoleConfiguration
from clearcut.database import session_scope
from clearcut.detection.adapters.sql_candidate_repository import (
    DetectionInvocationState,
    DetectionPersistenceError,
    SqlCandidateRepository,
)
from clearcut.detection.adapters.vertex_runtime import VertexDetectionRuntime
from clearcut.detection.application.run_detection_job import RunDetectionJobService
from clearcut.detection.domain.candidates import CandidateItem, ClearanceCategory
from clearcut.detection.ports.model_runtime import (
    DetectionAttemptMetadata,
    DetectionFailure,
    DetectionSafeError,
    DetectionSuccess,
    DetectionTokenUsage,
)
from clearcut.evaluation.adapters.hermetic_judge import HermeticJudgeAdapter
from clearcut.evaluation.adapters.sql_evaluation_repository import SqlEvaluationRepository
from clearcut.evaluation.application.evaluate import EvaluationService
from clearcut.evaluation.domain.gates import run_deterministic_gates
from clearcut.evaluation.domain.rubric import (
    DimensionStatus,
    JudgeDimension,
    JudgeVerdict,
)
from clearcut.evaluation.ports.judge import (
    JudgeAttemptMetadata,
    JudgeFailure,
    JudgeSafeError,
    JudgeSuccess,
    TokenUsage,
)
from clearcut.main import app
from clearcut.operations.adapters.sql_job_repository import SqlJobRepository
from clearcut.operations.application.run_job import JobExecutionError
from clearcut.operations.ports.job_repository import EnqueueJob
from clearcut.scripts.domain.elements import ElementType, ScriptElement
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


class FakeModels:
    def __init__(self, outcomes) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict] = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeClient:
    def __init__(self, outcomes) -> None:
        self.models = FakeModels(outcomes)


def _configuration() -> ModelRoleConfiguration:
    return ModelRoleConfiguration(
        role=GeminiRole.DETECTION,
        model="gemini-3.7-flash",
        environment_variable="CLEARCUT_GEMINI_DETECTION_MODEL",
        overridden=False,
    )


def _element(text: str = "Mara photographs an Apple iPhone.") -> ScriptElement:
    return ScriptElement.create(
        element_id=uuid4(),
        version_id=uuid4(),
        ordinal=1,
        element_type=ElementType.ACTION,
        text=text,
    )


def _response(payload: object) -> SimpleNamespace:
    return SimpleNamespace(
        text=json.dumps(payload) if not isinstance(payload, str) else payload,
        model_version="gemini-3.7-flash-20260820",
        response_id="detection-response-1",
        usage_metadata=SimpleNamespace(
            prompt_token_count=20,
            candidates_token_count=12,
            total_token_count=32,
        ),
    )


def _candidate_payload() -> dict:
    return {
        "candidates": [
            {
                "category": "products_and_trademarks",
                "text": "Apple iPhone",
                "span_start": 20,
                "span_end": 32,
                "rationale": "Named commercial product and trademark.",
                "uncertainty": "low",
            }
        ]
    }


@pytest.mark.asyncio
async def test_vertex_detection_returns_closed_candidates_and_provider_metadata() -> None:
    client = FakeClient([_response(_candidate_payload())])
    runtime = VertexDetectionRuntime(
        project="clearcut-workspace",
        role_configuration=_configuration(),
        client=client,
    )
    element = _element()

    result = await runtime.detect_element(element)

    assert isinstance(result, DetectionSuccess)
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.element_id == element.element_id
    assert candidate.category is ClearanceCategory.PRODUCTS_AND_TRADEMARKS
    assert candidate.span_start == 20
    assert candidate.span_end == 32
    assert candidate.text == "Apple iPhone"
    assert candidate.rationale == "Named commercial product and trademark."
    assert candidate.uncertainty == "low"
    assert result.metadata.requested_model == "gemini-3.7-flash"
    assert result.metadata.returned_model == "gemini-3.7-flash-20260820"
    assert result.metadata.response_id == "detection-response-1"
    assert result.metadata.usage.total_tokens == 32
    assert len(client.models.calls) == 1
    assert client.models.calls[0]["model"] == "gemini-3.7-flash"


@pytest.mark.asyncio
async def test_vertex_detection_distinguishes_valid_zero_candidates() -> None:
    client = FakeClient([_response({"candidates": []})])
    runtime = VertexDetectionRuntime(
        project="clearcut-workspace",
        role_configuration=_configuration(),
        client=client,
    )

    result = await runtime.detect_element(_element("Mara enters the quiet room."))

    assert isinstance(result, DetectionSuccess)
    assert result.candidates == ()
    assert len(client.models.calls) == 1


@pytest.mark.parametrize(
    "payload",
    [
        "not-json",
        {"candidates": [{"category": "legal_clearance", "text": "Apple"}]},
        {"candidates": [], "decision": "cleared"},
    ],
)
@pytest.mark.asyncio
async def test_vertex_detection_rejects_malformed_or_policy_invalid_output(
    payload: object,
) -> None:
    client = FakeClient([_response(payload)])
    runtime = VertexDetectionRuntime(
        project="clearcut-workspace",
        role_configuration=_configuration(),
        client=client,
    )

    result = await runtime.detect_element(_element())

    assert isinstance(result, DetectionFailure)
    assert result.error.code == "invalid_response"
    assert result.error.retryable is False
    assert result.attempt.returned_model == "gemini-3.7-flash-20260820"
    assert result.attempt.response_id == "detection-response-1"
    assert result.attempt.usage == DetectionTokenUsage(20, 12, 32)
    assert len(client.models.calls) == 1


@pytest.mark.asyncio
async def test_vertex_detection_redacts_retryable_provider_failure() -> None:
    client = FakeClient([TimeoutError("raw provider detail")])
    runtime = VertexDetectionRuntime(
        project="clearcut-workspace",
        role_configuration=_configuration(),
        client=client,
    )

    result = await runtime.detect_element(_element())

    assert isinstance(result, DetectionFailure)
    assert result.error.code == "provider_unavailable"
    assert result.error.retryable is True
    assert "raw provider detail" not in result.error.message
    assert result.attempt.requested_model == "gemini-3.7-flash"
    assert len(client.models.calls) == 1


async def _create_detection_scope() -> tuple[
    UUID,
    UUID,
    UUID,
    UUID,
    UUID,
    tuple[ScriptElement, ...],
]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"origin": "http://test"},
    ) as client:
        registration = await client.post(
            "/api/v1/users",
            json={
                "name": "Detection Owner",
                "email": f"detection-{uuid4().hex}@example.com",
                "password": "Password123!",
            },
        )
        assert registration.status_code == 201, registration.text
        context = await client.get("/api/v1/session-context")
        actor_id = UUID(context.json()["data"]["userId"])
        organization = await client.post(
            "/api/v1/organizations",
            json={"name": "Detection Studio", "slug": f"detect-{uuid4().hex[:8]}"},
        )
        org_id = UUID(organization.json()["data"]["orgId"])
        project = await client.post(
            f"/api/v1/organizations/{org_id}/projects",
            json={"title": "Detection Execution"},
        )
        project_id = UUID(project.json()["data"]["projectId"])

    script_id, version_id = uuid4(), uuid4()
    elements = (
        ScriptElement.create(
            element_id=uuid4(),
            version_id=version_id,
            ordinal=1,
            element_type=ElementType.ACTION,
            text="Mara photographs an Apple iPhone.",
        ),
        ScriptElement.create(
            element_id=uuid4(),
            version_id=version_id,
            ordinal=2,
            element_type=ElementType.ACTION,
            text="   ",
        ),
    )
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO scripts "
                "(id, org_id, project_id, title, current_slot, created_at) VALUES "
                "(:id, :org_id, :project_id, 'Detection Script', 'current', CURRENT_TIMESTAMP)"
            ),
            {
                "id": str(script_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO script_versions "
                "(id, script_id, org_id, project_id, ordinal, source_hash, "
                "parser_version, created_at) VALUES "
                "(:id, :script_id, :org_id, :project_id, 1, :source_hash, "
                "'detection-test', CURRENT_TIMESTAMP)"
            ),
            {
                "id": str(version_id),
                "script_id": str(script_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "source_hash": "d" * 64,
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO script_elements "
                "(id, version_id, ordinal, element_type, text) VALUES "
                "(:id, :version_id, :ordinal, :element_type, :text)"
            ),
            [
                {
                    "id": str(element.element_id),
                    "version_id": str(version_id),
                    "ordinal": element.ordinal,
                    "element_type": element.element_type.value,
                    "text": element.text,
                }
                for element in elements
            ],
        )

    jobs = SqlJobRepository()
    enqueued = await jobs.enqueue(
        EnqueueJob(
            org_id=org_id,
            project_id=project_id,
            actor_id=actor_id,
            job_type="detection",
            idempotency_key=f"detection:{version_id}",
            payload={
                "schemaVersion": 1,
                "target": {"type": "script_version", "id": str(version_id)},
            },
            audit_action="detection.started",
            target_type="script_version",
            target_id=version_id,
        )
    )
    claimed = await jobs.claim(
        org_id=org_id,
        project_id=project_id,
        job_id=enqueued.job.job_id,
        lease_owner="detection-repository-test",
    )
    assert claimed is not None
    assert claimed.attempt_count == 1
    return org_id, project_id, script_id, version_id, claimed.job_id, elements


def _detection_success(element: ScriptElement) -> DetectionSuccess:
    candidate = _candidate_payload()["candidates"][0]
    return DetectionSuccess(
        candidates=(
            CandidateItem.create(
                category=ClearanceCategory(candidate["category"]),
                element_id=element.element_id,
                span_start=candidate["span_start"],
                span_end=candidate["span_end"],
                text=candidate["text"],
                rationale=candidate["rationale"],
                uncertainty=candidate["uncertainty"],
            ),
        ),
        metadata=DetectionAttemptMetadata(
            status="succeeded",
            requested_model="gemini-3.7-flash",
            returned_model="gemini-3.7-flash-20260820",
            response_id="detection-response-1",
            usage=DetectionTokenUsage(
                input_tokens=20,
                output_tokens=12,
                total_tokens=32,
            ),
            latency_ms=25,
            error=None,
        ),
    )


@pytest.mark.asyncio
async def test_sql_candidate_repository_fences_and_replays_element_success() -> None:
    org_id, project_id, script_id, version_id, run_id, elements = await _create_detection_scope()
    repository = SqlCandidateRepository()

    loaded = await repository.load_input(
        org_id=org_id,
        project_id=project_id,
        version_id=version_id,
    )
    assert loaded.script_id == script_id
    assert loaded.version_id == version_id
    assert loaded.elements == elements

    first = await repository.prepare_invocation(
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        job_attempt_number=1,
        version_id=version_id,
        element_id=elements[0].element_id,
        requested_model="gemini-3.7-flash",
        input_sha256="a" * 64,
    )
    same_attempt = await repository.prepare_invocation(
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        job_attempt_number=1,
        version_id=version_id,
        element_id=elements[0].element_id,
        requested_model="gemini-3.7-flash",
        input_sha256="a" * 64,
    )
    assert first.state is DetectionInvocationState.READY
    assert same_attempt.state is DetectionInvocationState.PENDING
    assert same_attempt.invocation_id == first.invocation_id

    with pytest.raises(DetectionPersistenceError, match="immutable input or model"):
        await repository.prepare_invocation(
            org_id=org_id,
            project_id=project_id,
            run_id=run_id,
            job_attempt_number=1,
            version_id=version_id,
            element_id=elements[0].element_id,
            requested_model="gemini-3.7-flash",
            input_sha256="b" * 64,
        )

    success = _detection_success(elements[0])
    await repository.persist_success(
        invocation_id=first.invocation_id,
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        version_id=version_id,
        element_id=elements[0].element_id,
        result=success,
    )
    replay = await repository.prepare_invocation(
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        job_attempt_number=1,
        version_id=version_id,
        element_id=elements[0].element_id,
        requested_model="gemini-3.7-flash",
        input_sha256="a" * 64,
    )
    assert replay.state is DetectionInvocationState.SUCCEEDED
    assert replay.result == success

    async with session_scope() as session:
        persisted = (
            (
                await session.execute(
                    sa.text(
                        "SELECT c.*, i.requested_model, i.returned_model "
                        "FROM detection_candidates c JOIN detection_invocations i "
                        "ON i.id = c.invocation_id "
                        "WHERE c.org_id = :org_id AND c.project_id = :project_id "
                        "AND c.run_id = :run_id"
                    ),
                    {
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                        "run_id": str(run_id),
                    },
                )
            )
            .mappings()
            .one()
        )
    assert persisted["script_version_id"] == str(version_id)
    assert persisted["span_start"] == 20
    assert persisted["span_end"] == 32
    assert persisted["rationale"] == "Named commercial product and trademark."
    assert persisted["uncertainty"] == "low"
    assert persisted["requested_model"] == "gemini-3.7-flash"
    assert persisted["returned_model"] == "gemini-3.7-flash-20260820"

    async with session_scope() as session:
        await session.execute(
            sa.text(
                "UPDATE jobs SET attempt_count = 2 WHERE id = :run_id "
                "AND org_id = :org_id AND project_id = :project_id"
            ),
            {
                "run_id": str(run_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
            },
        )
    later = await repository.prepare_invocation(
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        job_attempt_number=2,
        version_id=version_id,
        element_id=elements[0].element_id,
        requested_model="gemini-3.7-flash",
        input_sha256="a" * 64,
    )
    assert later.state is DetectionInvocationState.READY
    assert later.invocation_id != first.invocation_id


@pytest.mark.asyncio
async def test_sql_candidate_repository_replays_safe_terminal_failure() -> None:
    org_id, project_id, _script_id, version_id, run_id, elements = await _create_detection_scope()
    repository = SqlCandidateRepository()
    prepared = await repository.prepare_invocation(
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        job_attempt_number=1,
        version_id=version_id,
        element_id=elements[0].element_id,
        requested_model="gemini-3.7-flash",
        input_sha256="c" * 64,
    )
    error = DetectionSafeError(
        code="invalid_response",
        message="The detection provider returned an invalid structured response.",
        retryable=False,
    )
    failure = DetectionFailure(
        error=error,
        attempt=DetectionAttemptMetadata(
            status="invalid_response",
            requested_model="gemini-3.7-flash",
            returned_model="gemini-3.7-flash-20260820",
            response_id="invalid-response-1",
            usage=DetectionTokenUsage(20, 12, 32),
            latency_ms=30,
            error=error,
        ),
    )

    await repository.persist_failure(
        invocation_id=prepared.invocation_id,
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        version_id=version_id,
        element_id=elements[0].element_id,
        result=failure,
    )
    replay = await repository.prepare_invocation(
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        job_attempt_number=1,
        version_id=version_id,
        element_id=elements[0].element_id,
        requested_model="gemini-3.7-flash",
        input_sha256="c" * 64,
    )

    assert replay.state is DetectionInvocationState.FAILED
    assert replay.error == error
    assert replay.result is None
    async with session_scope() as session:
        persisted = (
            (
                await session.execute(
                    sa.text(
                        "SELECT returned_model, response_id, input_tokens, output_tokens, "
                        "total_tokens FROM detection_invocations WHERE id = :id"
                    ),
                    {"id": str(prepared.invocation_id)},
                )
            )
            .mappings()
            .one()
        )
    assert persisted["returned_model"] == "gemini-3.7-flash-20260820"
    assert persisted["response_id"] == "invalid-response-1"
    assert persisted["input_tokens"] == 20
    assert persisted["output_tokens"] == 12
    assert persisted["total_tokens"] == 32


@pytest.mark.asyncio
async def test_sql_candidate_repository_persists_each_gate_for_its_candidate() -> None:
    org_id, project_id, _script_id, version_id, run_id, elements = await _create_detection_scope()
    repository = SqlCandidateRepository()
    prepared = await repository.prepare_invocation(
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        job_attempt_number=1,
        version_id=version_id,
        element_id=elements[0].element_id,
        requested_model="gemini-3.7-flash",
        input_sha256="e" * 64,
    )
    success = _detection_success(elements[0])
    candidates = await repository.persist_success(
        invocation_id=prepared.invocation_id,
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        version_id=version_id,
        element_id=elements[0].element_id,
        result=success,
    )
    gate_results = run_deterministic_gates(
        list(candidates),
        {elements[0].element_id: elements[0].text},
    )

    await repository.persist_gate_results(
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        job_attempt_number=1,
        lease_owner="detection-repository-test",
        results=gate_results,
    )

    async with session_scope() as session:
        rows = (
            (
                await session.execute(
                    sa.text(
                        "SELECT candidate_id, gate_name FROM deterministic_gate_results "
                        "WHERE org_id = :org_id AND project_id = :project_id "
                        "AND run_id = :run_id ORDER BY gate_name"
                    ),
                    {
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                        "run_id": str(run_id),
                    },
                )
            )
            .mappings()
            .all()
        )

    assert len(rows) == 3
    assert {UUID(str(row["candidate_id"])) for row in rows} == {candidates[0].item_id}
    assert {str(row["gate_name"]) for row in rows} == {
        "SpanBoundaryGate",
        "LegalCertaintyGate",
        "PromptInjectionGate",
    }


@pytest.mark.asyncio
async def test_cancelled_job_fences_terminal_detection_persistence() -> None:
    org_id, project_id, _script_id, version_id, run_id, elements = await _create_detection_scope()
    repository = SqlCandidateRepository()
    prepared = await repository.prepare_invocation(
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        job_attempt_number=1,
        version_id=version_id,
        element_id=elements[0].element_id,
        requested_model="gemini-3.7-flash",
        input_sha256="f" * 64,
    )
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "UPDATE jobs SET status = 'cancelled', stage = 'cancelled', "
                "lease_owner = NULL, lease_expires_at = NULL "
                "WHERE id = :run_id AND org_id = :org_id AND project_id = :project_id"
            ),
            {
                "run_id": str(run_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
            },
        )

    with pytest.raises(DetectionPersistenceError, match="active job attempt"):
        await repository.persist_success(
            invocation_id=prepared.invocation_id,
            org_id=org_id,
            project_id=project_id,
            run_id=run_id,
            version_id=version_id,
            element_id=elements[0].element_id,
            result=_detection_success(elements[0]),
        )

    async with session_scope() as session:
        candidate_count = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM detection_candidates "
                    "WHERE org_id = :org_id AND project_id = :project_id "
                    "AND run_id = :run_id"
                ),
                {
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                    "run_id": str(run_id),
                },
            )
        ).scalar_one()
    assert candidate_count == 0


class RecordingDetectionRuntime:
    requested_model = "gemini-3.7-flash"

    def __init__(self) -> None:
        self.elements: list[ScriptElement] = []

    async def detect_element(self, element: ScriptElement):
        self.elements.append(element)
        return _detection_success(element)


@pytest.mark.asyncio
async def test_detection_job_executes_non_empty_elements_and_persists_truthful_output() -> None:
    org_id, project_id, _script_id, version_id, run_id, elements = await _create_detection_scope()
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO protected_configurations "
                "(id, org_id, lifecycle, policy_version, prompt_version, created_at) "
                "VALUES (:id, :org_id, 'active', 'policy-v1', 'prompt-v1', "
                "CURRENT_TIMESTAMP)"
            ),
            {"id": str(uuid4()), "org_id": str(org_id)},
        )
    jobs = SqlJobRepository()
    job = await jobs.get(org_id=org_id, project_id=project_id, job_id=run_id)
    assert job is not None
    runtime = RecordingDetectionRuntime()
    processor = RunDetectionJobService(
        repository=SqlCandidateRepository(),
        job_repository=SqlJobRepository(),
        runtime=runtime,
        evaluation=EvaluationService(
            judge=HermeticJudgeAdapter(),
            repository=SqlEvaluationRepository(),
        ),
    )

    result = await processor(job)

    assert [element.element_id for element in runtime.elements] == [elements[0].element_id]
    assert result.summary["scriptVersionId"] == str(version_id)
    assert result.summary["elementsProcessed"] == 1
    assert result.summary["elementsSkipped"] == 1
    assert result.summary["candidateCount"] == 1
    assert result.summary["gateResultCount"] == 3
    assert result.summary["blockerCount"] == 0
    assert result.summary["clearanceItemCount"] == 1
    assert result.summary["evaluationId"]

    async with session_scope() as session:
        counts = {}
        for table in (
            "detection_candidates",
            "deterministic_gate_results",
            "agent_evaluations",
            "judge_verdicts",
            "clearance_items",
        ):
            counts[table] = (
                await session.execute(sa.text(f"SELECT count(*) FROM {table}"))
            ).scalar_one()
        candidate = (
            (
                await session.execute(
                    sa.text(
                        "SELECT c.*, i.requested_model, i.returned_model "
                        "FROM detection_candidates c JOIN detection_invocations i "
                        "ON i.id = c.invocation_id WHERE c.run_id = :run_id"
                    ),
                    {"run_id": str(run_id)},
                )
            )
            .mappings()
            .one()
        )

    assert counts == {
        "detection_candidates": 1,
        "deterministic_gate_results": 3,
        "agent_evaluations": 1,
        "judge_verdicts": 10,
        "clearance_items": 1,
    }
    assert candidate["rationale"] == "Named commercial product and trademark."
    assert candidate["uncertainty"] == "low"
    assert candidate["requested_model"] == "gemini-3.7-flash"
    assert candidate["returned_model"] == "gemini-3.7-flash-20260820"


class RejectingJudge(HermeticJudgeAdapter):
    async def evaluate(self, request):
        accepted = await super().evaluate(request)
        verdicts = tuple(
            JudgeVerdict.create(
                dimension=verdict.dimension,
                status=(
                    DimensionStatus.FAILED
                    if verdict.dimension is JudgeDimension.DETECTION_RECALL
                    else verdict.status
                ),
                score=(
                    0.0 if verdict.dimension is JudgeDimension.DETECTION_RECALL else verdict.score
                ),
                rationale=(
                    "Detection quality requires accountable human review."
                    if verdict.dimension is JudgeDimension.DETECTION_RECALL
                    else verdict.rationale
                ),
            )
            for verdict in accepted.verdicts
        )
        return JudgeSuccess(
            verdicts=verdicts,
            critique="Detection quality was rejected by the bounded judge.",
            metadata=accepted.metadata,
        )


@pytest.mark.asyncio
async def test_judge_rejection_persists_verdict_and_unresolved_item() -> None:
    org_id, project_id, _script_id, version_id, run_id, _elements = await _create_detection_scope()
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO protected_configurations "
                "(id, org_id, lifecycle, policy_version, prompt_version, created_at) "
                "VALUES (:id, :org_id, 'active', 'policy-v1', 'prompt-v1', "
                "CURRENT_TIMESTAMP)"
            ),
            {"id": str(uuid4()), "org_id": str(org_id)},
        )
    job = await SqlJobRepository().get(
        org_id=org_id,
        project_id=project_id,
        job_id=run_id,
    )
    assert job is not None
    processor = RunDetectionJobService(
        repository=SqlCandidateRepository(),
        job_repository=SqlJobRepository(),
        runtime=RecordingDetectionRuntime(),
        evaluation=EvaluationService(
            judge=RejectingJudge(),
            repository=SqlEvaluationRepository(),
        ),
    )

    with pytest.raises(JobExecutionError) as raised:
        await processor(job)

    assert raised.value.error.code == "judge_rejected"
    assert raised.value.error.retryable is False
    async with session_scope() as session:
        evaluation_count = (
            await session.execute(
                sa.text("SELECT count(*) FROM agent_evaluations WHERE run_id = :run_id"),
                {"run_id": str(run_id)},
            )
        ).scalar_one()
        failed_verdicts = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM judge_verdicts v "
                    "JOIN agent_evaluations e ON e.id = v.evaluation_id "
                    "WHERE e.run_id = :run_id AND v.status = 'failed'"
                ),
                {"run_id": str(run_id)},
            )
        ).scalar_one()
        item_count = (
            await session.execute(
                sa.text("SELECT count(*) FROM clearance_items WHERE version_id = :version_id"),
                {"version_id": str(version_id)},
            )
        ).scalar_one()
    assert evaluation_count == 1
    assert failed_verdicts == 1
    assert item_count == 1


class ZeroCandidateRuntime:
    requested_model = "gemini-3.7-flash"

    def __init__(self) -> None:
        self.calls = 0

    async def detect_element(self, element: ScriptElement):
        _ = element
        self.calls += 1
        return DetectionSuccess(
            candidates=(),
            metadata=DetectionAttemptMetadata(
                status="succeeded",
                requested_model=self.requested_model,
                returned_model="gemini-3.7-flash-20260820",
                response_id=f"zero-candidate-{self.calls}",
                usage=DetectionTokenUsage(10, 2, 12),
                latency_ms=10,
                error=None,
            ),
        )


@pytest.mark.asyncio
async def test_zero_candidates_is_an_explicit_successful_detection_summary() -> None:
    org_id, project_id, _script_id, version_id, run_id, _elements = await _create_detection_scope()
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO protected_configurations "
                "(id, org_id, lifecycle, policy_version, prompt_version, created_at) "
                "VALUES (:id, :org_id, 'active', 'policy-v1', 'prompt-v1', "
                "CURRENT_TIMESTAMP)"
            ),
            {"id": str(uuid4()), "org_id": str(org_id)},
        )
    job = await SqlJobRepository().get(
        org_id=org_id,
        project_id=project_id,
        job_id=run_id,
    )
    assert job is not None
    runtime = ZeroCandidateRuntime()
    processor = RunDetectionJobService(
        repository=SqlCandidateRepository(),
        job_repository=SqlJobRepository(),
        runtime=runtime,
        evaluation=EvaluationService(
            judge=HermeticJudgeAdapter(),
            repository=SqlEvaluationRepository(),
        ),
    )

    result = await processor(job)

    assert runtime.calls == 1
    assert result.summary["scriptVersionId"] == str(version_id)
    assert result.summary["candidateCount"] == 0
    assert result.summary["gateResultCount"] == 0
    assert result.summary["blockerCount"] == 0
    assert result.summary["clearanceItemCount"] == 0
    assert result.summary["judgePassed"] is False
    assert result.summary["reviewStatus"] == "unresolved"
    assert result.summary["reason"] == "no_candidates_detected"
    async with session_scope() as session:
        invocation = (
            (
                await session.execute(
                    sa.text(
                        "SELECT status, candidate_count FROM detection_invocations "
                        "WHERE run_id = :run_id"
                    ),
                    {"run_id": str(run_id)},
                )
            )
            .mappings()
            .one()
        )
        evaluation_count = (
            await session.execute(
                sa.text("SELECT count(*) FROM agent_evaluations WHERE run_id = :run_id"),
                {"run_id": str(run_id)},
            )
        ).scalar_one()
    assert invocation["status"] == "succeeded"
    assert invocation["candidate_count"] == 0
    assert evaluation_count == 1


class FailingDetectionRuntime:
    requested_model = "gemini-3.7-flash"

    def __init__(self) -> None:
        self.calls = 0

    async def detect_element(self, element: ScriptElement):
        _ = element
        self.calls += 1
        error = DetectionSafeError(
            code="provider_unavailable",
            message="The detection provider could not complete the request.",
            retryable=True,
        )
        return DetectionFailure(
            error=error,
            attempt=DetectionAttemptMetadata(
                status="failed",
                requested_model=self.requested_model,
                returned_model=None,
                response_id=None,
                usage=DetectionTokenUsage(None, None, None),
                latency_ms=15,
                error=error,
            ),
        )


@pytest.mark.asyncio
async def test_detection_provider_failure_is_persisted_and_fails_job_safely() -> None:
    org_id, project_id, _script_id, _version_id, run_id, _elements = await _create_detection_scope()
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO protected_configurations "
                "(id, org_id, lifecycle, policy_version, prompt_version, created_at) "
                "VALUES (:id, :org_id, 'active', 'policy-v1', 'prompt-v1', "
                "CURRENT_TIMESTAMP)"
            ),
            {"id": str(uuid4()), "org_id": str(org_id)},
        )
    job = await SqlJobRepository().get(
        org_id=org_id,
        project_id=project_id,
        job_id=run_id,
    )
    assert job is not None
    runtime = FailingDetectionRuntime()
    processor = RunDetectionJobService(
        repository=SqlCandidateRepository(),
        job_repository=SqlJobRepository(),
        runtime=runtime,
        evaluation=EvaluationService(
            judge=HermeticJudgeAdapter(),
            repository=SqlEvaluationRepository(),
        ),
    )

    with pytest.raises(JobExecutionError) as raised:
        await processor(job)

    assert runtime.calls == 1
    assert raised.value.error.code == "provider_unavailable"
    assert raised.value.error.retryable is True
    async with session_scope() as session:
        invocation = (
            (
                await session.execute(
                    sa.text(
                        "SELECT status, safe_error FROM detection_invocations "
                        "WHERE run_id = :run_id"
                    ),
                    {"run_id": str(run_id)},
                )
            )
            .mappings()
            .one()
        )
        candidate_count = (
            await session.execute(
                sa.text("SELECT count(*) FROM detection_candidates WHERE run_id = :run_id"),
                {"run_id": str(run_id)},
            )
        ).scalar_one()
    assert invocation["status"] == "failed"
    assert json.loads(invocation["safe_error"])["code"] == "provider_unavailable"
    assert candidate_count == 0


@pytest.mark.asyncio
async def test_detection_requires_an_active_org_policy_binding() -> None:
    """Detection fails closed when the organization has no active binding.

    The former companion case seeded two active bindings to prove detection also
    refuses an ambiguous one. That is now unreachable through this path: since
    0036 a partial unique index permits at most one active row per organization,
    so the ambiguity is rejected by the database before any job can observe it.
    The test below covers that boundary directly.
    """
    org_id, project_id, _script_id, _version_id, run_id, _elements = await _create_detection_scope()
    job = await SqlJobRepository().get(
        org_id=org_id,
        project_id=project_id,
        job_id=run_id,
    )
    assert job is not None
    runtime = RecordingDetectionRuntime()
    processor = RunDetectionJobService(
        repository=SqlCandidateRepository(),
        job_repository=SqlJobRepository(),
        runtime=runtime,
        evaluation=EvaluationService(
            judge=HermeticJudgeAdapter(),
            repository=SqlEvaluationRepository(),
        ),
    )

    with pytest.raises(JobExecutionError) as raised:
        await processor(job)

    assert raised.value.error.code == "detection_configuration_unavailable"
    assert raised.value.error.retryable is False
    assert runtime.elements == []


@pytest.mark.asyncio
async def test_a_second_active_policy_binding_is_rejected_by_the_database() -> None:
    """The one-active-binding invariant is enforced in storage, not just in readers.

    Detection and research each re-check it, but two hand-rolled reader checks
    cannot stop a concurrent activation from creating the ambiguity in the first
    place. The partial unique index added in 0036 does.
    """
    org_id, _project_id, _script_id, _version_id, _run_id, _elements = (
        await _create_detection_scope()
    )
    insert = sa.text(
        "INSERT INTO protected_configurations "
        "(id, org_id, lifecycle, policy_version, prompt_version, created_at) "
        "VALUES (:id, :org_id, 'active', :policy, :prompt, CURRENT_TIMESTAMP)"
    )
    async with session_scope() as session:
        await session.execute(
            insert,
            {
                "id": str(uuid4()),
                "org_id": str(org_id),
                "policy": "policy-v1",
                "prompt": "prompt-v1",
            },
        )

    with pytest.raises(IntegrityError):
        async with session_scope() as session:
            await session.execute(
                insert,
                {
                    "id": str(uuid4()),
                    "org_id": str(org_id),
                    "policy": "policy-v2",
                    "prompt": "prompt-v2",
                },
            )

    async with session_scope() as session:
        active_count = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM protected_configurations "
                    "WHERE org_id = :org_id AND lifecycle = 'active'"
                ),
                {"org_id": str(org_id)},
            )
        ).scalar_one()
    assert active_count == 1


def test_application_registers_the_detection_job_processor() -> None:
    assert "detection" in app.state.job_runner.configured_job_types
    assert isinstance(app.state.run_detection_job, RunDetectionJobService)


class FailingJudge:
    requested_model = "gemini-3.1-pro-preview"

    async def evaluate(self, request):
        _ = request
        error = JudgeSafeError(
            code="invalid_response",
            message="The judge provider returned an invalid structured response.",
            retryable=False,
        )
        return JudgeFailure(
            error=error,
            requested_model=self.requested_model,
            attempts=(
                JudgeAttemptMetadata(
                    ordinal=1,
                    status="invalid_response",
                    returned_model="gemini-3.1-pro-preview-20260815",
                    response_id="judge-invalid-1",
                    usage=TokenUsage(100, 20, 120),
                    latency_ms=10,
                    error=error,
                ),
                JudgeAttemptMetadata(
                    ordinal=2,
                    status="invalid_response",
                    returned_model="gemini-3.1-pro-preview-20260815",
                    response_id="judge-invalid-2",
                    usage=TokenUsage(100, 20, 120),
                    latency_ms=10,
                    error=error,
                ),
            ),
        )


@pytest.mark.asyncio
async def test_judge_failure_retains_unresolved_items_and_deterministic_gates() -> None:
    org_id, project_id, _script_id, _version_id, run_id, _elements = await _create_detection_scope()
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO protected_configurations "
                "(id, org_id, lifecycle, policy_version, prompt_version, created_at) "
                "VALUES (:id, :org_id, 'active', 'policy-v1', 'prompt-v1', "
                "CURRENT_TIMESTAMP)"
            ),
            {"id": str(uuid4()), "org_id": str(org_id)},
        )
    job = await SqlJobRepository().get(
        org_id=org_id,
        project_id=project_id,
        job_id=run_id,
    )
    assert job is not None
    processor = RunDetectionJobService(
        repository=SqlCandidateRepository(),
        job_repository=SqlJobRepository(),
        runtime=RecordingDetectionRuntime(),
        evaluation=EvaluationService(
            judge=FailingJudge(),
            repository=SqlEvaluationRepository(),
        ),
    )

    with pytest.raises(JobExecutionError) as raised:
        await processor(job)

    assert raised.value.error.code == "invalid_response"
    async with session_scope() as session:
        gate_count = (
            await session.execute(
                sa.text("SELECT count(*) FROM deterministic_gate_results WHERE run_id = :run_id"),
                {"run_id": str(run_id)},
            )
        ).scalar_one()
        item_count = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM clearance_items WHERE detection_candidate_id IS NOT NULL"
                )
            )
        ).scalar_one()
        attempt_count = (
            await session.execute(
                sa.text("SELECT count(*) FROM ai_provider_attempts WHERE run_id = :run_id"),
                {"run_id": str(run_id)},
            )
        ).scalar_one()
    assert gate_count == 3
    assert item_count == 1
    assert attempt_count == 2


@pytest.mark.asyncio
async def test_expired_lease_fences_terminal_detection_persistence() -> None:
    org_id, project_id, _script_id, version_id, run_id, elements = await _create_detection_scope()
    repository = SqlCandidateRepository()
    prepared = await repository.prepare_invocation(
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        job_attempt_number=1,
        version_id=version_id,
        element_id=elements[0].element_id,
        requested_model="gemini-3.7-flash",
        input_sha256="1" * 64,
    )
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "UPDATE jobs SET lease_expires_at = '2000-01-01 00:00:00' "
                "WHERE id = :run_id AND org_id = :org_id AND project_id = :project_id"
            ),
            {
                "run_id": str(run_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
            },
        )

    with pytest.raises(DetectionPersistenceError, match="active job lease"):
        await repository.persist_success(
            invocation_id=prepared.invocation_id,
            org_id=org_id,
            project_id=project_id,
            run_id=run_id,
            version_id=version_id,
            element_id=elements[0].element_id,
            result=_detection_success(elements[0]),
        )


@pytest.mark.asyncio
async def test_database_rejects_same_tenant_cross_run_provenance_splicing() -> None:
    (
        org_id,
        project_id,
        _script_id,
        version_id,
        first_run_id,
        elements,
    ) = await _create_detection_scope()
    repository = SqlCandidateRepository()
    prepared = await repository.prepare_invocation(
        org_id=org_id,
        project_id=project_id,
        run_id=first_run_id,
        job_attempt_number=1,
        version_id=version_id,
        element_id=elements[0].element_id,
        requested_model="gemini-3.7-flash",
        input_sha256="2" * 64,
    )
    candidates = await repository.persist_success(
        invocation_id=prepared.invocation_id,
        org_id=org_id,
        project_id=project_id,
        run_id=first_run_id,
        version_id=version_id,
        element_id=elements[0].element_id,
        result=_detection_success(elements[0]),
    )
    jobs = SqlJobRepository()
    first_job = await jobs.get(
        org_id=org_id,
        project_id=project_id,
        job_id=first_run_id,
    )
    assert first_job is not None
    assert first_job.actor_id is not None
    second = await jobs.enqueue(
        EnqueueJob(
            org_id=org_id,
            project_id=project_id,
            actor_id=first_job.actor_id,
            job_type="detection",
            idempotency_key=f"detection:splice:{uuid4()}",
            payload={
                "schemaVersion": 1,
                "target": {"type": "script_version", "id": str(version_id)},
            },
            audit_action="detection.started",
            target_type="script_version",
            target_id=version_id,
        )
    )
    second_job = await jobs.claim(
        org_id=org_id,
        project_id=project_id,
        job_id=second.job.job_id,
        lease_owner="second-run-worker",
    )
    assert second_job is not None

    with pytest.raises(IntegrityError):
        async with session_scope() as session:
            await session.execute(
                sa.text(
                    "INSERT INTO detection_candidates "
                    "(id, org_id, project_id, run_id, invocation_id, "
                    "script_version_id, element_id, ordinal, category, span_start, "
                    "span_end, text, rationale, uncertainty, candidate_fingerprint, "
                    "created_at) VALUES "
                    "(:id, :org_id, :project_id, :run_id, :invocation_id, "
                    ":version_id, :element_id, 2, 'products_and_trademarks', 20, "
                    "32, 'Apple iPhone', 'Cross-run splice', 'low', :fingerprint, "
                    "CURRENT_TIMESTAMP)"
                ),
                {
                    "id": str(uuid4()),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                    "run_id": str(second_job.job_id),
                    "invocation_id": str(prepared.invocation_id),
                    "version_id": str(version_id),
                    "element_id": str(elements[0].element_id),
                    "fingerprint": "3" * 64,
                },
            )

    with pytest.raises(IntegrityError):
        async with session_scope() as session:
            await session.execute(
                sa.text(
                    "INSERT INTO deterministic_gate_results "
                    "(id, org_id, project_id, run_id, candidate_id, gate_name, "
                    "passed, severity, details, created_at) VALUES "
                    "(:id, :org_id, :project_id, :run_id, :candidate_id, "
                    "'CrossRunGate', 0, 'blocker', 'Cross-run splice', "
                    "CURRENT_TIMESTAMP)"
                ),
                {
                    "id": str(uuid4()),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                    "run_id": str(second_job.job_id),
                    "candidate_id": str(candidates[0].item_id),
                },
            )


@pytest.mark.asyncio
async def test_lease_loss_after_validation_fences_detection_invocation_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org_id, project_id, _script_id, version_id, run_id, elements = await _create_detection_scope()
    repository = SqlCandidateRepository()
    original_execute = AsyncSession.execute
    lease_lost = False

    async def execute_with_lease_loss(
        session: AsyncSession,
        statement,
        params=None,
        **kwargs,
    ):
        nonlocal lease_lost
        result = await original_execute(
            session,
            statement,
            params=params,
            **kwargs,
        )
        sql = " ".join(str(statement).split())
        if not lease_lost and sql.startswith(
            "SELECT j.status, j.attempt_count, j.lease_owner, "
            "j.lease_expires_at > CURRENT_TIMESTAMP AS lease_active FROM jobs j"
        ):
            lease_lost = True
            await original_execute(
                session,
                sa.text(
                    "UPDATE jobs SET lease_expires_at = '2000-01-01 00:00:00' "
                    "WHERE id = :run_id AND org_id = :org_id "
                    "AND project_id = :project_id"
                ),
                params={
                    "run_id": str(run_id),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                },
            )
        return result

    monkeypatch.setattr(AsyncSession, "execute", execute_with_lease_loss)

    with pytest.raises(DetectionPersistenceError, match="active job lease"):
        await repository.prepare_invocation(
            org_id=org_id,
            project_id=project_id,
            run_id=run_id,
            job_attempt_number=1,
            version_id=version_id,
            element_id=elements[0].element_id,
            requested_model="gemini-3.7-flash",
            input_sha256="a" * 64,
        )

    assert lease_lost is True
    async with session_scope() as session:
        invocation_count = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM detection_invocations "
                    "WHERE org_id = :org_id AND project_id = :project_id "
                    "AND run_id = :run_id"
                ),
                {
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                    "run_id": str(run_id),
                },
            )
        ).scalar_one()
    assert invocation_count == 0


@pytest.mark.asyncio
async def test_lease_expiry_after_candidate_insert_rolls_back_detection_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org_id, project_id, _script_id, version_id, run_id, elements = await _create_detection_scope()
    repository = SqlCandidateRepository()
    prepared = await repository.prepare_invocation(
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        job_attempt_number=1,
        version_id=version_id,
        element_id=elements[0].element_id,
        requested_model="gemini-3.7-flash",
        input_sha256="a" * 64,
    )
    original_execute = AsyncSession.execute
    lease_expired = False

    async def execute_with_post_insert_expiry(
        session: AsyncSession,
        statement,
        params=None,
        **kwargs,
    ):
        nonlocal lease_expired
        result = await original_execute(
            session,
            statement,
            params=params,
            **kwargs,
        )
        sql = " ".join(str(statement).split())
        if not lease_expired and sql.startswith("INSERT INTO detection_candidates"):
            lease_expired = True
            await original_execute(
                session,
                sa.text(
                    "UPDATE jobs SET lease_expires_at = '2000-01-01 00:00:00' "
                    "WHERE id = :run_id AND org_id = :org_id "
                    "AND project_id = :project_id"
                ),
                params={
                    "run_id": str(run_id),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                },
            )
        return result

    monkeypatch.setattr(AsyncSession, "execute", execute_with_post_insert_expiry)

    with pytest.raises(DetectionPersistenceError, match="active job lease"):
        await repository.persist_success(
            invocation_id=prepared.invocation_id,
            org_id=org_id,
            project_id=project_id,
            run_id=run_id,
            version_id=version_id,
            element_id=elements[0].element_id,
            result=_detection_success(elements[0]),
        )

    assert lease_expired is True
    async with session_scope() as session:
        candidate_count = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM detection_candidates WHERE invocation_id = :invocation_id"
                ),
                {"invocation_id": str(prepared.invocation_id)},
            )
        ).scalar_one()
        invocation_status = (
            await session.execute(
                sa.text("SELECT status FROM detection_invocations WHERE id = :invocation_id"),
                {"invocation_id": str(prepared.invocation_id)},
            )
        ).scalar_one()
    assert candidate_count == 0
    assert invocation_status == "pending"


@pytest.mark.parametrize(
    ("field_name", "malformed_value", "expected_model", "expected_response_id", "expected_usage"),
    [
        (
            "model_version",
            object(),
            None,
            "detection-response-1",
            DetectionTokenUsage(20, 12, 32),
        ),
        (
            "response_id",
            object(),
            "gemini-3.7-flash-20260820",
            None,
            DetectionTokenUsage(20, 12, 32),
        ),
        (
            "prompt_token_count",
            "invalid",
            "gemini-3.7-flash-20260820",
            "detection-response-1",
            DetectionTokenUsage(None, 12, 32),
        ),
        (
            "candidates_token_count",
            -1,
            "gemini-3.7-flash-20260820",
            "detection-response-1",
            DetectionTokenUsage(20, None, 32),
        ),
        (
            "total_token_count",
            True,
            "gemini-3.7-flash-20260820",
            "detection-response-1",
            DetectionTokenUsage(20, 12, None),
        ),
    ],
)
@pytest.mark.asyncio
async def test_vertex_detection_preserves_valid_sibling_metadata(
    field_name: str,
    malformed_value: object,
    expected_model: str | None,
    expected_response_id: str | None,
    expected_usage: DetectionTokenUsage,
) -> None:
    response = _response(_candidate_payload())
    target = response if field_name in {"model_version", "response_id"} else response.usage_metadata
    setattr(target, field_name, malformed_value)
    runtime = VertexDetectionRuntime(
        project="clearcut-workspace",
        role_configuration=_configuration(),
        client=FakeClient([response]),
    )

    result = await runtime.detect_element(_element())

    assert isinstance(result, DetectionFailure)
    assert result.error.code == "invalid_response"
    assert result.attempt.status == "invalid_response"
    assert result.attempt.returned_model == expected_model
    assert result.attempt.response_id == expected_response_id
    assert result.attempt.usage == expected_usage
    assert result.attempt.latency_ms >= 0
    assert result.attempt.error == result.error


@pytest.mark.asyncio
async def test_database_rejects_clearance_item_candidate_provenance_splicing() -> None:
    org_id, project_id, script_id, version_id, run_id, elements = await _create_detection_scope()
    repository = SqlCandidateRepository()
    prepared = await repository.prepare_invocation(
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        job_attempt_number=1,
        version_id=version_id,
        element_id=elements[0].element_id,
        requested_model="gemini-3.7-flash",
        input_sha256="4" * 64,
    )
    candidate = (
        await repository.persist_success(
            invocation_id=prepared.invocation_id,
            org_id=org_id,
            project_id=project_id,
            run_id=run_id,
            version_id=version_id,
            element_id=elements[0].element_id,
            result=_detection_success(elements[0]),
        )
    )[0]
    fingerprint = repository.candidate_fingerprint(version_id, candidate)
    other_script_id = uuid4()
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO scripts "
                "(id, org_id, project_id, title, current_slot, created_at) VALUES "
                "(:id, :org_id, :project_id, 'Other Script', 'archived', "
                "CURRENT_TIMESTAMP)"
            ),
            {
                "id": str(other_script_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
            },
        )

    base_values = {
        "org_id": str(org_id),
        "project_id": str(project_id),
        "script_id": str(script_id),
        "version_id": str(version_id),
        "element_id": str(elements[0].element_id),
        "candidate_id": str(candidate.item_id),
        "run_id": str(run_id),
        "fingerprint": fingerprint,
    }
    statement = sa.text(
        "INSERT INTO clearance_items "
        "(id, org_id, project_id, script_id, version_id, element_id, category, "
        "text, status, created_at, detection_candidate_id, detection_run_id, "
        "candidate_fingerprint) VALUES "
        "(:id, :org_id, :project_id, :script_id, :version_id, :element_id, "
        "'products_and_trademarks', 'Apple iPhone', 'unresolved', "
        "CURRENT_TIMESTAMP, :candidate_id, :run_id, :fingerprint)"
    )

    with pytest.raises(IntegrityError):
        async with session_scope() as session:
            await session.execute(
                statement,
                base_values | {"id": str(uuid4()), "fingerprint": "5" * 64},
            )

    with pytest.raises(IntegrityError):
        async with session_scope() as session:
            await session.execute(
                statement,
                base_values | {"id": str(uuid4()), "script_id": str(other_script_id)},
            )


class RecordingJobProgressRepository(SqlJobRepository):
    def __init__(self) -> None:
        self.updates: list[tuple[float, str]] = []

    async def update_progress(self, **kwargs):
        self.updates.append((kwargs["progress"], kwargs["stage"]))
        return await super().update_progress(**kwargs)


@pytest.mark.asyncio
async def test_detection_execution_persists_truthful_non_research_stages() -> None:
    org_id, project_id, _script_id, _version_id, run_id, _elements = await _create_detection_scope()
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO protected_configurations "
                "(id, org_id, lifecycle, policy_version, prompt_version, created_at) "
                "VALUES (:id, :org_id, 'active', 'policy-v1', 'prompt-v1', "
                "CURRENT_TIMESTAMP)"
            ),
            {"id": str(uuid4()), "org_id": str(org_id)},
        )
    jobs = RecordingJobProgressRepository()
    job = await jobs.get(org_id=org_id, project_id=project_id, job_id=run_id)
    assert job is not None
    processor = RunDetectionJobService(
        repository=SqlCandidateRepository(),
        job_repository=jobs,
        runtime=RecordingDetectionRuntime(),
        evaluation=EvaluationService(
            judge=HermeticJudgeAdapter(),
            repository=SqlEvaluationRepository(),
        ),
    )

    await processor(job)

    stages = [stage for _progress, stage in jobs.updates]
    assert stages[0] == "reading_persisted_elements"
    assert "detecting_candidates" in stages
    assert "evaluating_findings" in stages
    assert stages[-1] == "finalizing_detected_findings"
    assert all("research" not in stage for stage in stages)
    assert [progress for progress, _stage in jobs.updates] == sorted(
        progress for progress, _stage in jobs.updates
    )
    persisted = await jobs.get(org_id=org_id, project_id=project_id, job_id=run_id)
    assert persisted is not None
    assert persisted.stage == "finalizing_detected_findings"
    assert persisted.progress < 100

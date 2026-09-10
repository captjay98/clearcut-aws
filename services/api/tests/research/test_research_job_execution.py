import importlib
import importlib.util
import json
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from clearcut.ai.model_roles import GeminiRole, ModelRoleConfiguration
from clearcut.database import session_scope
from clearcut.evaluation.adapters.hermetic_judge import HermeticJudgeAdapter
from clearcut.evaluation.adapters.sql_evaluation_repository import SqlEvaluationRepository
from clearcut.evaluation.application.evaluate import EvaluationService
from clearcut.main import app
from clearcut.operations.adapters.sql_job_repository import SqlJobRepository
from clearcut.operations.application.run_job import JobExecutionError
from clearcut.operations.ports.job_repository import EnqueueJob, JobRecord
from clearcut.research.domain.extraction import (
    ExtractBatchResponse,
    ExtractedPage,
    ExtractRequest,
)
from clearcut.research.domain.queries import ResearchPlan, SearchRequest
from clearcut.research.domain.snapshots import (
    ProviderFailure,
    SearchResponse,
    SearchResultItem,
)
from httpx import ASGITransport, AsyncClient


def _load_type(module_name: str, type_name: str) -> Any:
    assert importlib.util.find_spec(module_name) is not None, (
        f"Task 8 requires {module_name}.{type_name}"
    )
    module = importlib.import_module(module_name)
    value = getattr(module, type_name, None)
    assert value is not None, f"Task 8 requires {module_name}.{type_name}"
    return value


class RecordingPlanner:
    requested_model = "gemini-3.1-flash-lite"

    def __init__(self, plan: ResearchPlan) -> None:
        self.plan = plan
        self.requests: list[Any] = []

    async def plan_research(self, request: Any) -> Any:
        self.requests.append(request)
        usage_type = _load_type(
            "clearcut.research.ports.planner",
            "PlanningTokenUsage",
        )
        metadata_type = _load_type(
            "clearcut.research.ports.planner",
            "PlanningAttemptMetadata",
        )
        success_type = _load_type(
            "clearcut.research.ports.planner",
            "ResearchPlanningSuccess",
        )
        return success_type(
            plan=self.plan,
            metadata=metadata_type(
                status="succeeded",
                requested_model=self.requested_model,
                returned_model="gemini-3.1-flash-lite-20260820",
                response_id="planning-response-1",
                usage=usage_type(
                    input_tokens=12,
                    output_tokens=18,
                    total_tokens=30,
                ),
                latency_ms=14,
                error=None,
            ),
        )


class RecordingSearch:
    def __init__(self, outcomes: list[SearchResponse | ProviderFailure]) -> None:
        self.outcomes = list(outcomes)
        self.requests: list[SearchRequest] = []

    def search(self, request: SearchRequest) -> SearchResponse | ProviderFailure:
        self.requests.append(request)
        return self.outcomes.pop(0)


class RecordingExtract:
    def __init__(self, outcomes: list[ExtractBatchResponse] | None = None) -> None:
        self.outcomes = list(outcomes or [])
        self.requests: list[ExtractRequest] = []

    def extract(self, request: ExtractRequest) -> ExtractBatchResponse:
        self.requests.append(request)
        return self.outcomes.pop(0)


def _synthesized_claim_text(excerpt: str) -> str:
    return f"According to the source, {excerpt}"


class RecordingSynthesizer:
    requested_model = "gemini-3.1-flash-lite"

    def __init__(self, stance: str = "supports") -> None:
        self.stance = stance
        self.requests: list[Any] = []

    async def synthesize_claim(self, request: Any) -> Any:
        self.requests.append(request)
        stance_enum = _load_type(
            "clearcut.research.domain.claims",
            "EvidenceStance",
        )
        usage_type = _load_type(
            "clearcut.research.ports.claim_synthesizer",
            "SynthesisTokenUsage",
        )
        metadata_type = _load_type(
            "clearcut.research.ports.claim_synthesizer",
            "SynthesisAttemptMetadata",
        )
        success_type = _load_type(
            "clearcut.research.ports.claim_synthesizer",
            "ClaimSynthesisSuccess",
        )
        return success_type(
            claim_text=_synthesized_claim_text(request.excerpt),
            stance=stance_enum(self.stance),
            metadata=metadata_type(
                status="succeeded",
                requested_model=self.requested_model,
                returned_model="gemini-3.1-flash-lite-20260820",
                response_id="synthesis-response-1",
                usage=usage_type(
                    input_tokens=8,
                    output_tokens=12,
                    total_tokens=20,
                ),
                latency_ms=9,
                error=None,
            ),
        )


class FailingSynthesizer:
    requested_model = "gemini-3.1-flash-lite"

    def __init__(self, code: str = "provider_unavailable", retryable: bool = True) -> None:
        self.code = code
        self.retryable = retryable
        self.requests: list[Any] = []

    async def synthesize_claim(self, request: Any) -> Any:
        self.requests.append(request)
        error_type = _load_type(
            "clearcut.research.ports.claim_synthesizer",
            "SynthesisSafeError",
        )
        metadata_type = _load_type(
            "clearcut.research.ports.claim_synthesizer",
            "SynthesisAttemptMetadata",
        )
        usage_type = _load_type(
            "clearcut.research.ports.claim_synthesizer",
            "SynthesisTokenUsage",
        )
        failure_type = _load_type(
            "clearcut.research.ports.claim_synthesizer",
            "ClaimSynthesisFailure",
        )
        error = error_type(
            code=self.code,
            message="The claim synthesizer could not complete the request.",
            retryable=self.retryable,
        )
        return failure_type(
            error=error,
            attempt=metadata_type(
                status="failed",
                requested_model=self.requested_model,
                returned_model=None,
                response_id=None,
                usage=usage_type(None, None, None),
                latency_ms=5,
                error=error,
            ),
        )


def _plan() -> ResearchPlan:
    return ResearchPlan(
        objective=("Verify attributable ownership and current status for qualified human review."),
        search_queries=[
            "Example Mark official ownership",
            "Example Mark current registration",
        ],
    )


async def _create_research_scope() -> tuple[JobRecord, UUID, UUID, UUID, UUID]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"origin": "http://test"},
    ) as client:
        registration = await client.post(
            "/api/v1/users",
            json={
                "name": "Research Owner",
                "email": f"research-{uuid4().hex}@example.com",
                "password": "Password123!",
            },
        )
        assert registration.status_code == 201, registration.text
        context = await client.get("/api/v1/session-context")
        actor_id = UUID(context.json()["data"]["userId"])
        organization = await client.post(
            "/api/v1/organizations",
            json={"name": "Research Studio", "slug": f"research-{uuid4().hex[:8]}"},
        )
        org_id = UUID(organization.json()["data"]["orgId"])
        project = await client.post(
            f"/api/v1/organizations/{org_id}/projects",
            json={"title": "Research Execution"},
        )
        project_id = UUID(project.json()["data"]["projectId"])

    script_id = uuid4()
    version_id = uuid4()
    element_id = uuid4()
    item_id = uuid4()
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO scripts "
                "(id, org_id, project_id, title, current_slot, created_at) VALUES "
                "(:id, :org_id, :project_id, 'Research Script', 'current', "
                "CURRENT_TIMESTAMP)"
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
                "'research-test', CURRENT_TIMESTAMP)"
            ),
            {
                "id": str(version_id),
                "script_id": str(script_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "source_hash": "e" * 64,
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO script_elements "
                "(id, version_id, ordinal, element_type, text) VALUES "
                "(:id, :version_id, 1, 'action', :text)"
            ),
            {"id": str(element_id), "version_id": str(version_id), "text": "Example Mark"},
        )
        await session.execute(
            sa.text(
                "INSERT INTO clearance_items "
                "(id, org_id, project_id, script_id, version_id, element_id, "
                "category, text, status, created_at) VALUES "
                "(:id, :org_id, :project_id, :script_id, :version_id, "
                ":element_id, 'products_and_trademarks', 'Example Mark', "
                "'unresolved', CURRENT_TIMESTAMP)"
            ),
            {
                "id": str(item_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "script_id": str(script_id),
                "version_id": str(version_id),
                "element_id": str(element_id),
            },
        )

    jobs = SqlJobRepository()
    enqueued = await jobs.enqueue(
        EnqueueJob(
            org_id=org_id,
            project_id=project_id,
            actor_id=actor_id,
            job_type="research",
            idempotency_key=f"research:{item_id}",
            payload={
                "schemaVersion": 1,
                "target": {"type": "clearance_item", "id": str(item_id)},
            },
            audit_action="research.started",
            target_type="clearance_item",
            target_id=item_id,
        )
    )
    claimed = await jobs.claim(
        org_id=org_id,
        project_id=project_id,
        job_id=enqueued.job.job_id,
        lease_owner="research-execution-test",
    )
    assert claimed is not None
    return claimed, org_id, project_id, version_id, item_id


def _processor(
    planner: RecordingPlanner,
    search: RecordingSearch,
    extract: RecordingExtract,
    synthesizer: Any | None = None,
) -> Any:
    repository_type = _load_type(
        "clearcut.research.adapters.sql_research_repository",
        "SqlResearchRepository",
    )
    service_type = _load_type(
        "clearcut.research.application.run_research_job",
        "RunResearchJobService",
    )
    return service_type(
        repository=repository_type(),
        planner=planner,
        synthesizer=synthesizer or RecordingSynthesizer(),
        search=search,
        extract=extract,
        evaluation=EvaluationService(
            judge=HermeticJudgeAdapter(),
            repository=SqlEvaluationRepository(),
        ),
    )


@pytest.mark.asyncio
async def test_research_job_persists_plan_before_exact_ordered_empty_searches() -> None:
    job, org_id, project_id, version_id, item_id = await _create_research_scope()
    planner = RecordingPlanner(_plan())
    search = RecordingSearch(
        [
            SearchResponse(
                search_id="search-empty-1",
                session_id="session-empty-1",
                results=[],
                duration_ms=10,
            ),
            SearchResponse(
                search_id="search-empty-2",
                session_id="session-empty-2",
                results=[],
                duration_ms=11,
            ),
        ]
    )
    extract = RecordingExtract()

    result = await _processor(planner, search, extract)(job)

    assert len(planner.requests) == 1
    assert planner.requests[0].item_id == item_id
    assert planner.requests[0].version_id == version_id
    assert planner.requests[0].correlation_id == job.correlation_id
    assert [request.query for request in search.requests] == _plan().search_queries
    assert all(request.objective == _plan().objective for request in search.requests)
    assert all(request.correlation_id == job.correlation_id for request in search.requests)
    assert len({request.research_query_id for request in search.requests}) == 2
    assert extract.requests == []
    assert result.summary == {
        "clearanceItemId": str(item_id),
        "scriptVersionId": str(version_id),
        "queryCount": 2,
        "searchAttemptCount": 2,
        "extractAttemptCount": 0,
        "snapshotCount": 0,
        "claimCount": 0,
        "reviewStatus": "unresolved",
        "reason": "no_search_results",
    }

    async with session_scope() as session:
        run = (
            (
                await session.execute(
                    sa.text(
                        "SELECT * FROM research_runs WHERE org_id = :org_id "
                        "AND project_id = :project_id AND job_id = :job_id"
                    ),
                    {
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                        "job_id": str(job.job_id),
                    },
                )
            )
            .mappings()
            .one()
        )
        queries = (
            (
                await session.execute(
                    sa.text(
                        "SELECT * FROM research_queries WHERE run_id = :run_id ORDER BY ordinal"
                    ),
                    {"run_id": str(run["id"])},
                )
            )
            .mappings()
            .all()
        )
        attempts = (
            (
                await session.execute(
                    sa.text(
                        "SELECT operation_kind, status, receipt_id, query_id "
                        "FROM provider_attempts WHERE run_id = :run_id "
                        "ORDER BY created_at, id"
                    ),
                    {"run_id": str(run["id"])},
                )
            )
            .mappings()
            .all()
        )

    assert run["item_id"] == str(item_id)
    assert run["version_id"] == str(version_id)
    assert run["objective"] == _plan().objective
    assert run["status"] == "succeeded"
    assert [row["query"] for row in queries] == _plan().search_queries
    assert [row["ordinal"] for row in queries] == [1, 2]
    assert [row["operation_kind"] for row in attempts] == [
        "planning",
        "search",
        "search",
    ]
    assert [row["status"] for row in attempts] == [
        "succeeded",
        "succeeded",
        "succeeded",
    ]
    assert [row["receipt_id"] for row in attempts[1:]] == [
        "search-empty-1",
        "search-empty-2",
    ]
    assert [row["query_id"] for row in attempts[1:]] == [
        str(queries[0]["id"]),
        str(queries[1]["id"]),
    ]


@pytest.mark.asyncio
async def test_research_job_extracts_only_three_canonical_urls_from_authorizing_search() -> None:
    job, _org_id, _project_id, _version_id, item_id = await _create_research_scope()
    first_results = [
        SearchResultItem(
            url="https://Example.com:443/source#fragment",
            title="Primary source",
            publisher="Example Publisher",
            snippet="Attributable search excerpt.",
        ),
        SearchResultItem(
            url="https://example.com/source",
            title="Duplicate",
            publisher="Example Publisher",
            snippet="Duplicate excerpt.",
        ),
        *[
            SearchResultItem(
                url=f"https://example.com/source-{index}",
                title=f"Source {index}",
                publisher="Example Publisher",
                snippet=f"Attributable excerpt {index}.",
            )
            for index in range(1, 5)
        ],
    ]
    search = RecordingSearch(
        [
            SearchResponse(
                search_id="search-authentic-1",
                session_id="session-authentic-1",
                results=first_results,
                duration_ms=20,
            ),
            SearchResponse(
                search_id="search-authentic-2",
                session_id="session-authentic-2",
                results=[],
                duration_ms=21,
            ),
        ]
    )
    extract = RecordingExtract(
        [
            ExtractBatchResponse(
                extract_id="extract-authentic-1",
                session_id="session-authentic-1",
                results=(
                    ExtractedPage(
                        url="https://example.com/source",
                        title="Primary source",
                        content="Exact attributable extracted excerpt.",
                    ),
                    ExtractedPage(
                        url="https://example.com/source-1",
                        title="Source 1",
                        content="Exact attributable extracted excerpt one.",
                    ),
                    ExtractedPage(
                        url="https://example.com/source-2",
                        title="Source 2",
                        content="Exact attributable extracted excerpt two.",
                    ),
                ),
                errors=(),
                warnings=(),
            )
        ]
    )

    result = await _processor(RecordingPlanner(_plan()), search, extract)(job)

    assert len(extract.requests) == 1
    request = extract.requests[0]
    assert request.urls == [
        "https://example.com/source",
        "https://example.com/source-1",
        "https://example.com/source-2",
    ]
    assert request.research_run_id == search.requests[0].research_run_id
    assert request.research_query_id == search.requests[0].research_query_id
    assert result.summary["clearanceItemId"] == str(item_id)
    assert result.summary["extractAttemptCount"] == 1
    assert result.summary["snapshotCount"] == 8
    assert result.summary["claimCount"] == 3
    assert result.summary["evaluationId"]
    assert result.summary["headlineScore"] is not None
    assert result.summary["judgePassed"] is True
    assert result.summary["reviewStatus"] == "unresolved"
    assert result.summary["reason"] == "human_review_required"

    async with session_scope() as session:
        authorizations = (
            (
                await session.execute(
                    sa.text(
                        "SELECT canonical_url, search_attempt_id FROM search_result_authorizations "
                        "ORDER BY ordinal"
                    )
                )
            )
            .mappings()
            .all()
        )
        snapshots = (
            (
                await session.execute(
                    sa.text(
                        "SELECT origin, provider_attempt_id, authorization_id, excerpt "
                        "FROM source_snapshots ORDER BY retrieved_at, id"
                    )
                )
            )
            .mappings()
            .all()
        )
        claims = (
            (
                await session.execute(
                    sa.text(
                        "SELECT c.*, s.excerpt AS snapshot_excerpt, s.origin "
                        "FROM evidence_claims c JOIN source_snapshots s "
                        "ON s.id = c.snapshot_id ORDER BY c.created_at, c.id"
                    )
                )
            )
            .mappings()
            .all()
        )
        evaluations = (
            (
                await session.execute(
                    sa.text(
                        "SELECT e.id, e.stage, count(v.id) AS verdict_count "
                        "FROM agent_evaluations e JOIN judge_verdicts v "
                        "ON v.evaluation_id = e.id WHERE e.run_id = :job_id "
                        "GROUP BY e.id, e.stage"
                    ),
                    {"job_id": str(job.job_id)},
                )
            )
            .mappings()
            .all()
        )

    assert len(authorizations) == 5
    assert len({row["search_attempt_id"] for row in authorizations}) == 1
    assert len(snapshots) == 8
    assert {row["origin"] for row in snapshots} == {"search", "extract"}
    assert all(row["provider_attempt_id"] for row in snapshots)
    assert all(
        row["authorization_id"] is not None for row in snapshots if row["origin"] == "extract"
    )
    assert all(str(row["excerpt"]).strip() for row in snapshots)
    assert len(claims) == 3
    assert all(row["origin"] == "extract" for row in claims)
    assert all(row["stance"] == "supports" for row in claims)
    assert all(
        row["claim_text"] == _synthesized_claim_text(row["snapshot_excerpt"])
        for row in claims
    )
    assert all(row["claim_text"] != row["snapshot_excerpt"] for row in claims)
    assert all(row["provenance_excerpt"] == row["snapshot_excerpt"] for row in claims)
    assert len(evaluations) == 1
    assert evaluations[0]["stage"] == "research"
    assert evaluations[0]["verdict_count"] == 10


@pytest.mark.asyncio
async def test_search_failure_is_persisted_safely_and_skips_extract() -> None:
    job, _org_id, _project_id, _version_id, _item_id = await _create_research_scope()
    search = RecordingSearch(
        [
            ProviderFailure(
                kind="retryable",
                message="Parallel Search request failed without raw payload data.",
            )
        ]
    )
    extract = RecordingExtract()

    with pytest.raises(JobExecutionError) as raised:
        await _processor(RecordingPlanner(_plan()), search, extract)(job)

    assert raised.value.error.code == "research_search_failed"
    assert raised.value.error.retryable is True
    assert extract.requests == []
    async with session_scope() as session:
        attempt = (
            (
                await session.execute(
                    sa.text(
                        "SELECT operation_kind, status, safe_error FROM provider_attempts "
                        "WHERE operation_kind = 'search'"
                    )
                )
            )
            .mappings()
            .one()
        )
        snapshot_count = (
            await session.execute(sa.text("SELECT count(*) FROM source_snapshots"))
        ).scalar_one()
        claim_count = (
            await session.execute(sa.text("SELECT count(*) FROM evidence_claims"))
        ).scalar_one()

    assert attempt["status"] == "failed"
    safe_error = attempt["safe_error"]
    if isinstance(safe_error, str):
        safe_error = json.loads(safe_error)
    assert safe_error == {
        "code": "retryable",
        "message": "Parallel Search request failed without raw payload data.",
        "retryable": True,
    }
    assert snapshot_count == 0
    assert claim_count == 0


def test_research_processor_is_registered() -> None:
    assert "research" in app.state.job_runner.configured_job_types


class FakeModels:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def generate_content(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.response


@pytest.mark.asyncio
async def test_vertex_research_planner_returns_bounded_plan_and_authentic_metadata() -> None:
    planner_type = _load_type(
        "clearcut.research.adapters.vertex_planner",
        "VertexResearchPlanner",
    )
    request_type = _load_type(
        "clearcut.research.ports.planner",
        "ResearchPlanningRequest",
    )
    success_type = _load_type(
        "clearcut.research.ports.planner",
        "ResearchPlanningSuccess",
    )
    response = SimpleNamespace(
        text=json.dumps(
            {
                "objective": _plan().objective,
                "search_queries": _plan().search_queries,
            }
        ),
        model_version="gemini-3.1-flash-lite-20260820",
        response_id="planning-response-1",
        usage_metadata=SimpleNamespace(
            prompt_token_count=12,
            candidates_token_count=18,
            total_token_count=30,
        ),
    )
    models = FakeModels(response)
    planner = planner_type(
        project="clearcut-workspace",
        role_configuration=ModelRoleConfiguration(
            role=GeminiRole.RESEARCH_PLANNING,
            model="gemini-3.1-flash-lite",
            environment_variable="CLEARCUT_GEMINI_RESEARCH_MODEL",
            overridden=False,
        ),
        client=SimpleNamespace(models=models),
    )
    request = request_type(
        item_id=uuid4(),
        version_id=uuid4(),
        category="products_and_trademarks",
        text="Example Mark",
        correlation_id=uuid4(),
        research_run_id=uuid4(),
    )

    result = await planner.plan_research(request)

    assert isinstance(result, success_type)
    assert result.plan == _plan()
    assert result.metadata.requested_model == "gemini-3.1-flash-lite"
    assert result.metadata.returned_model == "gemini-3.1-flash-lite-20260820"
    assert result.metadata.response_id == "planning-response-1"
    assert result.metadata.usage.total_tokens == 30
    assert len(models.calls) == 1
    assert models.calls[0]["model"] == "gemini-3.1-flash-lite"


@pytest.mark.asyncio
async def test_retry_creates_attempt_scoped_research_run() -> None:
    job, org_id, project_id, _version_id, _item_id = await _create_research_scope()
    first_search = RecordingSearch(
        [
            ProviderFailure(
                kind="retryable",
                message="Parallel Search request failed safely.",
            )
        ]
    )

    with pytest.raises(JobExecutionError) as raised:
        await _processor(
            RecordingPlanner(_plan()),
            first_search,
            RecordingExtract(),
        )(job)

    assert job.lease_owner is not None
    assert job.actor_id is not None
    jobs = SqlJobRepository()
    failed = await jobs.fail(
        org_id=org_id,
        project_id=project_id,
        job_id=job.job_id,
        attempt_number=job.attempt_count,
        lease_owner=job.lease_owner,
        error=raised.value.error,
    )
    assert failed.status.value == "failed"
    await jobs.retry(
        org_id=org_id,
        project_id=project_id,
        job_id=job.job_id,
        actor_id=job.actor_id,
    )
    replacement = await jobs.claim(
        org_id=org_id,
        project_id=project_id,
        job_id=job.job_id,
        lease_owner="research-retry-test",
    )
    assert replacement is not None
    assert replacement.attempt_count == 2

    result = await _processor(
        RecordingPlanner(_plan()),
        RecordingSearch(
            [
                SearchResponse(
                    search_id="retry-search-1",
                    session_id="retry-session-1",
                    results=[],
                    duration_ms=1,
                ),
                SearchResponse(
                    search_id="retry-search-2",
                    session_id="retry-session-2",
                    results=[],
                    duration_ms=1,
                ),
            ]
        ),
        RecordingExtract(),
    )(replacement)

    assert result.summary["reason"] == "no_search_results"
    async with session_scope() as session:
        runs = (
            (
                await session.execute(
                    sa.text(
                        "SELECT job_attempt_number, status FROM research_runs "
                        "WHERE job_id = :job_id ORDER BY job_attempt_number"
                    ),
                    {"job_id": str(job.job_id)},
                )
            )
            .mappings()
            .all()
        )
    assert [(row["job_attempt_number"], row["status"]) for row in runs] == [
        (1, "failed"),
        (2, "succeeded"),
    ]


@pytest.mark.asyncio
async def test_extract_finalization_rejects_different_authorizing_search_attempt() -> None:
    job, org_id, project_id, _version_id, item_id = await _create_research_scope()
    assert job.lease_owner is not None
    repository_type = _load_type(
        "clearcut.research.adapters.sql_research_repository",
        "SqlResearchRepository",
    )
    persistence_error = _load_type(
        "clearcut.research.adapters.sql_research_repository",
        "ResearchPersistenceError",
    )
    planning_request_type = _load_type(
        "clearcut.research.ports.planner",
        "ResearchPlanningRequest",
    )
    repository = repository_type()
    research_input = await repository.load_input(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
    )
    prepared = await repository.prepare_planning(
        org_id=org_id,
        project_id=project_id,
        job_id=job.job_id,
        job_attempt_number=job.attempt_count,
        lease_owner=job.lease_owner,
        correlation_id=job.correlation_id,
        research_input=research_input,
        requested_model="gemini-3.1-flash-lite",
        input_sha256="f" * 64,
    )
    planner = RecordingPlanner(_plan())
    planning_result = await planner.plan_research(
        planning_request_type(
            item_id=item_id,
            version_id=research_input.version_id,
            category=research_input.category,
            text=research_input.text,
            correlation_id=job.correlation_id,
            research_run_id=prepared.run_id,
        )
    )
    queries = await repository.persist_planning_success(
        org_id=org_id,
        project_id=project_id,
        job_id=job.job_id,
        job_attempt_number=job.attempt_count,
        lease_owner=job.lease_owner,
        run_id=prepared.run_id,
        attempt_id=prepared.attempt_id,
        result=planning_result,
    )
    query = queries[0]
    search_attempt_ids: list[UUID] = []
    for ordinal in (1, 2):
        search_attempt = await repository.prepare_search(
            org_id=org_id,
            project_id=project_id,
            job_id=job.job_id,
            job_attempt_number=job.attempt_count,
            lease_owner=job.lease_owner,
            correlation_id=job.correlation_id,
            run_id=prepared.run_id,
            item_id=item_id,
            query=query,
        )
        search_attempt_ids.append(search_attempt.attempt_id)
        await repository.persist_search_success(
            org_id=org_id,
            project_id=project_id,
            job_id=job.job_id,
            job_attempt_number=job.attempt_count,
            lease_owner=job.lease_owner,
            run_id=prepared.run_id,
            item_id=item_id,
            query_id=query.query_id,
            attempt_id=search_attempt.attempt_id,
            result=SearchResponse(
                search_id=f"search-{ordinal}",
                session_id=f"session-{ordinal}",
                results=[
                    SearchResultItem(
                        url="https://example.com/source",
                        title="Source",
                        publisher="Publisher",
                        snippet="Search excerpt.",
                    )
                ],
                duration_ms=1,
            ),
        )

    extract_attempt = await repository.prepare_extract(
        org_id=org_id,
        project_id=project_id,
        job_id=job.job_id,
        job_attempt_number=job.attempt_count,
        lease_owner=job.lease_owner,
        correlation_id=job.correlation_id,
        run_id=prepared.run_id,
        item_id=item_id,
        query_id=query.query_id,
        search_attempt_id=search_attempt_ids[0],
        urls=["https://example.com/source"],
    )
    with pytest.raises(persistence_error):
        await repository.persist_extract_success(
            org_id=org_id,
            project_id=project_id,
            job_id=job.job_id,
            job_attempt_number=job.attempt_count,
            lease_owner=job.lease_owner,
            run_id=prepared.run_id,
            item_id=item_id,
            query_id=query.query_id,
            search_attempt_id=search_attempt_ids[1],
            attempt_id=extract_attempt.attempt_id,
            result=ExtractBatchResponse(
                extract_id="extract-swapped",
                session_id="session-2",
                results=(
                    ExtractedPage(
                        url="https://example.com/source",
                        title="Source",
                        content="Extracted excerpt.",
                    ),
                ),
                errors=(),
                warnings=(),
            ),
        )


@pytest.mark.asyncio
async def test_extract_persistence_bounds_excerpts_and_redacts_diagnostics() -> None:
    job, _org_id, _project_id, _version_id, _item_id = await _create_research_scope()
    error_type = _load_type(
        "clearcut.research.domain.extraction",
        "ExtractedPageError",
    )
    unsafe_marker = "raw-provider-secret"
    search = RecordingSearch(
        [
            SearchResponse(
                search_id="search-safe-1",
                session_id="session-safe-1",
                results=[
                    SearchResultItem(
                        url="https://example.com/source",
                        title="Source",
                        publisher="Publisher",
                        snippet="Search excerpt.",
                    )
                ],
                duration_ms=1,
            ),
            SearchResponse(
                search_id="search-safe-2",
                session_id="session-safe-2",
                results=[],
                duration_ms=1,
            ),
        ]
    )
    extract = RecordingExtract(
        [
            ExtractBatchResponse(
                extract_id="extract-safe-1",
                session_id="session-safe-1",
                results=(
                    ExtractedPage(
                        url="https://example.com/source",
                        title="Source",
                        content="Attributable excerpt. " + ("x" * 5000) + unsafe_marker,
                    ),
                ),
                errors=(
                    error_type(
                        url="https://example.com/source",
                        error_kind="blocked",
                        message=unsafe_marker,
                    ),
                ),
                warnings=(unsafe_marker,),
            )
        ]
    )

    await _processor(RecordingPlanner(_plan()), search, extract)(job)

    async with session_scope() as session:
        excerpt = (
            await session.execute(
                sa.text("SELECT excerpt FROM source_snapshots WHERE origin = 'extract'")
            )
        ).scalar_one()
        warnings = (
            await session.execute(
                sa.text("SELECT warnings FROM provider_attempts WHERE operation_kind = 'extract'")
            )
        ).scalar_one()
    if isinstance(warnings, str):
        warnings = json.loads(warnings)
    assert len(excerpt) <= 4000
    assert unsafe_marker not in excerpt
    assert warnings == ["provider_warning_count:1", "extract_error:blocked"]


@pytest.mark.asyncio
async def test_stale_research_worker_is_fenced_and_replacement_attempt_completes() -> None:
    job, org_id, project_id, _version_id, item_id = await _create_research_scope()
    assert job.lease_owner is not None
    assert job.actor_id is not None
    repository_type = _load_type(
        "clearcut.research.adapters.sql_research_repository",
        "SqlResearchRepository",
    )
    persistence_error = _load_type(
        "clearcut.research.adapters.sql_research_repository",
        "ResearchPersistenceError",
    )
    planning_request_type = _load_type(
        "clearcut.research.ports.planner",
        "ResearchPlanningRequest",
    )
    repository = repository_type()
    research_input = await repository.load_input(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
    )
    prepared = await repository.prepare_planning(
        org_id=org_id,
        project_id=project_id,
        job_id=job.job_id,
        job_attempt_number=job.attempt_count,
        lease_owner=job.lease_owner,
        correlation_id=job.correlation_id,
        research_input=research_input,
        requested_model="gemini-3.1-flash-lite",
        input_sha256="e" * 64,
    )
    planner = RecordingPlanner(_plan())
    planning_result = await planner.plan_research(
        planning_request_type(
            item_id=item_id,
            version_id=research_input.version_id,
            category=research_input.category,
            text=research_input.text,
            correlation_id=job.correlation_id,
            research_run_id=prepared.run_id,
        )
    )

    async with session_scope() as session:
        await session.execute(
            sa.text("UPDATE jobs SET lease_expires_at = :expired WHERE id = :job_id"),
            {"expired": "2000-01-01T00:00:00+00:00", "job_id": str(job.job_id)},
        )
    jobs = SqlJobRepository()
    recovered = await jobs.recover_interrupted_local_jobs()
    assert [record.job_id for record in recovered] == [job.job_id]
    await jobs.retry(
        org_id=org_id,
        project_id=project_id,
        job_id=job.job_id,
        actor_id=job.actor_id,
    )
    replacement = await jobs.claim(
        org_id=org_id,
        project_id=project_id,
        job_id=job.job_id,
        lease_owner="research-stale-replacement",
    )
    assert replacement is not None
    assert replacement.attempt_count == 2

    with pytest.raises(persistence_error):
        await repository.persist_planning_success(
            org_id=org_id,
            project_id=project_id,
            job_id=job.job_id,
            job_attempt_number=job.attempt_count,
            lease_owner=job.lease_owner,
            run_id=prepared.run_id,
            attempt_id=prepared.attempt_id,
            result=planning_result,
        )

    result = await _processor(
        RecordingPlanner(_plan()),
        RecordingSearch(
            [
                SearchResponse(
                    search_id="replacement-search-1",
                    session_id="replacement-session-1",
                    results=[],
                    duration_ms=1,
                ),
                SearchResponse(
                    search_id="replacement-search-2",
                    session_id="replacement-session-2",
                    results=[],
                    duration_ms=1,
                ),
            ]
        ),
        RecordingExtract(),
    )(replacement)
    assert result.summary["reason"] == "no_search_results"

    async with session_scope() as session:
        stale_attempt = (
            (
                await session.execute(
                    sa.text(
                        "SELECT status, safe_error FROM provider_attempts WHERE id = :attempt_id"
                    ),
                    {"attempt_id": str(prepared.attempt_id)},
                )
            )
            .mappings()
            .one()
        )
        stale_run = (
            (
                await session.execute(
                    sa.text("SELECT status, safe_error FROM research_runs WHERE id = :run_id"),
                    {"run_id": str(prepared.run_id)},
                )
            )
            .mappings()
            .one()
        )
        stale_query_count = (
            await session.execute(
                sa.text("SELECT count(*) FROM research_queries WHERE run_id = :run_id"),
                {"run_id": str(prepared.run_id)},
            )
        ).scalar_one()
    assert stale_attempt["status"] == "failed"
    assert stale_run["status"] == "failed"
    for safe_error in (stale_attempt["safe_error"], stale_run["safe_error"]):
        if isinstance(safe_error, str):
            safe_error = json.loads(safe_error)
        assert safe_error == {
            "code": "interrupted",
            "message": "A replacement job attempt superseded this research execution.",
            "retryable": True,
        }
    assert stale_query_count == 0


def _search_results_for_extract_intent() -> list[SearchResultItem]:
    return [
        SearchResultItem(
            url=f"https://example.com/source-{index}",
            title=f"Source {index}",
            publisher="Example Publisher",
            snippet=f"Attributable excerpt {index}.",
        )
        for index in range(1, 5)
    ]


@pytest.mark.asyncio
async def test_extract_finalization_rejects_url_outside_persisted_target_subset() -> None:
    job, _org_id, _project_id, _version_id, _item_id = await _create_research_scope()
    search = RecordingSearch(
        [
            SearchResponse(
                search_id="search-targets-1",
                session_id="session-targets-1",
                results=_search_results_for_extract_intent(),
                duration_ms=1,
            ),
            SearchResponse(
                search_id="search-targets-2",
                session_id="session-targets-2",
                results=[],
                duration_ms=1,
            ),
        ]
    )
    extract = RecordingExtract(
        [
            ExtractBatchResponse(
                extract_id="extract-targets-1",
                session_id="session-targets-1",
                results=(
                    ExtractedPage(
                        url="https://example.com/source-4",
                        title="Unselected source",
                        content="Unselected attributable excerpt.",
                    ),
                ),
                errors=(),
                warnings=(),
            )
        ]
    )

    with pytest.raises(JobExecutionError) as raised:
        await _processor(RecordingPlanner(_plan()), search, extract)(job)

    assert raised.value.error.code == "research_persistence_failed"
    async with session_scope() as session:
        extract_snapshot_count = (
            await session.execute(
                sa.text("SELECT count(*) FROM source_snapshots WHERE origin = 'extract'")
            )
        ).scalar_one()
        claim_count = (
            await session.execute(sa.text("SELECT count(*) FROM evidence_claims"))
        ).scalar_one()
    assert extract_snapshot_count == 0
    assert claim_count == 0


@pytest.mark.asyncio
async def test_extract_finalization_rejects_mismatched_search_session() -> None:
    job, _org_id, _project_id, _version_id, _item_id = await _create_research_scope()
    search = RecordingSearch(
        [
            SearchResponse(
                search_id="search-session-1",
                session_id="session-authoritative",
                results=_search_results_for_extract_intent(),
                duration_ms=1,
            ),
            SearchResponse(
                search_id="search-session-2",
                session_id="session-second",
                results=[],
                duration_ms=1,
            ),
        ]
    )
    extract = RecordingExtract(
        [
            ExtractBatchResponse(
                extract_id="extract-session-1",
                session_id="session-unrelated",
                results=(
                    ExtractedPage(
                        url="https://example.com/source-1",
                        title="Selected source",
                        content="Selected attributable excerpt.",
                    ),
                ),
                errors=(),
                warnings=(),
            )
        ]
    )

    with pytest.raises(JobExecutionError) as raised:
        await _processor(RecordingPlanner(_plan()), search, extract)(job)

    assert raised.value.error.code == "research_persistence_failed"
    async with session_scope() as session:
        extract_snapshot_count = (
            await session.execute(
                sa.text("SELECT count(*) FROM source_snapshots WHERE origin = 'extract'")
            )
        ).scalar_one()
    assert extract_snapshot_count == 0



def _extract_success_flow() -> tuple[RecordingSearch, RecordingExtract]:
    search = RecordingSearch(
        [
            SearchResponse(
                search_id="search-synth-1",
                session_id="session-synth-1",
                results=[
                    SearchResultItem(
                        url="https://example.com/source-1",
                        title="Source 1",
                        publisher="Example Publisher",
                        snippet="Attributable excerpt one.",
                    ),
                ],
                duration_ms=20,
            ),
            SearchResponse(
                search_id="search-synth-2",
                session_id="session-synth-2",
                results=[],
                duration_ms=21,
            ),
        ]
    )
    extract = RecordingExtract(
        [
            ExtractBatchResponse(
                extract_id="extract-synth-1",
                session_id="session-synth-1",
                results=(
                    ExtractedPage(
                        url="https://example.com/source-1",
                        title="Source 1",
                        content="Exact attributable extracted excerpt one.",
                    ),
                ),
                errors=(),
                warnings=(),
            )
        ]
    )
    return search, extract


@pytest.mark.asyncio
async def test_synthesis_failure_produces_typed_retryable_job_failure_without_claims() -> None:
    job, org_id, project_id, _version_id, item_id = await _create_research_scope()
    search, extract = _extract_success_flow()
    synthesizer = FailingSynthesizer(code="provider_unavailable", retryable=True)

    with pytest.raises(JobExecutionError) as raised:
        await _processor(RecordingPlanner(_plan()), search, extract, synthesizer)(job)

    assert raised.value.error.code == "research_synthesis_failed"
    assert raised.value.error.retryable is True
    assert len(synthesizer.requests) == 1
    assert synthesizer.requests[0].item_id == item_id
    assert synthesizer.requests[0].excerpt == "Exact attributable extracted excerpt one."

    async with session_scope() as session:
        run = (
            (
                await session.execute(
                    sa.text(
                        "SELECT status FROM research_runs WHERE org_id = :org_id "
                        "AND project_id = :project_id AND job_id = :job_id"
                    ),
                    {
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                        "job_id": str(job.job_id),
                    },
                )
            )
            .mappings()
            .one()
        )
        claim_count = (
            await session.execute(sa.text("SELECT count(*) FROM evidence_claims"))
        ).scalar_one()
        evaluation_count = (
            await session.execute(
                sa.text("SELECT count(*) FROM agent_evaluations WHERE run_id = :job_id"),
                {"job_id": str(job.job_id)},
            )
        ).scalar_one()

    assert run["status"] == "failed"
    assert claim_count == 0
    assert evaluation_count == 0

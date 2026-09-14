"""Integration tests for Bounded Strands Research Workflow."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from clearcut.database import session_scope
from clearcut.evaluation.adapters.hermetic_judge import HermeticJudgeAdapter
from clearcut.evaluation.adapters.sql_evaluation_repository import SqlEvaluationRepository
from clearcut.evaluation.application.evaluate import EvaluationService
from clearcut.operations.adapters.sql_job_repository import SqlJobRepository
from clearcut.operations.ports.job_repository import EnqueueJob
from clearcut.research.adapters.sql_research_repository import SqlResearchRepository
from clearcut.research.adapters.sql_step_receipt_repository import SqlStepReceiptRepository
from clearcut.research.adapters.strands_workflow import (
    ScriptedMockStrandsModel,
    StrandsResearchWorkflow,
)
from clearcut.research.application.run_research_job import RunResearchJobService
from clearcut.research.domain.claims import EvidenceStance
from clearcut.research.domain.extraction import ExtractBatchResponse, ExtractedPage
from clearcut.research.domain.queries import ResearchPlan
from clearcut.research.domain.snapshots import SearchResponse, SearchResultItem
from clearcut.research.ports.claim_synthesizer import (
    ClaimSynthesisSuccess,
    ClaimSynthesizerPort,
    SynthesisAttemptMetadata,
    SynthesisTokenUsage,
)
from clearcut.research.ports.planner import (
    PlanningAttemptMetadata,
    PlanningTokenUsage,
    ResearchPlannerPort,
    ResearchPlanningSuccess,
)
from clearcut.research.ports.workflow import ResearchWorkflowContext


class DummyPlanner(ResearchPlannerPort):
    requested_model = "test-planner"

    async def plan_research(self, request: Any) -> Any:
        return ResearchPlanningSuccess(
            plan=ResearchPlan(
                "Investigate Nike mark clearance", ["nike mark clearance", "nike film product"]
            ),
            metadata=PlanningAttemptMetadata(
                status="succeeded",
                requested_model="test-planner",
                returned_model="test-planner-v1",
                response_id="plan-1",
                usage=PlanningTokenUsage(10, 10, 20),
                latency_ms=10,
                error=None,
            ),
        )


class DummySynthesizer(ClaimSynthesizerPort):
    requested_model = "test-synthesizer"

    async def synthesize_claim(self, request: Any) -> Any:
        return ClaimSynthesisSuccess(
            claim_text=f"Synthesized claim from {request.url}: {request.excerpt[:50]}",
            stance=EvidenceStance.SUPPORTS,
            metadata=SynthesisAttemptMetadata(
                status="succeeded",
                requested_model="test-synthesizer",
                returned_model="test-synthesizer-v1",
                response_id="synth-1",
                usage=SynthesisTokenUsage(10, 10, 20),
                latency_ms=10,
                error=None,
            ),
        )


class DummySearch:
    def search(self, request: Any) -> SearchResponse:
        return SearchResponse(
            search_id="search-123",
            session_id="session-456",
            results=[
                SearchResultItem(
                    url="https://example.gov/trademark/nike",
                    title="Nike Trademark Details",
                    publisher="USPTO Official",
                    snippet="Official registration records for trademark Nike footwear and apparel.",
                ),
                SearchResultItem(
                    url="https://example.com/shoes/review",
                    title="Shoe Review Magazine",
                    publisher="Sneaker World",
                    snippet="Review of shoes in popular cinematic releases.",
                ),
            ],
        )


class DummyExtract:
    def extract(self, request: Any) -> ExtractBatchResponse:
        return ExtractBatchResponse(
            extract_id="extract-123",
            session_id="session-456",
            results=tuple(
                ExtractedPage(
                    url=u,
                    title="Nike Mark Details",
                    content="Detailed excerpt regarding official registration and cinematic use of the mark.",
                )
                for u in request.urls
            ),
            errors=(),
            warnings=(),
        )


async def _seed_test_project_and_item() -> tuple[UUID, UUID, UUID, UUID, UUID]:
    org_id = uuid4()
    project_id = uuid4()
    script_id = uuid4()
    version_id = uuid4()
    item_id = uuid4()
    element_id = uuid4()

    user_id = uuid4()
    async with session_scope() as session:
        await session.execute(
            sa.text("INSERT INTO users (id, email, created_at) VALUES (:id, :email, :created_at)"),
            {
                "id": str(user_id),
                "email": f"user-{user_id.hex[:8]}@example.com",
                "created_at": datetime.now(UTC),
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO organizations (id, name, slug, created_at) "
                "VALUES (:id, :name, :slug, :created_at)"
            ),
            {
                "id": str(org_id),
                "name": "Studio",
                "slug": f"studio-{org_id.hex[:8]}",
                "created_at": datetime.now(UTC),
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO protected_configurations "
                "(id, org_id, lifecycle, policy_version, prompt_version, created_at) "
                "VALUES (:id, :org_id, 'active', 'policy-v1', 'prompt-v1', CURRENT_TIMESTAMP)"
            ),
            {"id": str(uuid4()), "org_id": str(org_id)},
        )
        await session.execute(
            sa.text(
                "INSERT INTO projects (id, org_id, title, created_at) "
                "VALUES (:id, :org_id, 'Title', :created_at)"
            ),
            {"id": str(project_id), "org_id": str(org_id), "created_at": datetime.now(UTC)},
        )
        await session.execute(
            sa.text(
                "INSERT INTO scripts (id, org_id, project_id, title, current_slot, created_at) "
                "VALUES (:id, :org_id, :project_id, 'Script', 'current', :created_at)"
            ),
            {
                "id": str(script_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "created_at": datetime.now(UTC),
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO script_versions (id, script_id, org_id, project_id, ordinal, source_hash, parser_version, created_at) "
                "VALUES (:id, :script_id, :org_id, :project_id, 1, :source_hash, 'test', :created_at)"
            ),
            {
                "id": str(version_id),
                "script_id": str(script_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "source_hash": "c" * 64,
                "created_at": datetime.now(UTC),
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO script_elements (id, version_id, ordinal, element_type, text) "
                "VALUES (:id, :version_id, 1, 'action', 'John ties his Nike shoes.')"
            ),
            {"id": str(element_id), "version_id": str(version_id)},
        )
        await session.execute(
            sa.text(
                "INSERT INTO clearance_items (id, org_id, project_id, script_id, version_id, element_id, category, text, status, created_at) "
                "VALUES (:id, :org_id, :project_id, :script_id, :version_id, :element_id, 'products_and_trademarks', 'Nike Shoes', 'unresolved', :created_at)"
            ),
            {
                "id": str(item_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "script_id": str(script_id),
                "version_id": str(version_id),
                "element_id": str(element_id),
                "created_at": datetime.now(UTC),
            },
        )
    return org_id, project_id, script_id, version_id, item_id, user_id


@pytest.mark.asyncio
async def test_strands_executes_multi_step_research():
    org_id, project_id, _, version_id, item_id, user_id = await _seed_test_project_and_item()

    jobs = SqlJobRepository()
    enqueued = await jobs.enqueue(
        EnqueueJob(
            org_id=org_id,
            project_id=project_id,
            actor_id=user_id,
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
        lease_owner="test-worker",
    )
    assert claimed is not None

    run_id = uuid4()
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO research_runs (id, org_id, project_id, item_id, status, created_at, "
                "job_id, version_id, job_attempt_number, lease_owner, correlation_id) "
                "VALUES (:id, :org_id, :project_id, :item_id, 'running', :created_at, "
                ":job_id, :version_id, :job_attempt_number, :lease_owner, :correlation_id)"
            ),
            {
                "id": str(run_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "item_id": str(item_id),
                "created_at": datetime.now(UTC),
                "job_id": str(claimed.job_id),
                "version_id": str(version_id),
                "job_attempt_number": claimed.attempt_count,
                "lease_owner": claimed.lease_owner,
                "correlation_id": str(claimed.correlation_id),
            },
        )

    repository = SqlResearchRepository()
    receipt_repo = SqlStepReceiptRepository()
    eval_repo = SqlEvaluationRepository()
    judge = HermeticJudgeAdapter()
    evaluation = EvaluationService(repository=eval_repo, judge=judge)

    mock_model = ScriptedMockStrandsModel(
        [
            {"type": "tool", "name": "read_item_context", "input": {}},
            {
                "type": "tool",
                "name": "plan_queries",
                "input": {"queries": ["nike shoe clearance", "nike logo movie"]},
            },
            {"type": "tool", "name": "search_evidence", "input": {"query": "nike shoe clearance"}},
            {
                "type": "tool",
                "name": "extract_admitted_source",
                "input": {"url": "https://example.gov/trademark/nike"},
            },
            {"type": "tool", "name": "evaluate_source_evidence", "input": {}},
            {"type": "tool", "name": "read_research_progress", "input": {}},
            {"type": "text", "text": "Research synthesis completed."},
        ]
    )

    workflow = StrandsResearchWorkflow(
        repository=repository,
        step_receipt_repo=receipt_repo,
        search=DummySearch(),
        extract=DummyExtract(),
        synthesizer=DummySynthesizer(),
        evaluation=evaluation,
        model=mock_model,
    )

    context = ResearchWorkflowContext(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        version_id=version_id,
        run_id=run_id,
        job_id=claimed.job_id,
        attempt_number=claimed.attempt_count,
        lease_owner="test-worker",
        category="products_and_trademarks",
        item_text="Nike Shoes",
        correlation_id=claimed.correlation_id,
        policy_version=1,
        prompt_version=1,
    )

    result = await workflow.execute_research(context)

    assert result.status == "succeeded"
    assert result.review_status == "unresolved"
    assert result.reason == "human_review_required"
    assert result.cleared is False
    assert result.needs_human_review is True
    assert result.search_attempt_count >= 1
    assert result.snapshot_count >= 1
    assert result.claim_count >= 1
    assert result.step_count == 6

    # Verify ordered step receipts in DB
    receipts = await receipt_repo.list_receipts_for_run(
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
    )
    assert len(receipts) == 6
    assert [r.step_index for r in receipts] == [0, 1, 2, 3, 4, 5]
    assert [r.tool_name for r in receipts] == [
        "read_item_context",
        "plan_queries",
        "search_evidence",
        "extract_admitted_source",
        "evaluate_source_evidence",
        "read_research_progress",
    ]
    for r in receipts:
        assert len(r.tool_input_hash) == 64
        assert len(r.tool_output_hash) == 64
        assert r.status == "succeeded"


@pytest.mark.asyncio
async def test_run_research_job_delegates_to_strands_workflow():
    org_id, project_id, _, version_id, item_id, user_id = await _seed_test_project_and_item()

    jobs = SqlJobRepository()
    enqueued = await jobs.enqueue(
        EnqueueJob(
            org_id=org_id,
            project_id=project_id,
            actor_id=user_id,
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
        lease_owner="test-strands-worker",
    )
    assert claimed is not None

    repository = SqlResearchRepository()
    receipt_repo = SqlStepReceiptRepository()
    eval_repo = SqlEvaluationRepository()
    judge = HermeticJudgeAdapter()
    evaluation = EvaluationService(repository=eval_repo, judge=judge)

    mock_model = ScriptedMockStrandsModel(
        [
            {"type": "tool", "name": "read_item_context", "input": {}},
            {"type": "tool", "name": "search_evidence", "input": {"query": "nike shoes"}},
            {"type": "tool", "name": "evaluate_source_evidence", "input": {}},
            {"type": "text", "text": "Finished researching item."},
        ]
    )

    workflow = StrandsResearchWorkflow(
        repository=repository,
        step_receipt_repo=receipt_repo,
        search=DummySearch(),
        extract=DummyExtract(),
        synthesizer=DummySynthesizer(),
        evaluation=evaluation,
        model=mock_model,
    )

    service = RunResearchJobService(
        repository=repository,
        planner=DummyPlanner(),
        synthesizer=DummySynthesizer(),
        search=DummySearch(),
        extract=DummyExtract(),
        evaluation=evaluation,
        workflow=workflow,
    )

    execution_result = await service(claimed)
    summary = execution_result.summary
    assert summary["clearanceItemId"] == str(item_id)
    assert summary["reviewStatus"] == "unresolved"
    assert summary["stepCount"] == 3


@pytest.mark.asyncio
async def test_strands_workflow_fails_when_search_is_skipped():
    """Verify workflow marks run as failed and returns missing_mandatory_search if no search was run."""
    org_id, project_id, _, version_id, item_id, user_id = await _seed_test_project_and_item()

    run_id = uuid4()
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO research_runs (id, org_id, project_id, item_id, status, created_at, "
                "version_id, job_attempt_number, lease_owner, correlation_id) "
                "VALUES (:id, :org_id, :project_id, :item_id, 'running', :created_at, "
                ":version_id, 1, 'worker-1', :correlation_id)"
            ),
            {
                "id": str(run_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "item_id": str(item_id),
                "created_at": datetime.now(UTC),
                "version_id": str(version_id),
                "correlation_id": str(uuid4()),
            },
        )

    repository = SqlResearchRepository()
    receipt_repo = SqlStepReceiptRepository()
    eval_repo = SqlEvaluationRepository()
    judge = HermeticJudgeAdapter()
    evaluation = EvaluationService(repository=eval_repo, judge=judge)

    # Model only reads context and does not run search
    mock_model = ScriptedMockStrandsModel(
        [
            {"type": "tool", "name": "read_item_context", "input": {}},
            {"type": "text", "text": "Skipped search."},
        ]
    )

    workflow = StrandsResearchWorkflow(
        repository=repository,
        step_receipt_repo=receipt_repo,
        search=DummySearch(),
        extract=DummyExtract(),
        synthesizer=DummySynthesizer(),
        evaluation=evaluation,
        model=mock_model,
    )

    context = ResearchWorkflowContext(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        version_id=version_id,
        run_id=run_id,
        category="products_and_trademarks",
        item_text="Nike Shoes",
    )

    result = await workflow.execute_research(context)
    assert result.status == "failed"
    assert result.error == "missing_mandatory_search"
    assert result.cleared is False
    assert result.needs_human_review is True
    assert result.review_status == "unresolved"

    # Verify research_runs was updated to failed
    async with session_scope() as session:
        run_row = (
            await session.execute(
                sa.text("SELECT status FROM research_runs WHERE id = :run_id"),
                {"run_id": str(run_id)},
            )
        ).first()
        assert run_row is not None
        assert run_row[0] == "failed"


@pytest.mark.asyncio
async def test_strands_workflow_fails_when_citation_unauthenticated():
    """Verify workflow fails when claims cite snapshots not belonging to the scoped run."""
    org_id, project_id, _, version_id, item_id, user_id = await _seed_test_project_and_item()

    jobs = SqlJobRepository()
    enqueued = await jobs.enqueue(
        EnqueueJob(
            org_id=org_id,
            project_id=project_id,
            actor_id=user_id,
            job_type="research",
            idempotency_key=f"research:{item_id}:unauth",
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
        lease_owner="test-worker",
    )
    assert claimed is not None

    run_id = uuid4()
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO research_runs (id, org_id, project_id, item_id, status, created_at, "
                "job_id, version_id, job_attempt_number, lease_owner, correlation_id) "
                "VALUES (:id, :org_id, :project_id, :item_id, 'running', :created_at, "
                ":job_id, :version_id, :job_attempt_number, :lease_owner, :correlation_id)"
            ),
            {
                "id": str(run_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "item_id": str(item_id),
                "created_at": datetime.now(UTC),
                "job_id": str(claimed.job_id),
                "version_id": str(version_id),
                "job_attempt_number": claimed.attempt_count,
                "lease_owner": claimed.lease_owner,
                "correlation_id": str(claimed.correlation_id),
            },
        )
        # Insert a prior run and source snapshot
        prior_run_id = uuid4()
        await session.execute(
            sa.text(
                "INSERT INTO research_runs (id, org_id, project_id, item_id, status, created_at, "
                "version_id, job_attempt_number, lease_owner, correlation_id) "
                "VALUES (:id, :org_id, :project_id, :item_id, 'succeeded', :created_at, "
                ":version_id, 1, 'worker-1', :correlation_id)"
            ),
            {
                "id": str(prior_run_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "item_id": str(item_id),
                "created_at": datetime.now(UTC),
                "version_id": str(version_id),
                "correlation_id": str(uuid4()),
            },
        )
        prior_snapshot_id = uuid4()
        await session.execute(
            sa.text(
                """
                INSERT INTO source_snapshots (
                    id, org_id, project_id, item_id, run_id, url, title,
                    publisher, excerpt, origin, sha256_hash, retrieved_at
                ) VALUES (
                    :id, :org_id, :project_id, :item_id, :run_id, 'https://example.com',
                    'Prior Snapshot', 'Publisher', 'Excerpt', 'search', :hash, :retrieved_at
                )
                """
            ),
            {
                "id": str(prior_snapshot_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "item_id": str(item_id),
                "run_id": str(prior_run_id),
                "hash": "a" * 64,
                "retrieved_at": datetime.now(UTC),
            },
        )
        # Insert a claim referencing the prior snapshot (unauthenticated in current run_id)
        await session.execute(
            sa.text(
                """
                INSERT INTO evidence_claims (
                    id, org_id, project_id, item_id, snapshot_id,
                    stance, authority_tier, claim_text, provenance_excerpt, created_at
                ) VALUES (
                    :id, :org_id, :project_id, :item_id, :snapshot_id,
                    'supports', 'primary_official', 'Claim citing prior run snapshot', 'Excerpt', :created_at
                )
                """
            ),
            {
                "id": str(uuid4()),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "item_id": str(item_id),
                "snapshot_id": str(prior_snapshot_id),
                "created_at": datetime.now(UTC),
            },
        )

    repository = SqlResearchRepository()
    receipt_repo = SqlStepReceiptRepository()
    eval_repo = SqlEvaluationRepository()
    judge = HermeticJudgeAdapter()
    evaluation = EvaluationService(repository=eval_repo, judge=judge)

    mock_model = ScriptedMockStrandsModel(
        [
            {"type": "tool", "name": "read_item_context", "input": {}},
            {"type": "tool", "name": "plan_queries", "input": {"queries": ["nike shoes"]}},
            {"type": "tool", "name": "search_evidence", "input": {"query": "nike shoes"}},
            {"type": "text", "text": "Done."},
        ]
    )

    workflow = StrandsResearchWorkflow(
        repository=repository,
        step_receipt_repo=receipt_repo,
        search=DummySearch(),
        extract=DummyExtract(),
        synthesizer=DummySynthesizer(),
        evaluation=evaluation,
        model=mock_model,
    )

    context = ResearchWorkflowContext(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        version_id=version_id,
        run_id=run_id,
        category="products_and_trademarks",
        item_text="Nike Shoes",
        job_id=claimed.job_id,
        attempt_number=claimed.attempt_count,
        lease_owner=claimed.lease_owner,
        correlation_id=claimed.correlation_id,
    )

    result = await workflow.execute_research(context)
    assert result.status == "failed"
    assert "unauthenticated" in (result.error or "").lower()
    assert result.cleared is False
    assert result.needs_human_review is True

    # Confirm DB status is failed
    async with session_scope() as session:
        run_row = (
            await session.execute(
                sa.text("SELECT status FROM research_runs WHERE id = :run_id"),
                {"run_id": str(run_id)},
            )
        ).first()
        assert run_row is not None
        assert run_row[0] == "failed"

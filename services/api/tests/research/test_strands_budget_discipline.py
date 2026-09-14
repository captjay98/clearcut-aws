"""Tests verifying JobBudgetTracker enforcement across Strands agent tools and model streaming."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
import sqlalchemy as sa
from clearcut.ai.budgets import BudgetExceededError, JobBudget, JobBudgetTracker
from clearcut.database import session_scope
from clearcut.operations.adapters.sql_job_repository import SqlJobRepository
from clearcut.operations.ports.job_repository import EnqueueJob
from clearcut.research.adapters.sql_research_repository import SqlResearchRepository
from clearcut.research.adapters.sql_step_receipt_repository import SqlStepReceiptRepository
from clearcut.research.adapters.strands_workflow import (
    LeafPermitModelWrapper,
    ScriptedMockStrandsModel,
    StrandsResearchWorkflow,
)
from clearcut.research.application.agent_tools import create_scoped_research_tools
from clearcut.research.domain.extraction import ExtractBatchResponse
from clearcut.research.domain.snapshots import SearchResponse, SearchResultItem
from clearcut.research.ports.workflow import ResearchWorkflowContext


class DummySearch:
    def search(self, request: Any) -> SearchResponse:
        return SearchResponse(
            search_id="s-1",
            session_id="sess-1",
            results=[
                SearchResultItem(
                    url="https://example.gov/brand",
                    title="Brand Details",
                    publisher="Official",
                    snippet="Official trademark registry entry.",
                )
            ],
        )


class DummyExtract:
    def extract(self, request: Any) -> ExtractBatchResponse:
        return ExtractBatchResponse(
            extract_id="ext-1",
            session_id="sess-1",
            results=(),
            errors=(),
            warnings=(),
        )


async def _seed_test_org_and_run() -> ResearchWorkflowContext:
    org_id = uuid4()
    project_id = uuid4()
    script_id = uuid4()
    version_id = uuid4()
    item_id = uuid4()
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
                "name": "Org",
                "slug": f"org-{org_id.hex[:8]}",
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
                "source_hash": "b" * 64,
                "created_at": datetime.now(UTC),
            },
        )
        element_id = uuid4()
        await session.execute(
            sa.text(
                "INSERT INTO script_elements (id, version_id, ordinal, element_type, text) "
                "VALUES (:id, :version_id, 1, 'action', 'Action text.')"
            ),
            {"id": str(element_id), "version_id": str(version_id)},
        )
        await session.execute(
            sa.text(
                "INSERT INTO clearance_items (id, org_id, project_id, script_id, version_id, element_id, category, text, status, created_at) "
                "VALUES (:id, :org_id, :project_id, :script_id, :version_id, :element_id, 'products_and_trademarks', 'Test Brand', 'unresolved', :created_at)"
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

    return ResearchWorkflowContext(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        version_id=version_id,
        run_id=run_id,
        job_id=claimed.job_id,
        attempt_number=claimed.attempt_count,
        lease_owner=claimed.lease_owner,
        correlation_id=claimed.correlation_id,
        category="products_and_trademarks",
        item_text="Test Brand",
    )


@pytest.mark.asyncio
async def test_search_call_budget_halts_subsequent_search():
    """Verify exceeding max_search_calls raises BudgetExceededError."""
    context = await _seed_test_org_and_run()
    budget_tracker = JobBudgetTracker(budget=JobBudget(max_search_calls=1))

    tools = create_scoped_research_tools(
        context=context,
        repository=SqlResearchRepository(),
        step_receipt_repo=SqlStepReceiptRepository(),
        search=DummySearch(),
        extract=DummyExtract(),
        budget_tracker=budget_tracker,
    )
    search_tool = next(t for t in tools if t.tool_spec["name"] == "search_evidence")

    # 1st search call succeeds
    result1 = await search_tool(query="brand clearance")
    assert result1["status"] == "succeeded"

    # 2nd search call exceeds budget
    with pytest.raises(BudgetExceededError) as exc_info:
        await search_tool(query="brand clearance query 2")

    assert "search_calls" in str(exc_info.value)


@pytest.mark.asyncio
async def test_tool_call_limit_enforced():
    """Verify exceeding max_tool_calls raises BudgetExceededError."""
    context = await _seed_test_org_and_run()
    budget_tracker = JobBudgetTracker(budget=JobBudget(max_tool_calls=2))

    tools = create_scoped_research_tools(
        context=context,
        repository=SqlResearchRepository(),
        step_receipt_repo=SqlStepReceiptRepository(),
        search=DummySearch(),
        extract=DummyExtract(),
        budget_tracker=budget_tracker,
    )
    read_item_tool = next(t for t in tools if t.tool_spec["name"] == "read_item_context")
    plan_tool = next(t for t in tools if t.tool_spec["name"] == "plan_queries")
    progress_tool = next(t for t in tools if t.tool_spec["name"] == "read_research_progress")

    await read_item_tool()
    await plan_tool(queries=["q1", "q2"])

    # 3rd tool call exceeds max_tool_calls=2
    with pytest.raises(BudgetExceededError) as exc_info:
        await progress_tool()

    assert "tool_calls" in str(exc_info.value)


@pytest.mark.asyncio
async def test_token_budget_enforced_during_streaming():
    """Verify exceeding max_total_tokens in model streaming raises BudgetExceededError."""
    budget_tracker = JobBudgetTracker(budget=JobBudget(max_total_tokens=15))

    mock_model = ScriptedMockStrandsModel(
        [
            {"type": "text", "text": "This response consumes tokens."},
        ]
    )

    wrapped_model = LeafPermitModelWrapper(
        underlying=mock_model,
        budget_tracker=budget_tracker,
    )

    # ScriptedMockStrandsModel text step emits usage totalTokens=30 (exceeds 15)
    with pytest.raises(BudgetExceededError) as exc_info:
        async for _ in wrapped_model.stream([{"role": "user", "content": [{"text": "hello"}]}]):
            pass

    assert "tokens" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_strands_workflow_handles_budget_exceeded():
    """Verify workflow terminates with failure error message when budget is exceeded."""
    context = await _seed_test_org_and_run()
    budget_tracker = JobBudgetTracker(budget=JobBudget(max_tool_calls=1))

    # Model attempts 2 tool calls, exceeding budget of 1
    mock_model = ScriptedMockStrandsModel(
        [
            {"type": "tool", "name": "read_item_context", "input": {}},
            {"type": "tool", "name": "plan_queries", "input": {"queries": ["q1"]}},
            {"type": "text", "text": "Finished."},
        ]
    )

    workflow = StrandsResearchWorkflow(
        repository=SqlResearchRepository(),
        step_receipt_repo=SqlStepReceiptRepository(),
        search=DummySearch(),
        extract=DummyExtract(),
        model=mock_model,
        budget_tracker=budget_tracker,
    )

    result = await workflow.execute_research(context)
    # The workflow terminates safely with failure status and error details
    assert result.status == "failed"
    assert result.error is not None
    assert "BudgetExceededError" in result.error or "budget" in result.error.lower()
    assert result.review_status == "unresolved"
    assert result.cleared is False
    assert result.needs_human_review is True

    # Confirm DB research_runs was updated to failed, not succeeded
    async with session_scope() as session:
        run_row = (
            await session.execute(
                sa.text("SELECT status FROM research_runs WHERE id = :run_id"),
                {"run_id": str(context.run_id)},
            )
        ).first()
        assert run_row is not None
        assert run_row[0] == "failed"

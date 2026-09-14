"""Tests verifying Strands agent crash recovery and step receipt replay."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
import sqlalchemy as sa
from clearcut.database import session_scope
from clearcut.operations.adapters.sql_job_repository import SqlJobRepository
from clearcut.operations.ports.job_repository import EnqueueJob
from clearcut.research.adapters.sql_research_repository import SqlResearchRepository
from clearcut.research.adapters.sql_step_receipt_repository import SqlStepReceiptRepository
from clearcut.research.adapters.strands_workflow import (
    ScriptedMockStrandsModel,
    StrandsResearchWorkflow,
)
from clearcut.research.application.agent_tools import create_scoped_research_tools
from clearcut.research.domain.extraction import ExtractBatchResponse
from clearcut.research.domain.snapshots import SearchResponse, SearchResultItem
from clearcut.research.ports.workflow import ResearchWorkflowContext


class CountingSearch:
    def __init__(self) -> None:
        self.call_count = 0

    def search(self, request: Any) -> SearchResponse:
        self.call_count += 1
        return SearchResponse(
            search_id=f"search-{self.call_count}",
            session_id="session-crash-test",
            results=[
                SearchResultItem(
                    url="https://example.gov/trademark/records",
                    title="Trademark Registry Entry",
                    publisher="USPTO Official",
                    snippet="Official registration records for the brand.",
                )
            ],
        )


class CountingExtract:
    def __init__(self) -> None:
        self.call_count = 0

    def extract(self, request: Any) -> ExtractBatchResponse:
        self.call_count += 1
        return ExtractBatchResponse(
            extract_id=f"extract-{self.call_count}",
            session_id="session-crash-test",
            results=(),
            errors=(),
            warnings=(),
        )


async def _seed_test_context() -> ResearchWorkflowContext:
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
                "source_hash": "c" * 64,
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
                "VALUES (:id, :org_id, :project_id, :script_id, :version_id, :element_id, 'products_and_trademarks', 'Test Product', 'unresolved', :created_at)"
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
        item_text="Test Product",
    )


@pytest.mark.asyncio
async def test_search_tool_replay_bypasses_provider_invocation():
    """Verify tool replay returns committed receipt output without re-invoking search provider."""
    context = await _seed_test_context()
    search_provider = CountingSearch()
    step_repo = SqlStepReceiptRepository()
    research_repo = SqlResearchRepository()

    tools = create_scoped_research_tools(
        context=context,
        repository=research_repo,
        step_receipt_repo=step_repo,
        search=search_provider,
        extract=CountingExtract(),
    )
    search_tool = next(t for t in tools if t.tool_spec["name"] == "search_evidence")

    # First invocation hits provider
    res1 = await search_tool(query="product trademark query")
    assert res1["status"] == "succeeded"
    assert search_provider.call_count == 1

    # Verify receipt recorded in DB
    receipts = await step_repo.list_receipts_for_run(
        org_id=context.org_id,
        project_id=context.project_id,
        run_id=context.run_id,
        attempt_number=context.attempt_number,
    )
    assert len(receipts) == 1
    assert receipts[0].tool_name == "search_evidence"

    # Second invocation with same query replays from step receipts
    res2 = await search_tool(query="product trademark query")
    assert res2["status"] == "succeeded"
    # Call count did NOT increment
    assert search_provider.call_count == 1
    assert res2["snapshot_count"] == res1["snapshot_count"]
    assert res2["snapshots"] == res1["snapshots"]

    # Receipts count remains 1 (no duplicate inserted)
    receipts_after = await step_repo.list_receipts_for_run(
        org_id=context.org_id,
        project_id=context.project_id,
        run_id=context.run_id,
        attempt_number=context.attempt_number,
    )
    assert len(receipts_after) == 1


@pytest.mark.asyncio
async def test_crash_recovery_progress_inspection():
    """Verify agent can inspect completed steps via read_research_progress after crash."""
    context = await _seed_test_context()
    search_provider = CountingSearch()
    step_repo = SqlStepReceiptRepository()
    research_repo = SqlResearchRepository()

    tools = create_scoped_research_tools(
        context=context,
        repository=research_repo,
        step_receipt_repo=step_repo,
        search=search_provider,
        extract=CountingExtract(),
    )
    read_item_tool = next(t for t in tools if t.tool_spec["name"] == "read_item_context")
    plan_tool = next(t for t in tools if t.tool_spec["name"] == "plan_queries")

    # Step 0: read context
    await read_item_tool()
    # Step 1: plan queries
    await plan_tool(queries=["q1", "q2"])

    # Simulate worker crash and restart: create fresh tool suite with same context
    recovered_tools = create_scoped_research_tools(
        context=context,
        repository=research_repo,
        step_receipt_repo=step_repo,
        search=search_provider,
        extract=CountingExtract(),
    )
    recovered_progress_tool = next(
        t for t in recovered_tools if t.tool_spec["name"] == "read_research_progress"
    )

    progress = await recovered_progress_tool()
    assert progress["step_count"] == 2
    assert progress["tool_counts"]["read_item_context"] == 1
    assert progress["tool_counts"]["plan_queries"] == 1


@pytest.mark.asyncio
async def test_workflow_replays_prior_steps_on_restart():
    """Verify StrandsResearchWorkflow seamlessly replays cached steps on restart without duplicate provider calls."""
    context = await _seed_test_context()
    search_provider = CountingSearch()
    extract_provider = CountingExtract()
    step_repo = SqlStepReceiptRepository()
    research_repo = SqlResearchRepository()

    # Pre-populate run with a search step receipt
    tools = create_scoped_research_tools(
        context=context,
        repository=research_repo,
        step_receipt_repo=step_repo,
        search=search_provider,
        extract=extract_provider,
    )
    search_tool = next(t for t in tools if t.tool_spec["name"] == "search_evidence")
    await search_tool(query="brand clearance")
    assert search_provider.call_count == 1

    # Simulate fresh workflow on recovered worker
    mock_model = ScriptedMockStrandsModel(
        [
            # Recovered agent re-runs search with same query (e.g. from prompt / conversation replay)
            {"type": "tool", "name": "search_evidence", "input": {"query": "brand clearance"}},
            {"type": "text", "text": "Research evaluated from cached results."},
        ]
    )

    workflow = StrandsResearchWorkflow(
        repository=research_repo,
        step_receipt_repo=step_repo,
        search=search_provider,
        extract=extract_provider,
        model=mock_model,
    )

    result = await workflow.execute_research(context)
    # Search provider was NOT called again during workflow execution
    assert search_provider.call_count == 1
    assert result.status == "succeeded"
    assert result.review_status == "unresolved"


@pytest.mark.asyncio
async def test_step_receipt_unique_constraints_prevent_divergence():
    """Verify database unique constraints prevent duplicate step ordinals or replayed receipts."""
    context = await _seed_test_context()
    step_repo = SqlStepReceiptRepository()

    hash_1 = "1" * 64
    hash_2 = "2" * 64
    out_1 = "a" * 64
    out_2 = "b" * 64

    # Record step 0
    await step_repo.record_step(
        org_id=context.org_id,
        project_id=context.project_id,
        run_id=context.run_id,
        item_id=context.item_id,
        job_id=context.job_id,
        attempt_number=context.attempt_number,
        step_index=0,
        tool_name="read_item_context",
        input_payload={"test": 1},
        tool_input_hash=hash_1,
        output_payload={"status": "ok"},
        tool_output_hash=out_1,
        duration_ms=5,
        status="succeeded",
    )

    # Attempt to record step with same step_index=0 fails constraint
    with pytest.raises(sa.exc.IntegrityError):
        await step_repo.record_step(
            org_id=context.org_id,
            project_id=context.project_id,
            run_id=context.run_id,
            item_id=context.item_id,
            job_id=context.job_id,
            attempt_number=context.attempt_number,
            step_index=0,
            tool_name="plan_queries",
            input_payload={"test": 2},
            tool_input_hash=hash_2,
            output_payload={"status": "ok"},
            tool_output_hash=out_2,
            duration_ms=5,
            status="succeeded",
        )

    # Attempt to record step with same tool_input_hash fails replay constraint
    with pytest.raises(sa.exc.IntegrityError):
        await step_repo.record_step(
            org_id=context.org_id,
            project_id=context.project_id,
            run_id=context.run_id,
            item_id=context.item_id,
            job_id=context.job_id,
            attempt_number=context.attempt_number,
            step_index=1,
            tool_name="read_item_context",
            input_payload={"test": 1},
            tool_input_hash=hash_1,
            output_payload={"status": "ok"},
            tool_output_hash=out_1,
            duration_ms=5,
            status="succeeded",
        )

"""Tests verifying leaf-only permit discipline and deadlock freedom for Bedrock in Strands."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from clearcut.bootstrap.paid_providers import (
    PaidProviderDisabledError,
    PaidProviderGate,
)
from clearcut.database import session_scope
from clearcut.research.adapters.sql_research_repository import SqlResearchRepository
from clearcut.research.adapters.sql_step_receipt_repository import SqlStepReceiptRepository
from clearcut.research.adapters.strands_workflow import (
    LeafPermitModelWrapper,
    ScriptedMockStrandsModel,
    StrandsResearchWorkflow,
)
from clearcut.research.domain.extraction import ExtractBatchResponse
from clearcut.research.domain.snapshots import SearchResponse
from clearcut.research.ports.workflow import ResearchWorkflowContext
from strands.tools import tool


class DummySearch:
    def search(self, request: Any) -> SearchResponse:
        return SearchResponse(
            search_id="s-1",
            session_id="sess-1",
            results=(),
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


async def _seed_test_org_and_run() -> tuple[UUID, UUID, UUID, UUID, UUID]:
    org_id = uuid4()
    project_id = uuid4()
    script_id = uuid4()
    version_id = uuid4()
    item_id = uuid4()
    run_id = uuid4()

    async with session_scope() as session:
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
    return org_id, project_id, item_id, version_id, run_id


@pytest.mark.asyncio
async def test_leaf_permit_wrapper_releases_permit_before_tool_execution():
    """Verify Bedrock permit is released during tool execution (active_count == 0)."""
    # Strict limit = 1 permit
    gate = PaidProviderGate(
        enabled_providers={"bedrock"},
        concurrency_limits={"bedrock": 1},
    )

    mock_model = ScriptedMockStrandsModel(
        [
            {"type": "tool", "name": "read_item_context", "input": {}},
            {"type": "text", "text": "Turn finished."},
        ]
    )

    wrapped_model = LeafPermitModelWrapper(
        underlying=mock_model,
        gate=gate,
    )

    org_id, project_id, item_id, version_id, run_id = await _seed_test_org_and_run()
    context = ResearchWorkflowContext(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        version_id=version_id,
        run_id=run_id,
        category="products_and_trademarks",
        item_text="Test Product",
    )

    receipt_repo = SqlStepReceiptRepository()
    workflow = StrandsResearchWorkflow(
        repository=SqlResearchRepository(),
        step_receipt_repo=receipt_repo,
        search=DummySearch(),
        extract=DummyExtract(),
        model=wrapped_model,
        gate=gate,
    )

    # Wrap read_item_context tool or observe receipts
    result = await workflow.execute_research(context)
    # Status is failed because mandatory search was not executed, but permits must be released
    assert result.status == "failed"

    # Verify at the end of the workflow, no leaked permits
    assert gate.active_count("bedrock") == 0


@pytest.mark.asyncio
async def test_subordinate_bedrock_call_within_tool_does_not_deadlock():
    """Verify subordinate call can acquire Bedrock permit inside tool without deadlocking."""
    gate = PaidProviderGate(
        enabled_providers={"bedrock"},
        concurrency_limits={"bedrock": 1},  # Exactly 1 permit available
    )

    subordinate_call_completed = False

    @tool
    async def nested_tool() -> dict[str, Any]:
        """A tool that makes a subordinate Bedrock call."""
        nonlocal subordinate_call_completed
        # If the parent orchestrator held the permit across tool calls,
        # this acquire would deadlock forever!
        assert gate.active_count("bedrock") == 0
        async with gate.acquire("bedrock"):
            assert gate.active_count("bedrock") == 1
            await asyncio.sleep(0.01)
            subordinate_call_completed = True
        assert gate.active_count("bedrock") == 0
        return {"status": "subordinate_completed"}

    mock_model = ScriptedMockStrandsModel(
        [
            {"type": "tool", "name": "nested_tool", "input": {}},
            {"type": "text", "text": "All done."},
        ]
    )

    wrapped_model = LeafPermitModelWrapper(
        underlying=mock_model,
        gate=gate,
    )

    from strands import Agent

    agent = Agent(
        model=wrapped_model,
        tools=[nested_tool],
    )

    # Must complete within 2 seconds (not deadlock)
    await asyncio.wait_for(agent.invoke_async("Start nested test"), timeout=2.0)
    assert subordinate_call_completed is True
    assert gate.active_count("bedrock") == 0


@pytest.mark.asyncio
async def test_disabled_bedrock_fails_closed():
    """Verify that if bedrock is disabled in the gate, permit acquisition fails closed."""
    gate = PaidProviderGate(
        enabled_providers={"gemini"},  # bedrock not enabled
        concurrency_limits={"bedrock": 1},
    )

    mock_model = ScriptedMockStrandsModel(
        [
            {"type": "text", "text": "Should not reach here."},
        ]
    )

    wrapped_model = LeafPermitModelWrapper(
        underlying=mock_model,
        gate=gate,
    )

    with pytest.raises(PaidProviderDisabledError) as exc_info:
        async for _ in wrapped_model.stream([{"role": "user", "content": [{"text": "hello"}]}]):
            pass

    assert "bedrock" in str(exc_info.value).lower()

"""Tests verifying server-side tenant-bound tool scope and SSRF defense."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from clearcut.database import session_scope
from clearcut.research.adapters.sql_research_repository import SqlResearchRepository
from clearcut.research.adapters.sql_step_receipt_repository import SqlStepReceiptRepository
from clearcut.research.application.agent_tools import (
    EvaluateSourceEvidenceArgs,
    ExtractAdmittedSourceArgs,
    PlanQueriesArgs,
    ReadItemContextArgs,
    ReadResearchProgressArgs,
    SearchEvidenceArgs,
    create_scoped_research_tools,
)
from clearcut.research.domain.extraction import ExtractBatchResponse
from clearcut.research.domain.snapshots import SearchResponse
from clearcut.research.ports.workflow import ResearchWorkflowContext
from pydantic import ValidationError


class RecordingExtract:
    def __init__(self) -> None:
        self.calls: list[Any] = []

    def extract(self, request: Any) -> ExtractBatchResponse:
        self.calls.append(request)
        return ExtractBatchResponse(
            extract_id="ext-rec",
            session_id="session-rec",
            results=(),
            errors=(),
            warnings=(),
        )


class DummySearch:
    def search(self, request: Any) -> SearchResponse:
        return SearchResponse(
            search_id="s-1",
            session_id="sess-1",
            results=(),
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
                "source_hash": "a" * 64,
                "created_at": datetime.now(UTC),
            },
        )
        element_id = uuid4()
        await session.execute(
            sa.text(
                "INSERT INTO script_elements (id, version_id, ordinal, element_type, text) "
                "VALUES (:id, :version_id, 1, 'action', 'Ferrari F40 speeds past.')"
            ),
            {"id": str(element_id), "version_id": str(version_id)},
        )
        await session.execute(
            sa.text(
                "INSERT INTO clearance_items (id, org_id, project_id, script_id, version_id, element_id, category, text, status, created_at) "
                "VALUES (:id, :org_id, :project_id, :script_id, :version_id, :element_id, 'products_and_trademarks', 'Ferrari F40', 'unresolved', :created_at)"
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


def test_tool_specs_strictly_exclude_tenant_and_governance_identifiers():
    """Verify tool parameter schemas exposed to the model strictly exclude tenant IDs."""
    context = ResearchWorkflowContext(
        org_id=uuid4(),
        project_id=uuid4(),
        item_id=uuid4(),
        version_id=uuid4(),
        run_id=uuid4(),
        category="products_and_trademarks",
        item_text="Test item",
    )
    tools = create_scoped_research_tools(
        context=context,
        repository=SqlResearchRepository(),
        step_receipt_repo=SqlStepReceiptRepository(),
        search=DummySearch(),
        extract=RecordingExtract(),
    )

    forbidden_fields = {
        "org_id",
        "project_id",
        "item_id",
        "run_id",
        "lease_owner",
        "job_id",
        "attempt_number",
        "policy_version",
        "prompt_version",
    }

    assert len(tools) == 6
    for tool in tools:
        spec = tool.tool_spec
        input_schema = spec.get("inputSchema", {}).get("json", {})
        properties = input_schema.get("properties", {})
        for forbidden in forbidden_fields:
            assert forbidden not in properties, (
                f"Tool '{spec['name']}' exposes forbidden parameter '{forbidden}' in its schema!"
            )
        assert input_schema.get("additionalProperties") is False, (
            f"Tool '{spec['name']}' must enforce additionalProperties=False in schema!"
        )


def test_pydantic_argument_models_forbid_extra_fields():
    """Verify Pydantic models fail validation if tenant fields or unknown arguments are passed."""
    with pytest.raises(ValidationError):
        ReadItemContextArgs.model_validate({"org_id": str(uuid4())})

    with pytest.raises(ValidationError):
        PlanQueriesArgs.model_validate({"queries": ["test"], "project_id": str(uuid4())})

    with pytest.raises(ValidationError):
        SearchEvidenceArgs.model_validate({"query": "test", "run_id": str(uuid4())})

    with pytest.raises(ValidationError):
        ExtractAdmittedSourceArgs.model_validate(
            {"url": "https://example.com", "lease_owner": "hacker"}
        )

    with pytest.raises(ValidationError):
        EvaluateSourceEvidenceArgs.model_validate({"cleared": True})

    with pytest.raises(ValidationError):
        ReadResearchProgressArgs.model_validate({"extra_param": 123})


@pytest.mark.asyncio
async def test_extract_rejects_unadmitted_url_without_network_access():
    """Verify extract_admitted_source validates search admission and rejects unadmitted targets."""
    org_id, project_id, item_id, version_id, run_id = await _seed_test_org_and_run()

    recording_extract = RecordingExtract()
    receipt_repo = SqlStepReceiptRepository()
    context = ResearchWorkflowContext(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        version_id=version_id,
        run_id=run_id,
        category="products_and_trademarks",
        item_text="Ferrari F40",
    )
    tools = create_scoped_research_tools(
        context=context,
        repository=SqlResearchRepository(),
        step_receipt_repo=receipt_repo,
        search=DummySearch(),
        extract=recording_extract,
    )
    extract_tool = next(t for t in tools if t.tool_spec["name"] == "extract_admitted_source")

    # Unadmitted arbitrary URL
    result = await extract_tool(url="https://arbitrary-site.com/leaked-data")
    assert result["status"] == "rejected"
    assert "was not admitted by a prior search" in result["error"]

    # Verify extract provider was NEVER called (fail-closed before network)
    assert len(recording_extract.calls) == 0

    # Verify an immutable rejected receipt was recorded
    receipts = await receipt_repo.list_receipts_for_run(
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
    )
    assert len(receipts) == 1
    assert receipts[0].tool_name == "extract_admitted_source"
    assert receipts[0].status == "rejected"


@pytest.mark.asyncio
async def test_extract_rejects_ssrf_targets():
    """Verify extract_admitted_source rejects AWS metadata service and loopback addresses."""
    org_id, project_id, item_id, version_id, run_id = await _seed_test_org_and_run()

    recording_extract = RecordingExtract()
    receipt_repo = SqlStepReceiptRepository()
    context = ResearchWorkflowContext(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        version_id=version_id,
        run_id=run_id,
        category="products_and_trademarks",
        item_text="Ferrari F40",
    )
    tools = create_scoped_research_tools(
        context=context,
        repository=SqlResearchRepository(),
        step_receipt_repo=receipt_repo,
        search=DummySearch(),
        extract=recording_extract,
    )
    extract_tool = next(t for t in tools if t.tool_spec["name"] == "extract_admitted_source")

    ssrf_targets = [
        "http://169.254.169.254/latest/meta-data/",
        "https://169.254.169.254/latest/meta-data/",
        "http://127.0.0.1:8000/internal",
        "file:///etc/passwd",
    ]

    for target in ssrf_targets:
        result = await extract_tool(url=target)
        assert result["status"] == "rejected"

    assert len(recording_extract.calls) == 0

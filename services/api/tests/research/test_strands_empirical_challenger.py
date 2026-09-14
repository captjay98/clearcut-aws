"""Empirical adversarial challenge suite for Strands tool scoping, SSRF defense, and anti-self-clearance."""

from __future__ import annotations

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
from clearcut.research.application.agent_tools import (
    EvaluateSourceEvidenceArgs,
    ExtractAdmittedSourceArgs,
    PlanQueriesArgs,
    ReadItemContextArgs,
    ReadResearchProgressArgs,
    SearchEvidenceArgs,
    create_scoped_research_tools,
)
from clearcut.research.application.completion_validator import (
    DeterministicCompletionValidator,
    MissingMandatorySearchError,
    UnauthenticatedCitationError,
)
from clearcut.research.domain.claims import EvidenceClaim, EvidenceStance, SourceAuthorityTier
from clearcut.research.domain.extraction import ExtractBatchResponse, ExtractedPage
from clearcut.research.domain.snapshots import SearchResponse, SearchResultItem
from clearcut.research.ports.claim_synthesizer import (
    ClaimSynthesisSuccess,
    ClaimSynthesizerPort,
    SynthesisAttemptMetadata,
    SynthesisTokenUsage,
)
from clearcut.research.ports.step_receipt_repository import StepReceiptRecord
from clearcut.research.ports.workflow import ResearchWorkflowContext
from pydantic import ValidationError


class RecordingExtractProvider:
    def __init__(self) -> None:
        self.calls: list[Any] = []

    def extract(self, request: Any) -> ExtractBatchResponse:
        self.calls.append(request)
        return ExtractBatchResponse(
            extract_id="ext-rec",
            session_id="session-rec",
            results=tuple(
                ExtractedPage(url=u, title="Extracted", content="Content") for u in request.urls
            ),
            errors=(),
            warnings=(),
        )


class ControlledSearchProvider:
    def __init__(self, items: list[SearchResultItem] | None = None) -> None:
        self.items = items or []

    def search(self, request: Any) -> SearchResponse:
        return SearchResponse(
            search_id="s-controlled",
            session_id="sess-controlled",
            results=list(self.items),
        )


class DummySynthesizer(ClaimSynthesizerPort):
    requested_model = "test-synthesizer"

    async def synthesize_claim(self, request: Any) -> Any:
        return ClaimSynthesisSuccess(
            claim_text=f"Synthesized claim: {request.excerpt[:50]}",
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


async def _seed_test_project_and_item() -> tuple[UUID, UUID, UUID, UUID, UUID, UUID]:
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
                "name": "Test Org",
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
        await session.execute(
            sa.text(
                "INSERT INTO script_elements (id, version_id, ordinal, element_type, text) "
                "VALUES (:id, :version_id, 1, 'action', 'John wears Nike sneakers.')"
            ),
            {"id": str(element_id), "version_id": str(version_id)},
        )
        await session.execute(
            sa.text(
                "INSERT INTO clearance_items (id, org_id, project_id, script_id, version_id, element_id, category, text, status, created_at) "
                "VALUES (:id, :org_id, :project_id, :script_id, :version_id, :element_id, 'products_and_trademarks', 'Nike Sneakers', 'unresolved', :created_at)"
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


# =========================================================================
# ATTACK 1: PROMPT INJECTION SCOPE SPOOFING
# =========================================================================


def test_adversarial_prompt_injection_schema_forbid_all_tools():
    """Verify all Pydantic tool argument schemas forbid extra fields."""
    tool_arg_models = [
        (ReadItemContextArgs, {}),
        (PlanQueriesArgs, {"queries": ["test query"]}),
        (SearchEvidenceArgs, {"query": "test query"}),
        (ExtractAdmittedSourceArgs, {"url": "https://example.com"}),
        (EvaluateSourceEvidenceArgs, {}),
        (ReadResearchProgressArgs, {}),
    ]

    injected_keys = [
        "org_id",
        "project_id",
        "run_id",
        "tenant_id",
        "lease_owner",
        "item_id",
        "job_id",
        "system_override",
    ]

    for model_cls, valid_data in tool_arg_models:
        for key in injected_keys:
            bad_data = {**valid_data, key: str(uuid4())}
            with pytest.raises(ValidationError) as exc:
                model_cls.model_validate(bad_data)
            assert "Extra inputs are not permitted" in str(exc.value)


def test_tool_specs_model_facing_additional_properties_false():
    """Verify tool specs presented to the model enforce additionalProperties=False and omit tenant IDs."""
    context = ResearchWorkflowContext(
        org_id=uuid4(),
        project_id=uuid4(),
        item_id=uuid4(),
        version_id=uuid4(),
        run_id=uuid4(),
        category="products_and_trademarks",
        item_text="Test element",
    )
    tools = create_scoped_research_tools(
        context=context,
        repository=SqlResearchRepository(),
        step_receipt_repo=SqlStepReceiptRepository(),
        search=ControlledSearchProvider(),
        extract=RecordingExtractProvider(),
    )

    forbidden_params = {"org_id", "project_id", "run_id", "item_id", "lease_owner", "job_id"}
    assert len(tools) == 6
    for t in tools:
        spec = t.tool_spec
        schema = spec.get("inputSchema", {}).get("json", {})
        assert schema.get("additionalProperties") is False
        props = schema.get("properties", {})
        for forbidden in forbidden_params:
            assert forbidden not in props, f"Tool {spec['name']} exposed {forbidden}"


@pytest.mark.asyncio
async def test_workflow_rejects_model_injected_tenant_scope():
    """Verify an agent emitting tool use with foreign org_id/project_id fails safely without creating foreign records."""
    org_id, project_id, _, version_id, item_id, user_id = await _seed_test_project_and_item()
    foreign_org_id = uuid4()
    foreign_project_id = uuid4()

    jobs = SqlJobRepository()
    q_job = await jobs.enqueue(
        EnqueueJob(
            org_id=org_id,
            project_id=project_id,
            actor_id=user_id,
            job_type="research",
            idempotency_key=f"res:{item_id}:inj",
            payload={"schemaVersion": 1, "target": {"type": "clearance_item", "id": str(item_id)}},
            audit_action="research.started",
            target_type="clearance_item",
            target_id=item_id,
        )
    )
    claimed = await jobs.claim(
        org_id=org_id,
        project_id=project_id,
        job_id=q_job.job.job_id,
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
                "correlation_id": str(uuid4()),
            },
        )

    # Adversarial model attempts to pass foreign org_id and project_id to search_evidence
    bad_model = ScriptedMockStrandsModel(
        [
            {
                "type": "tool",
                "name": "search_evidence",
                "input": {
                    "query": "Nike",
                    "org_id": str(foreign_org_id),
                    "project_id": str(foreign_project_id),
                },
            },
            {"type": "text", "text": "Search completed with injected org."},
        ]
    )

    workflow = StrandsResearchWorkflow(
        repository=SqlResearchRepository(),
        step_receipt_repo=SqlStepReceiptRepository(),
        search=ControlledSearchProvider(),
        extract=RecordingExtractProvider(),
        evaluation=EvaluationService(
            repository=SqlEvaluationRepository(), judge=HermeticJudgeAdapter()
        ),
        model=bad_model,
    )

    context = ResearchWorkflowContext(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        version_id=version_id,
        run_id=run_id,
        job_id=claimed.job_id,
        attempt_number=claimed.attempt_count,
        lease_owner=claimed.lease_owner,
        correlation_id=str(uuid4()),
        category="products_and_trademarks",
        item_text="Nike Sneakers",
    )

    result = await workflow.execute_research(context)
    # The workflow executes safely using server-side bound tenant context
    assert result.status == "succeeded"
    assert result.cleared is False
    assert result.review_status == "unresolved"

    # Confirm zero foreign records created in the database (tenant isolation held)
    async with session_scope() as session:
        foreign_queries = (
            await session.execute(
                sa.text("SELECT COUNT(*) FROM research_queries WHERE org_id = :org"),
                {"org": str(foreign_org_id)},
            )
        ).scalar_one()
        assert foreign_queries == 0

        # Confirm all created records strictly belong to the authenticated context tenant
        scoped_queries = (
            await session.execute(
                sa.text(
                    "SELECT COUNT(*) FROM research_queries WHERE org_id = :org AND project_id = :proj AND run_id = :run"
                ),
                {
                    "org": str(context.org_id),
                    "proj": str(context.project_id),
                    "run": str(context.run_id),
                },
            )
        ).scalar_one()
        assert scoped_queries >= 1


# =========================================================================
# ATTACK 2: SSRF AND UNADMITTED SOURCE EXTRACTION
# =========================================================================


@pytest.mark.asyncio
async def test_extract_rejects_aws_imds_and_ipv6_metadata():
    """Verify all AWS metadata, loopback, internal network, and non-HTTPS targets are rejected before network access."""
    org_id, project_id, _, version_id, item_id, _ = await _seed_test_project_and_item()
    spy_extract = RecordingExtractProvider()
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
    context = ResearchWorkflowContext(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        version_id=version_id,
        run_id=run_id,
        category="products_and_trademarks",
        item_text="Nike Sneakers",
    )
    tools = {
        t.tool_spec["name"]: t
        for t in create_scoped_research_tools(
            context=context,
            repository=SqlResearchRepository(),
            step_receipt_repo=SqlStepReceiptRepository(),
            search=ControlledSearchProvider(),
            extract=spy_extract,
        )
    }

    ssrf_targets = [
        # AWS IMDSv1 and IMDSv2
        "http://169.254.169.254/latest/meta-data/",
        "http://169.254.169.254/latest/meta-data/iam/security-credentials/",
        "http://169.254.169.254/latest/api/token",
        "https://169.254.169.254/latest/meta-data/",
        # IPv6 IMDS
        "http://[fd00:ec2::254]/latest/meta-data/",
        "https://[fd00:ec2::254]/latest/meta-data/",
        # Loopback & Internal RFC1918
        "http://localhost:8000/internal",
        "http://127.0.0.1:8000/internal",
        "http://0.0.0.0:18080/api",
        "http://[::1]:8000/",
        "http://10.0.0.1/admin",
        "http://172.16.0.1/admin",
        "http://192.168.1.1/admin",
        # Scheme smuggling & file protocols
        "file:///etc/passwd",
        "gopher://127.0.0.1:6379/_INFO",
        "ftp://evil.com/resource",
        "data:text/html,<script>alert(1)</script>",
        # Credentials in URL
        "https://user:pass@evil.com/",
        # Unadmitted external URLs
        "https://attacker.com/leak",
        "https://en.wikipedia.org/wiki/Nike",
    ]

    for target in ssrf_targets:
        res = await tools["extract_admitted_source"](url=target)
        assert res["status"] == "rejected"
        assert "was not admitted by a prior search in this research run" in res["error"]

    # Assert provider was NEVER called (zero network traffic)
    assert len(spy_extract.calls) == 0


@pytest.mark.asyncio
async def test_extract_rejects_cross_tenant_url_poaching():
    """Verify Org 2 cannot extract a URL admitted by Org 1 in a separate search run."""
    # Setup Org 1
    org1, proj1, _, v1, item1, user1 = await _seed_test_project_and_item()
    jobs = SqlJobRepository()
    q_job1 = await jobs.enqueue(
        EnqueueJob(
            org_id=org1,
            project_id=proj1,
            actor_id=user1,
            job_type="research",
            idempotency_key=f"res:{item1}:p1",
            payload={"schemaVersion": 1, "target": {"type": "clearance_item", "id": str(item1)}},
            audit_action="research.started",
            target_type="clearance_item",
            target_id=item1,
        )
    )
    claimed1 = await jobs.claim(
        org_id=org1, project_id=proj1, job_id=q_job1.job.job_id, lease_owner="worker-1"
    )
    assert claimed1 is not None
    run1 = uuid4()
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO research_runs (id, org_id, project_id, item_id, status, created_at, "
                "job_id, version_id, job_attempt_number, lease_owner, correlation_id) "
                "VALUES (:id, :org_id, :project_id, :item_id, 'running', :created_at, "
                ":job_id, :version_id, :job_attempt_number, :lease_owner, :correlation_id)"
            ),
            {
                "id": str(run1),
                "org_id": str(org1),
                "project_id": str(proj1),
                "item_id": str(item1),
                "created_at": datetime.now(UTC),
                "job_id": str(claimed1.job_id),
                "version_id": str(v1),
                "job_attempt_number": claimed1.attempt_count,
                "lease_owner": claimed1.lease_owner,
                "correlation_id": str(uuid4()),
            },
        )

    admitted_url = "https://example.gov/trademark/nike"
    search_provider1 = ControlledSearchProvider(
        items=[
            SearchResultItem(
                url=admitted_url,
                title="Nike Trademark",
                publisher="USPTO",
                snippet="Official registration",
            )
        ]
    )
    repo = SqlResearchRepository()
    receipt_repo = SqlStepReceiptRepository()

    context1 = ResearchWorkflowContext(
        org_id=org1,
        project_id=proj1,
        item_id=item1,
        version_id=v1,
        run_id=run1,
        job_id=claimed1.job_id,
        attempt_number=claimed1.attempt_count,
        lease_owner=claimed1.lease_owner,
        correlation_id=str(uuid4()),
        category="products_and_trademarks",
        item_text="Nike Sneakers",
    )
    tools1 = {
        t.tool_spec["name"]: t
        for t in create_scoped_research_tools(
            context=context1,
            repository=repo,
            step_receipt_repo=receipt_repo,
            search=search_provider1,
            extract=RecordingExtractProvider(),
        )
    }

    s_res = await tools1["search_evidence"](query="Nike mark")
    assert s_res["status"] == "succeeded"
    assert s_res["snapshot_count"] == 1

    # Setup Org 2
    org2, proj2, _, v2, item2, user2 = await _seed_test_project_and_item()
    q_job2 = await jobs.enqueue(
        EnqueueJob(
            org_id=org2,
            project_id=proj2,
            actor_id=user2,
            job_type="research",
            idempotency_key=f"res:{item2}:p2",
            payload={"schemaVersion": 1, "target": {"type": "clearance_item", "id": str(item2)}},
            audit_action="research.started",
            target_type="clearance_item",
            target_id=item2,
        )
    )
    claimed2 = await jobs.claim(
        org_id=org2, project_id=proj2, job_id=q_job2.job.job_id, lease_owner="worker-2"
    )
    assert claimed2 is not None
    run2 = uuid4()
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO research_runs (id, org_id, project_id, item_id, status, created_at, "
                "job_id, version_id, job_attempt_number, lease_owner, correlation_id) "
                "VALUES (:id, :org_id, :project_id, :item_id, 'running', :created_at, "
                ":job_id, :version_id, :job_attempt_number, :lease_owner, :correlation_id)"
            ),
            {
                "id": str(run2),
                "org_id": str(org2),
                "project_id": str(proj2),
                "item_id": str(item2),
                "created_at": datetime.now(UTC),
                "job_id": str(claimed2.job_id),
                "version_id": str(v2),
                "job_attempt_number": claimed2.attempt_count,
                "lease_owner": claimed2.lease_owner,
                "correlation_id": str(uuid4()),
            },
        )

    spy_extract2 = RecordingExtractProvider()
    context2 = ResearchWorkflowContext(
        org_id=org2,
        project_id=proj2,
        item_id=item2,
        version_id=v2,
        run_id=run2,
        job_id=claimed2.job_id,
        attempt_number=claimed2.attempt_count,
        lease_owner=claimed2.lease_owner,
        correlation_id=str(uuid4()),
        category="products_and_trademarks",
        item_text="Other Element",
    )
    tools2 = {
        t.tool_spec["name"]: t
        for t in create_scoped_research_tools(
            context=context2,
            repository=repo,
            step_receipt_repo=receipt_repo,
            search=ControlledSearchProvider(),
            extract=spy_extract2,
        )
    }

    # Org 2 attempts to extract the URL authorized only in Org 1
    res2 = await tools2["extract_admitted_source"](url=admitted_url)
    assert res2["status"] == "rejected"
    assert "was not admitted by a prior search in this research run" in res2["error"]
    assert len(spy_extract2.calls) == 0


# =========================================================================
# ATTACK 3: AUTONOMOUS SELF-CLEARANCE BYPASS
# =========================================================================


@pytest.mark.asyncio
async def test_adversarial_hallucinated_self_clearance_without_search():
    """Verify LLM claims of clearance without search are intercepted and failed."""
    validator = DeterministicCompletionValidator()
    org_id = uuid4()
    project_id = uuid4()
    run_id = uuid4()
    item_id = uuid4()

    # Case A: raise_exc=True raises MissingMandatorySearchError
    with pytest.raises(MissingMandatorySearchError):
        await validator.validate(
            org_id=org_id,
            project_id=project_id,
            run_id=run_id,
            item_id=item_id,
            step_receipts=[],
            claims=[],
            raw_summary={"cleared": True, "review_status": "cleared"},
            raise_exc=True,
        )

    # Case B: raise_exc=False returns valid=False, cleared=False, needs_human_review=True
    outcome = await validator.validate(
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        item_id=item_id,
        step_receipts=[],
        claims=[],
        raw_summary={"cleared": True, "review_status": "cleared"},
        raise_exc=False,
    )
    assert outcome.valid is False
    assert outcome.error == "missing_mandatory_search"
    assert outcome.cleared is False
    assert outcome.needs_human_review is True
    assert outcome.review_status == "unresolved"


@pytest.mark.asyncio
async def test_adversarial_self_clearance_after_empty_search():
    """Verify LLM claims of clearance after empty search are forced to unresolved."""
    validator = DeterministicCompletionValidator()
    org_id = uuid4()
    project_id = uuid4()
    run_id = uuid4()
    item_id = uuid4()

    search_receipt = StepReceiptRecord(
        id=uuid4(),
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        item_id=item_id,
        job_id=None,
        attempt_number=1,
        step_index=0,
        tool_name="search_evidence",
        tool_input_hash="a" * 64,
        tool_output_hash="b" * 64,
        input_payload={"query": "Nike"},
        output_payload={"status": "succeeded", "snapshot_count": 0},
        status="succeeded",
        duration_ms=50,
        created_at=datetime.now(UTC),
    )

    outcome = await validator.validate(
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        item_id=item_id,
        step_receipts=[search_receipt],
        claims=[],
        raw_summary={"cleared": True, "review_status": "cleared", "needs_human_review": False},
        raise_exc=False,
    )
    assert outcome.valid is True
    assert outcome.cleared is False
    assert outcome.needs_human_review is True
    assert outcome.review_status == "unresolved"
    assert outcome.reason == "no_search_results"
    assert outcome.sanitized_summary["cleared"] is False
    assert outcome.sanitized_summary["needs_human_review"] is True


@pytest.mark.asyncio
async def test_adversarial_self_clearance_with_foreign_citations():
    """Verify LLM claims citing foreign snapshot IDs trigger UnauthenticatedCitationError."""
    validator = DeterministicCompletionValidator()
    org_id = uuid4()
    project_id = uuid4()
    run_id = uuid4()
    item_id = uuid4()

    foreign_snapshot_id = uuid4()
    claim = EvidenceClaim(
        claim_id=uuid4(),
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        snapshot_id=foreign_snapshot_id,
        claim_text="Forged claim referencing unauthenticated snapshot",
        stance=EvidenceStance.SUPPORTS,
        authority_tier=SourceAuthorityTier.PRIMARY_OFFICIAL,
        provenance_excerpt="Fabricated citation",
    )

    search_receipt = StepReceiptRecord(
        id=uuid4(),
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        item_id=item_id,
        job_id=None,
        attempt_number=1,
        step_index=0,
        tool_name="search_evidence",
        tool_input_hash="a" * 64,
        tool_output_hash="b" * 64,
        input_payload={"query": "Nike"},
        output_payload={"status": "succeeded"},
        status="succeeded",
        duration_ms=50,
        created_at=datetime.now(UTC),
    )

    with pytest.raises(UnauthenticatedCitationError):
        await validator.validate(
            org_id=org_id,
            project_id=project_id,
            run_id=run_id,
            item_id=item_id,
            step_receipts=[search_receipt],
            claims=[claim],
            raw_summary={"cleared": True},
            raise_exc=True,
        )

    # With raise_exc=False, validation fails cleanly
    outcome = await validator.validate(
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        item_id=item_id,
        step_receipts=[search_receipt],
        claims=[claim],
        raw_summary={"cleared": True},
        raise_exc=False,
    )
    assert outcome.valid is False
    assert outcome.reason == "unauthenticated_citation"
    assert outcome.cleared is False
    assert outcome.needs_human_review is True
    assert outcome.review_status == "unresolved"

"""Adversarial stress and attack suite for Strands research agent.

Authored by challenger_m3_1 to rigorously probe:
1. Prompt injection and tenant scope spoofing.
2. SSRF, scheme smuggling, credential embedding, and cross-tenant extraction.
3. Autonomous self-clearance bypass and cross-tenant citation forgery.
"""

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
    create_scoped_research_tools,
)
from clearcut.research.application.completion_validator import (
    DeterministicCompletionValidator,
    MissingMandatorySearchError,
    UnauthenticatedCitationError,
)
from clearcut.research.domain.claims import (
    EvidenceClaim,
    EvidenceStance,
    SourceAuthorityTier,
)
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


class RecordingExtract:
    def __init__(self) -> None:
        self.calls: list[Any] = []

    def extract(self, request: Any) -> ExtractBatchResponse:
        self.calls.append(request)
        return ExtractBatchResponse(
            extract_id="ext-adv",
            session_id="session-adv",
            results=tuple(
                ExtractedPage(
                    url=u,
                    title="Extracted",
                    content="Extracted body content.",
                )
                for u in request.urls
            ),
            errors=(),
            warnings=(),
        )


class DummySearch:
    def __init__(self, items: list[SearchResultItem] | None = None) -> None:
        self.items = items or []

    def search(self, request: Any) -> SearchResponse:
        return SearchResponse(
            search_id="s-adv",
            session_id="sess-adv",
            results=self.items,
        )


class DummySynthesizer(ClaimSynthesizerPort):
    requested_model = "adv-synth"

    async def synthesize_claim(self, request: Any) -> Any:
        return ClaimSynthesisSuccess(
            claim_text=f"Claim on {request.url}",
            stance=EvidenceStance.SUPPORTS,
            metadata=SynthesisAttemptMetadata(
                status="succeeded",
                requested_model="adv-synth",
                returned_model="adv-synth-v1",
                response_id="synth-adv",
                usage=SynthesisTokenUsage(10, 10, 20),
                latency_ms=10,
                error=None,
            ),
        )


async def _seed_org_and_run(
    item_text: str = "Test item",
) -> tuple[UUID, UUID, UUID, UUID, UUID, UUID, str, int]:
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
                "name": f"Org-{org_id.hex[:6]}",
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
                "VALUES (:id, :org_id, 'Project', :created_at)"
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
                "source_hash": "e" * 64,
                "created_at": datetime.now(UTC),
            },
        )
        element_id = uuid4()
        await session.execute(
            sa.text(
                "INSERT INTO script_elements (id, version_id, ordinal, element_type, text) "
                "VALUES (:id, :version_id, 1, 'action', :text)"
            ),
            {"id": str(element_id), "version_id": str(version_id), "text": item_text},
        )
        await session.execute(
            sa.text(
                "INSERT INTO clearance_items (id, org_id, project_id, script_id, version_id, element_id, category, text, status, created_at) "
                "VALUES (:id, :org_id, :project_id, :script_id, :version_id, :element_id, 'products_and_trademarks', :text, 'unresolved', :created_at)"
            ),
            {
                "id": str(item_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "script_id": str(script_id),
                "version_id": str(version_id),
                "element_id": str(element_id),
                "text": item_text,
                "created_at": datetime.now(UTC),
            },
        )

    # Enqueue and claim job
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
        lease_owner="test-adv-worker",
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
    return (
        org_id,
        project_id,
        item_id,
        version_id,
        run_id,
        claimed.job_id,
        claimed.lease_owner,
        claimed.attempt_count,
    )


# =========================================================================
# ATTACK VECTOR 1: Prompt Injection & Scope Spoofing
# =========================================================================


@pytest.mark.asyncio
async def test_tool_invocations_reject_spoofed_tenant_arguments():
    """Adversarial Attack: Attempt passing injected kwargs to tools."""
    org_id, project_id, item_id, version_id, run_id, job_id, lease_owner, attempt = (
        await _seed_org_and_run()
    )
    context = ResearchWorkflowContext(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        version_id=version_id,
        run_id=run_id,
        job_id=job_id,
        lease_owner=lease_owner,
        attempt_number=attempt,
        category="products_and_trademarks",
        item_text="Test",
    )
    tools = create_scoped_research_tools(
        context=context,
        repository=SqlResearchRepository(),
        step_receipt_repo=SqlStepReceiptRepository(),
        search=DummySearch(),
        extract=RecordingExtract(),
    )
    tool_map = {t.tool_spec["name"]: t for t in tools}

    foreign_org = str(uuid4())
    foreign_proj = str(uuid4())
    foreign_run = str(uuid4())

    # 1. read_item_context with injected org_id
    with pytest.raises(TypeError):
        await tool_map["read_item_context"](org_id=foreign_org)

    # 2. plan_queries with injected project_id
    with pytest.raises(TypeError):
        await tool_map["plan_queries"](queries=["brand check"], project_id=foreign_proj)

    # 3. search_evidence with injected run_id
    with pytest.raises(TypeError):
        await tool_map["search_evidence"](query="brand check", run_id=foreign_run)

    # 4. extract_admitted_source with injected lease_owner
    with pytest.raises(TypeError):
        await tool_map["extract_admitted_source"](
            url="https://example.com", lease_owner="adversary"
        )

    # 5. evaluate_source_evidence with injected cleared status
    with pytest.raises(TypeError):
        await tool_map["evaluate_source_evidence"](cleared=True)

    # 6. read_research_progress with injected extra args
    with pytest.raises(TypeError):
        await tool_map["read_research_progress"](evil="param")


@pytest.mark.asyncio
async def test_sql_injection_in_search_query_is_safely_parameterized():
    """Adversarial Attack: SQL injection payload in search query."""
    org_id, project_id, item_id, version_id, run_id, job_id, lease_owner, attempt = (
        await _seed_org_and_run()
    )
    context = ResearchWorkflowContext(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        version_id=version_id,
        run_id=run_id,
        job_id=job_id,
        lease_owner=lease_owner,
        attempt_number=attempt,
        category="products_and_trademarks",
        correlation_id=uuid4(),
        item_text="Test",
    )
    repository = SqlResearchRepository()
    receipt_repo = SqlStepReceiptRepository()
    tools = create_scoped_research_tools(
        context=context,
        repository=repository,
        step_receipt_repo=receipt_repo,
        search=DummySearch(),
        extract=RecordingExtract(),
    )
    search_tool = next(t for t in tools if t.tool_spec["name"] == "search_evidence")

    sql_payload = "'; DROP TABLE organizations; SELECT * FROM projects WHERE '1'='1"
    result = await search_tool(query=sql_payload)

    assert result["status"] == "succeeded"
    assert result["query"] == sql_payload

    # Assert organizations table still exists and is untouched
    async with session_scope() as session:
        check = await session.execute(
            sa.text("SELECT id FROM organizations WHERE id = :id"),
            {"id": str(org_id)},
        )
        assert check.scalar_one() is not None


@pytest.mark.asyncio
async def test_cross_tenant_replay_isolation():
    """Adversarial Attack: Ensure step receipts from Tenant A cannot be replayed by Tenant B."""
    org_a, proj_a, item_a, ver_a, run_a, job_a, lease_a, att_a = await _seed_org_and_run()
    org_b, proj_b, item_b, ver_b, run_b, job_b, lease_b, att_b = await _seed_org_and_run()

    receipt_repo = SqlStepReceiptRepository()
    repository = SqlResearchRepository()

    ctx_a = ResearchWorkflowContext(
        org_id=org_a,
        project_id=proj_a,
        item_id=item_a,
        version_id=ver_a,
        run_id=run_a,
        job_id=job_a,
        lease_owner=lease_a,
        attempt_number=att_a,
        category="products_and_trademarks",
        correlation_id=uuid4(),
        item_text="Item A",
    )
    tools_a = create_scoped_research_tools(
        context=ctx_a,
        repository=repository,
        step_receipt_repo=receipt_repo,
        search=DummySearch(),
        extract=RecordingExtract(),
    )
    read_tool_a = next(t for t in tools_a if t.tool_spec["name"] == "read_item_context")
    out_a = await read_tool_a()
    assert out_a["item_id"] == str(item_a)

    # Now Tenant B calls read_item_context with identical input ({})
    ctx_b = ResearchWorkflowContext(
        org_id=org_b,
        project_id=proj_b,
        item_id=item_b,
        version_id=ver_b,
        run_id=run_b,
        job_id=job_b,
        lease_owner=lease_b,
        attempt_number=att_b,
        category="products_and_trademarks",
        correlation_id=uuid4(),
        item_text="Item B",
    )
    tools_b = create_scoped_research_tools(
        context=ctx_b,
        repository=repository,
        step_receipt_repo=receipt_repo,
        search=DummySearch(),
        extract=RecordingExtract(),
    )
    read_tool_b = next(t for t in tools_b if t.tool_spec["name"] == "read_item_context")
    out_b = await read_tool_b()

    # Must return Tenant B's data, NOT Tenant A's replayed data
    assert out_b["item_id"] == str(item_b)
    assert out_b["text"] == "Item B"


# =========================================================================
# ATTACK VECTOR 2: SSRF, Scheme Smuggling & Cross-Tenant Extraction
# =========================================================================


@pytest.mark.asyncio
async def test_ssrf_comprehensive_matrix_rejected():
    """Adversarial Attack: Probe extract tool with AWS metadata, loopback, and scheme smuggling."""
    org_id, project_id, item_id, version_id, run_id, job_id, lease_owner, attempt = (
        await _seed_org_and_run()
    )
    context = ResearchWorkflowContext(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        version_id=version_id,
        run_id=run_id,
        job_id=job_id,
        lease_owner=lease_owner,
        attempt_number=attempt,
        category="products_and_trademarks",
        correlation_id=uuid4(),
        item_text="Test",
    )
    recording_extract = RecordingExtract()
    tools = create_scoped_research_tools(
        context=context,
        repository=SqlResearchRepository(),
        step_receipt_repo=SqlStepReceiptRepository(),
        search=DummySearch(),
        extract=recording_extract,
    )
    extract_tool = next(t for t in tools if t.tool_spec["name"] == "extract_admitted_source")

    malicious_targets = [
        # AWS IMDSv1 & IMDSv2
        "http://169.254.169.254/latest/meta-data/",
        "http://169.254.169.254/latest/meta-data/iam/security-credentials/",
        "https://169.254.169.254/latest/dynamic/instance-identity/document",
        "http://[fd00:ec2::254]/latest/meta-data/",
        # Localhost / Internal network
        "http://localhost:8000/api/internal",
        "http://127.0.0.1:15433",
        "http://0.0.0.0:80",
        "http://10.0.0.1/admin",
        "http://192.168.1.1/",
        # Protocol smuggling
        "file:///etc/shadow",
        "ftp://ftp.example.com/dump",
        "gopher://127.0.0.1:6379/_FLUSHALL",
        "javascript:alert(1)",
        "data:text/html,<script>evil()</script>",
        # Credential embedding
        "https://admin:supersecret@legitimate-site.org/info",
        # Arbitrary external non-admitted site
        "https://pastebin.com/raw/leak",
        "https://attacker.com/collect",
    ]

    for target in malicious_targets:
        result = await extract_tool(url=target)
        assert result["status"] == "rejected", f"Target {target} was not rejected!"
        assert "not admitted" in result["error"]

    # Invariant: Zero outbound HTTP calls were dispatched
    assert len(recording_extract.calls) == 0


@pytest.mark.asyncio
async def test_cross_tenant_url_admission_isolation():
    """Adversarial Attack: Run A admits a URL. Run B attempts to extract it without prior search."""
    org_a, proj_a, item_a, ver_a, run_a, job_a, lease_a, att_a = await _seed_org_and_run()
    org_b, proj_b, item_b, ver_b, run_b, job_b, lease_b, att_b = await _seed_org_and_run()

    target_url = "https://legit-source.org/trademark/record"
    search_item = SearchResultItem(
        url=target_url,
        title="Official Trademark",
        publisher="USPTO",
        snippet="Official mark registration.",
    )

    repository = SqlResearchRepository()
    receipt_repo = SqlStepReceiptRepository()
    recording_extract = RecordingExtract()

    # Run A searches and admits the URL
    ctx_a = ResearchWorkflowContext(
        org_id=org_a,
        project_id=proj_a,
        item_id=item_a,
        version_id=ver_a,
        run_id=run_a,
        job_id=job_a,
        lease_owner=lease_a,
        attempt_number=att_a,
        category="products_and_trademarks",
        correlation_id=uuid4(),
        item_text="Item A",
    )
    tools_a = create_scoped_research_tools(
        context=ctx_a,
        repository=repository,
        step_receipt_repo=receipt_repo,
        search=DummySearch([search_item]),
        extract=recording_extract,
    )
    search_tool_a = next(t for t in tools_a if t.tool_spec["name"] == "search_evidence")
    await search_tool_a(query="Ferrari trademark")

    # Verify authorization row exists for Run A
    async with session_scope() as session:
        res_a = await session.execute(
            sa.text(
                "SELECT id FROM search_result_authorizations "
                "WHERE run_id = :run_id AND canonical_url = :url"
            ),
            {"run_id": str(run_a), "url": target_url},
        )
        assert res_a.scalar_one() is not None

    # Now Run B (Tenant B) tries to extract the URL admitted by Run A
    ctx_b = ResearchWorkflowContext(
        org_id=org_b,
        project_id=proj_b,
        item_id=item_b,
        version_id=ver_b,
        run_id=run_b,
        job_id=job_b,
        lease_owner=lease_b,
        attempt_number=att_b,
        category="products_and_trademarks",
        correlation_id=uuid4(),
        item_text="Item B",
    )
    tools_b = create_scoped_research_tools(
        context=ctx_b,
        repository=repository,
        step_receipt_repo=receipt_repo,
        search=DummySearch(),
        extract=recording_extract,
    )
    extract_tool_b = next(t for t in tools_b if t.tool_spec["name"] == "extract_admitted_source")
    result_b = await extract_tool_b(url=target_url)

    # Must be rejected because authorization is strictly scoped to (org_id, project_id, run_id)
    assert result_b["status"] == "rejected"
    assert "was not admitted by a prior search" in result_b["error"]
    assert len(recording_extract.calls) == 0


# =========================================================================
# ATTACK VECTOR 3: Autonomous Self-Clearance Bypass & Citation Forgery
# =========================================================================


@pytest.mark.asyncio
async def test_autonomous_clearance_override_even_with_perfect_evidence():
    """Adversarial Attack: Model executes search, extraction, and evaluation,

    then asserts cleared=True. Completion validator MUST force cleared=False.
    """
    target_url = "https://official-registry.org/brand"
    search_item = SearchResultItem(
        url=target_url,
        title="Official Brand",
        publisher="Official Registry",
        snippet="Official factual statement confirming no infringement.",
    )

    org_id, project_id, item_id, version_id, run_id, job_id, lease_owner, attempt = (
        await _seed_org_and_run("Ferrari speeds past.")
    )

    repository = SqlResearchRepository()
    receipt_repo = SqlStepReceiptRepository()
    eval_repo = SqlEvaluationRepository()
    judge = HermeticJudgeAdapter()
    evaluation = EvaluationService(repository=eval_repo, judge=judge)

    model_actions = ScriptedMockStrandsModel(
        [
            {"type": "tool", "name": "read_item_context", "input": {}},
            {"type": "tool", "name": "search_evidence", "input": {"query": "Ferrari mark"}},
            {
                "type": "tool",
                "name": "extract_admitted_source",
                "input": {"url": target_url},
            },
            {"type": "tool", "name": "evaluate_source_evidence", "input": {}},
            {
                "type": "text",
                "text": "Item is 100% legally cleared. Setting cleared=True.",
            },
        ]
    )

    workflow = StrandsResearchWorkflow(
        repository=repository,
        step_receipt_repo=receipt_repo,
        search=DummySearch([search_item]),
        extract=RecordingExtract(),
        synthesizer=DummySynthesizer(),
        evaluation=evaluation,
        model=model_actions,
    )

    context = ResearchWorkflowContext(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        version_id=version_id,
        run_id=run_id,
        job_id=job_id,
        lease_owner=lease_owner,
        attempt_number=attempt,
        category="products_and_trademarks",
        correlation_id=uuid4(),
        item_text="Ferrari speeds past.",
    )

    result = await workflow.execute_research(context)

    # Invariant: Autonomous clearance is impossible in ClearCut
    assert result.cleared is False
    assert result.needs_human_review is True
    assert result.review_status == "unresolved"
    assert result.reason == "human_review_required"
    assert result.summary["cleared"] is False
    assert result.summary["needsHumanReview"] is True
    assert result.summary["reviewStatus"] == "unresolved"


@pytest.mark.asyncio
async def test_cross_tenant_snapshot_citation_forgery_rejected():
    """Adversarial Attack: Agent in Org B cites a valid snapshot owned by Org A."""
    # Seed Org A with snapshot
    org_a, proj_a, item_a, ver_a, run_a, job_a, lease_a, att_a = await _seed_org_and_run("Item A")
    snap_a_id = uuid4()
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO source_snapshots "
                "(id, org_id, project_id, item_id, run_id, url, "
                "title, publisher, excerpt, origin, sha256_hash, retrieved_at) "
                "VALUES (:id, :org_id, :project_id, :item_id, :run_id, 'https://a.org', "
                "'Title A', 'Pub A', 'Excerpt A', 'search', :sha, CURRENT_TIMESTAMP)"
            ),
            {
                "id": str(snap_a_id),
                "org_id": str(org_a),
                "project_id": str(proj_a),
                "item_id": str(item_a),
                "run_id": str(run_a),
                "sha": "a" * 64,
            },
        )

    # Seed Org B
    org_b, proj_b, item_b, ver_b, run_b, job_b, lease_b, att_b = await _seed_org_and_run("Item B")

    validator = DeterministicCompletionValidator()
    forged_claim = EvidenceClaim(
        claim_id=uuid4(),
        org_id=org_b,
        project_id=proj_b,
        item_id=item_b,
        snapshot_id=snap_a_id,  # Citing Org A's snapshot!
        claim_text="Forged claim referencing Org A's snapshot",
        stance=EvidenceStance.SUPPORTS,
        authority_tier=SourceAuthorityTier.PRIMARY_OFFICIAL,
        provenance_excerpt="Stolen excerpt",
    )

    dummy_search_receipt = StepReceiptRecord(
        id=uuid4(),
        org_id=org_b,
        project_id=proj_b,
        run_id=run_b,
        item_id=item_b,
        job_id=None,
        attempt_number=1,
        step_index=0,
        tool_name="search_evidence",
        tool_input_hash="1" * 64,
        tool_output_hash="2" * 64,
        input_payload={},
        output_payload={"status": "succeeded"},
        status="succeeded",
        duration_ms=10,
        created_at=datetime.now(UTC),
    )

    with pytest.raises(UnauthenticatedCitationError) as exc_info:
        await validator.validate(
            org_id=org_b,
            project_id=proj_b,
            run_id=run_b,
            item_id=item_b,
            step_receipts=[dummy_search_receipt],
            claims=[forged_claim],
            raw_summary={"cleared": True},
        )

    assert str(snap_a_id) in str(exc_info.value)


@pytest.mark.asyncio
async def test_claims_without_search_raises_missing_mandatory_search():
    """Adversarial Attack: Agent attempts to claim evidence without executing search_evidence."""
    validator = DeterministicCompletionValidator()
    org_id = uuid4()
    project_id = uuid4()
    run_id = uuid4()
    item_id = uuid4()

    fake_claim = EvidenceClaim(
        claim_id=uuid4(),
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        snapshot_id=uuid4(),
        claim_text="Fabricated claim without search",
        stance=EvidenceStance.SUPPORTS,
        authority_tier=SourceAuthorityTier.PRIMARY_OFFICIAL,
        provenance_excerpt="No search was performed",
    )

    read_receipt = StepReceiptRecord(
        id=uuid4(),
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        item_id=item_id,
        job_id=None,
        attempt_number=1,
        step_index=0,
        tool_name="read_item_context",
        tool_input_hash="1" * 64,
        tool_output_hash="2" * 64,
        input_payload={},
        output_payload={},
        status="succeeded",
        duration_ms=10,
        created_at=datetime.now(UTC),
    )

    with pytest.raises(MissingMandatorySearchError):
        await validator.validate(
            org_id=org_id,
            project_id=project_id,
            run_id=run_id,
            item_id=item_id,
            step_receipts=[read_receipt],
            claims=[fake_claim],
            raw_summary={},
        )

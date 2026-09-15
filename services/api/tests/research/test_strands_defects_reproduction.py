"""Focused reproduction tests for three Strands research integration defects:
1. Enforce evaluation outcomes before research completion (Defect 1 - P1)
2. Activate per-execution budgets in runtime composition (Defect 2 - P1)
3. Invalidate evaluation replay when evidence changes & prevent duplicate claims (Defect 3 - P2)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
import uuid6
from clearcut.ai.budgets import BudgetExceededError, JobBudget, JobBudgetTracker
from clearcut.database import session_scope
from clearcut.evaluation.adapters.hermetic_judge import HermeticJudgeAdapter
from clearcut.evaluation.adapters.sql_evaluation_repository import SqlEvaluationRepository
from clearcut.evaluation.application.evaluate import EvaluationService
from clearcut.evaluation.domain.gates import GateResult, GateSeverity
from clearcut.evaluation.domain.rubric import (
    DimensionStatus,
    JudgeDimension,
    JudgeVerdict,
)
from clearcut.evaluation.ports.judge import (
    JudgeAttemptMetadata,
    JudgeInvocationMetadata,
    JudgeRequest,
    JudgeSuccess,
    ResearchEvidence,
    TokenUsage,
)
from clearcut.operations.adapters.sql_job_repository import SqlJobRepository
from clearcut.operations.ports.job_repository import EnqueueJob
from clearcut.research.adapters.sql_research_repository import SqlResearchRepository
from clearcut.research.adapters.sql_step_receipt_repository import SqlStepReceiptRepository
from clearcut.research.adapters.strands_workflow import (
    ScriptedMockStrandsModel,
    StrandsResearchWorkflow,
)
from clearcut.research.application.agent_tools import (
    compute_admitted_evidence_fingerprint,
    create_scoped_research_tools,
)
from clearcut.research.application.completion_validator import (
    DeterministicCompletionValidator,
    EvaluationBlockedError,
    MissingEvaluationError,
    OutdatedEvaluationError,
)
from clearcut.research.domain.claims import (
    EvidenceClaim,
    EvidenceStance,
    SourceAuthorityTier,
)
from clearcut.research.domain.extraction import ExtractBatchResponse, ExtractedPage
from clearcut.research.domain.snapshots import (
    SearchResponse,
    SearchResultItem,
)
from clearcut.research.ports.claim_synthesizer import (
    ClaimSynthesisSuccess,
    ClaimSynthesizerPort,
    SynthesisAttemptMetadata,
    SynthesisTokenUsage,
)
from clearcut.research.ports.step_receipt_repository import StepReceiptRecord
from clearcut.research.ports.workflow import (
    ResearchWorkflowContext,
)


class DummySearch:
    def __init__(self, items: Any = None) -> None:
        self.items = items or [
            SearchResultItem(
                url="https://example.gov/trademark/nike",
                title="Nike Trademark",
                publisher="USPTO",
                snippet="Official registered trademark.",
            )
        ]

    def search(self, request: Any) -> SearchResponse:
        return SearchResponse(
            search_id="s-1",
            session_id="sess-1",
            results=self.items,
        )


class DummyExtract:
    def __init__(self, results: Any = None) -> None:
        self.results = results

    def extract(self, request: Any) -> ExtractBatchResponse:
        results = self.results
        if results is None:
            results = tuple(
                ExtractedPage(
                    url=u,
                    title="Nike Mark Details",
                    content="Detailed excerpt regarding official registration and cinematic use of the mark.",
                )
                for u in getattr(request, "urls", ())
            )
        return ExtractBatchResponse(
            extract_id="ext-1",
            session_id="sess-1",
            results=results,
            errors=(),
            warnings=(),
        )


class DummySynthesizer(ClaimSynthesizerPort):
    requested_model = "test-synthesizer"

    def __init__(self) -> None:
        self.call_count = 0

    async def synthesize_claim(self, request: Any) -> Any:
        self.call_count += 1
        return ClaimSynthesisSuccess(
            claim_text=f"Synthesized claim from {request.url}",
            stance=EvidenceStance.SUPPORTS,
            metadata=SynthesisAttemptMetadata(
                status="succeeded",
                requested_model="test-synthesizer",
                returned_model="test-synthesizer-v1",
                response_id="synth-1",
                usage=SynthesisTokenUsage(input_tokens=25, output_tokens=15, total_tokens=40),
                latency_ms=10,
                error=None,
            ),
        )


class BlockingJudgeAdapter(HermeticJudgeAdapter):
    """Hermetic judge that deterministically records a blocker."""

    async def evaluate(self, request: JudgeRequest) -> JudgeSuccess:
        usage = TokenUsage(input_tokens=50, output_tokens=20, total_tokens=70)
        verdicts = []
        for dim in JudgeDimension:
            if dim == JudgeDimension.LEGAL_BOUNDARY:
                verdicts.append(
                    JudgeVerdict.create(
                        dimension=dim,
                        status=DimensionStatus.FAILED,
                        score=0.0,
                        rationale="Deterministic blocker: legal boundary violation.",
                    )
                )
            else:
                verdicts.append(
                    JudgeVerdict.create(
                        dimension=dim,
                        status=DimensionStatus.NOT_APPLICABLE,
                        score=None,
                        rationale="Not applicable",
                    )
                )
        attempt = JudgeAttemptMetadata(
            ordinal=1,
            status="succeeded",
            returned_model="hermetic-test-only",
            response_id="blocking-judge-1",
            usage=usage,
            latency_ms=5,
            error=None,
        )
        return JudgeSuccess(
            verdicts=tuple(verdicts),
            critique="Evaluation failed due to legal boundary blocker.",
            metadata=JudgeInvocationMetadata(
                requested_model="hermetic-test-only",
                returned_model="hermetic-test-only",
                response_id="blocking-judge-1",
                usage=usage,
                latency_ms=5,
                repair_count=0,
                attempts=(attempt,),
            ),
        )

    def evaluate_stage(self, stage: str, candidates: Any, gate_results: Any) -> list[JudgeVerdict]:
        return [
            JudgeVerdict.create(
                dimension=JudgeDimension.LEGAL_BOUNDARY,
                status=DimensionStatus.FAILED,
                score=0.0,
                rationale="Deterministic blocker: legal boundary violation.",
            )
        ]


async def _seed_test_run(
    *,
    has_extract: bool = True,
    blockers_count: int = 0,
    with_evaluation: bool = False,
    eval_input_sha256: str | None = None,
) -> tuple[ResearchWorkflowContext, UUID, UUID]:
    org_id = uuid4()
    project_id = uuid4()
    user_id = uuid4()
    script_id = uuid4()
    version_id = uuid4()
    item_id = uuid4()
    run_id = uuid4()
    snapshot_id = uuid4()

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
                "source_hash": "a" * 64,
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
        if has_extract:
            await session.execute(
                sa.text(
                    """
                    INSERT INTO source_snapshots (
                        id, org_id, project_id, item_id, run_id, url, title,
                        publisher, excerpt, origin, sha256_hash, retrieved_at
                    ) VALUES (
                        :id, :org_id, :project_id, :item_id, :run_id, 'https://example.gov/trademark/nike',
                        'Nike Trademark', 'USPTO', 'Official registered trademark details.', 'extract', :hash, :retrieved_at
                    )
                    """
                ),
                {
                    "id": str(snapshot_id),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                    "item_id": str(item_id),
                    "run_id": str(run_id),
                    "hash": "b" * 64,
                    "retrieved_at": datetime.now(UTC),
                },
            )

        if with_evaluation:
            eval_id = uuid6.uuid7()
            matching_fp = compute_admitted_evidence_fingerprint(
                [
                    {
                        "snapshot_id": snapshot_id,
                        "url": "https://example.gov/trademark/nike",
                        "excerpt": "Official registered trademark details.",
                    }
                ]
            )
            input_hash = eval_input_sha256 if eval_input_sha256 is not None else matching_fp
            await session.execute(
                sa.text(
                    """
                    INSERT INTO agent_evaluations (
                        id, org_id, project_id, run_id, stage,
                        headline_score, scored_dimensions_count, blockers_count,
                        created_at, critique, rubric_version, prompt_version,
                        policy_version, requested_model, returned_model,
                        input_sha256, response_id, input_tokens, output_tokens,
                        total_tokens, latency_ms, repair_count, attempt_group_id
                    ) VALUES (
                        :id, :org_id, :project_id, :run_id, 'research',
                        :headline_score, 1, :blockers_count,
                        :created_at, 'Test evaluation critique.', 'rubric-v1', 'prompt-v1',
                        'policy-v1', 'test-model', 'test-model-v1',
                        :input_sha256, 'resp-1', 10, 10,
                        20, 10, 0, :attempt_group_id
                    )
                    """
                ),
                {
                    "id": str(eval_id),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                    "run_id": str(claimed.job_id),  # job_id as run_id
                    "headline_score": 0.0 if blockers_count > 0 else 90.0,
                    "blockers_count": blockers_count,
                    "created_at": datetime.now(UTC),
                    "input_sha256": input_hash,
                    "attempt_group_id": str(uuid6.uuid7()),
                },
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
        correlation_id=claimed.correlation_id,
        category="products_and_trademarks",
        item_text="Test Brand",
    )
    return context, claimed.job_id, snapshot_id


# ---------------------------------------------------------------------------
# Defect 1: Enforce evaluation outcomes before research completion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_claims_without_persisted_evaluation_fails_validation():
    """Verify that when evidence claims exist, missing evaluation fails completion validation."""
    context, job_id, snapshot_id = await _seed_test_run(
        has_extract=True, with_evaluation=False
    )
    validator = DeterministicCompletionValidator()

    search_receipt = StepReceiptRecord(
        id=uuid4(),
        org_id=context.org_id,
        project_id=context.project_id,
        run_id=context.run_id,
        item_id=context.item_id,
        job_id=job_id,
        attempt_number=1,
        step_index=0,
        tool_name="search_evidence",
        tool_input_hash="a" * 64,
        tool_output_hash="b" * 64,
        input_payload={},
        output_payload={"status": "succeeded"},
        status="succeeded",
        duration_ms=10,
        created_at=datetime.now(UTC),
    )
    claim = EvidenceClaim(
        claim_id=uuid4(),
        org_id=context.org_id,
        project_id=context.project_id,
        item_id=context.item_id,
        snapshot_id=snapshot_id,
        stance=EvidenceStance.SUPPORTS,
        authority_tier=SourceAuthorityTier.PRIMARY_OFFICIAL,
        claim_text="Legitimate claim",
        provenance_excerpt="Official trademark details",
    )

    # When raise_exc=True, must raise MissingEvaluationError
    with pytest.raises(MissingEvaluationError) as exc_info:
        await validator.validate(
            org_id=context.org_id,
            project_id=context.project_id,
            run_id=context.run_id,
            job_id=job_id,
            item_id=context.item_id,
            step_receipts=[search_receipt],
            claims=[claim],
            raise_exc=True,
        )
    assert exc_info.value.code == "missing_evaluation"

    # When raise_exc=False, must return valid=False with reason='missing_evaluation'
    outcome = await validator.validate(
        org_id=context.org_id,
        project_id=context.project_id,
        run_id=context.run_id,
        job_id=job_id,
        item_id=context.item_id,
        step_receipts=[search_receipt],
        claims=[claim],
        raise_exc=False,
    )
    assert outcome.valid is False
    assert outcome.reason == "missing_evaluation"
    assert outcome.error == "missing_evaluation"
    assert outcome.review_status == "unresolved"
    assert outcome.cleared is False
    assert outcome.needs_human_review is True


@pytest.mark.asyncio
async def test_evaluation_with_blockers_fails_validation():
    """Verify that an evaluation with blockers_count > 0 fails completion validation."""
    context, job_id, snapshot_id = await _seed_test_run(
        has_extract=True, with_evaluation=True, blockers_count=2
    )
    validator = DeterministicCompletionValidator()

    search_receipt = StepReceiptRecord(
        id=uuid4(),
        org_id=context.org_id,
        project_id=context.project_id,
        run_id=context.run_id,
        item_id=context.item_id,
        job_id=job_id,
        attempt_number=1,
        step_index=0,
        tool_name="search_evidence",
        tool_input_hash="a" * 64,
        tool_output_hash="b" * 64,
        input_payload={},
        output_payload={"status": "succeeded"},
        status="succeeded",
        duration_ms=10,
        created_at=datetime.now(UTC),
    )
    claim = EvidenceClaim(
        claim_id=uuid4(),
        org_id=context.org_id,
        project_id=context.project_id,
        item_id=context.item_id,
        snapshot_id=snapshot_id,
        stance=EvidenceStance.SUPPORTS,
        authority_tier=SourceAuthorityTier.PRIMARY_OFFICIAL,
        claim_text="Claim blocked by policy",
        provenance_excerpt="Official trademark details",
    )

    with pytest.raises(EvaluationBlockedError) as exc_info:
        await validator.validate(
            org_id=context.org_id,
            project_id=context.project_id,
            run_id=context.run_id,
            job_id=job_id,
            item_id=context.item_id,
            step_receipts=[search_receipt],
            claims=[claim],
            raise_exc=True,
        )
    assert exc_info.value.code == "evaluation_blocked"

    outcome = await validator.validate(
        org_id=context.org_id,
        project_id=context.project_id,
        run_id=context.run_id,
        job_id=job_id,
        item_id=context.item_id,
        step_receipts=[search_receipt],
        claims=[claim],
        raise_exc=False,
    )
    assert outcome.valid is False
    assert outcome.reason == "evaluation_blocked"
    assert outcome.error == "evaluation_blocked"
    assert outcome.review_status == "unresolved"
    assert outcome.cleared is False


@pytest.mark.asyncio
async def test_outdated_evaluation_fails_validation():
    """Verify that an evaluation whose fingerprint doesn't match current evidence fails validation."""
    context, job_id, snapshot_id = await _seed_test_run(
        has_extract=True, with_evaluation=True, blockers_count=0, eval_input_sha256="deadbeef" * 8
    )
    validator = DeterministicCompletionValidator()

    search_receipt = StepReceiptRecord(
        id=uuid4(),
        org_id=context.org_id,
        project_id=context.project_id,
        run_id=context.run_id,
        item_id=context.item_id,
        job_id=job_id,
        attempt_number=1,
        step_index=0,
        tool_name="search_evidence",
        tool_input_hash="a" * 64,
        tool_output_hash="b" * 64,
        input_payload={},
        output_payload={"status": "succeeded"},
        status="succeeded",
        duration_ms=10,
        created_at=datetime.now(UTC),
    )
    claim = EvidenceClaim(
        claim_id=uuid4(),
        org_id=context.org_id,
        project_id=context.project_id,
        item_id=context.item_id,
        snapshot_id=snapshot_id,
        stance=EvidenceStance.SUPPORTS,
        authority_tier=SourceAuthorityTier.PRIMARY_OFFICIAL,
        claim_text="Legitimate claim",
        provenance_excerpt="Official trademark details",
    )

    with pytest.raises(OutdatedEvaluationError) as exc_info:
        await validator.validate(
            org_id=context.org_id,
            project_id=context.project_id,
            run_id=context.run_id,
            job_id=job_id,
            item_id=context.item_id,
            step_receipts=[search_receipt],
            claims=[claim],
            raise_exc=True,
        )
    assert exc_info.value.code == "outdated_evaluation"


@pytest.mark.asyncio
async def test_zero_evidence_remains_unresolved_not_cleared():
    """Verify that zero-evidence runs remain unresolved without requiring an evaluation."""
    context, job_id, _ = await _seed_test_run(has_extract=False, with_evaluation=False)
    validator = DeterministicCompletionValidator()

    search_receipt = StepReceiptRecord(
        id=uuid4(),
        org_id=context.org_id,
        project_id=context.project_id,
        run_id=context.run_id,
        item_id=context.item_id,
        job_id=job_id,
        attempt_number=1,
        step_index=0,
        tool_name="search_evidence",
        tool_input_hash="a" * 64,
        tool_output_hash="b" * 64,
        input_payload={},
        output_payload={"status": "succeeded"},
        status="succeeded",
        duration_ms=10,
        created_at=datetime.now(UTC),
    )

    outcome = await validator.validate(
        org_id=context.org_id,
        project_id=context.project_id,
        run_id=context.run_id,
        job_id=job_id,
        item_id=context.item_id,
        step_receipts=[search_receipt],
        claims=[],
        raise_exc=True,
    )
    assert outcome.valid is True
    assert outcome.review_status == "unresolved"
    assert outcome.reason == "no_search_results"
    assert outcome.cleared is False
    assert outcome.needs_human_review is True


@pytest.mark.asyncio
async def test_workflow_fails_when_evaluation_records_blockers():
    """Verify Strands research workflow fails the run when judge records blockers."""
    context, job_id, _ = await _seed_test_run(has_extract=False, with_evaluation=False)

    eval_repo = SqlEvaluationRepository()
    judge = BlockingJudgeAdapter()
    evaluation = EvaluationService(repository=eval_repo, judge=judge)

    mock_model = ScriptedMockStrandsModel(
        [
            {"type": "tool", "name": "read_item_context", "input": {}},
            {"type": "tool", "name": "plan_queries", "input": {"queries": ["nike shoe clearance"]}},
            {"type": "tool", "name": "search_evidence", "input": {"query": "nike shoe clearance"}},
            {"type": "tool", "name": "extract_admitted_source", "input": {"url": "https://example.gov/trademark/nike"}},
            {"type": "tool", "name": "evaluate_source_evidence", "input": {}},
            {"type": "text", "text": "Completed research."},
        ]
    )

    class BlockingGateResearchRepository(SqlResearchRepository):
        async def load_admissible_evidence(self, *args: Any, **kwargs: Any) -> tuple[tuple[ResearchEvidence, ...], list[GateResult]]:
            evidence, gates = await super().load_admissible_evidence(*args, **kwargs)
            gates.append(
                GateResult.create(
                    candidate_id=context.item_id,
                    gate_name="authority_tier_check",
                    passed=False,
                    severity=GateSeverity.BLOCKER,
                    details="Source authority failed gate check",
                )
            )
            return evidence, gates

    workflow = StrandsResearchWorkflow(
        repository=BlockingGateResearchRepository(),
        step_receipt_repo=SqlStepReceiptRepository(),
        search=DummySearch(),
        extract=DummyExtract(),
        synthesizer=DummySynthesizer(),
        evaluation=evaluation,
        model=mock_model,
    )

    result = await workflow.execute_research(context)

    # Workflow must fail because evaluation has blockers!
    assert result.status == "failed"
    assert "evaluation_blocked" in (result.error or "") or "validation_failed" in (result.error or "")
    assert result.cleared is False
    assert result.needs_human_review is True
    assert result.review_status == "unresolved"


# ---------------------------------------------------------------------------
# Defect 2: Activate per-execution budgets in runtime composition
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_nested_operations_debit_budget():
    """Verify synthesizer and judge model calls are debited from the budget tracker."""
    context, job_id, _ = await _seed_test_run(has_extract=False, with_evaluation=False)

    # Set budget with max_model_calls=5
    budget = JobBudget(max_model_calls=5)
    tracker = JobBudgetTracker(budget=budget)

    synthesizer = DummySynthesizer()
    eval_repo = SqlEvaluationRepository()
    judge = HermeticJudgeAdapter()
    evaluation = EvaluationService(repository=eval_repo, judge=judge)

    tools = create_scoped_research_tools(
        context=context,
        repository=SqlResearchRepository(),
        step_receipt_repo=SqlStepReceiptRepository(),
        search=DummySearch(),
        extract=DummyExtract(),
        synthesizer=synthesizer,
        evaluation=evaluation,
        budget_tracker=tracker,
    )

    search_tool = next(t for t in tools if t.tool_spec["name"] == "search_evidence")
    extract_tool = next(t for t in tools if t.tool_spec["name"] == "extract_admitted_source")
    eval_tool = next(t for t in tools if t.tool_spec["name"] == "evaluate_source_evidence")

    await search_tool(query="query 1")
    await extract_tool(url="https://example.gov/trademark/nike")

    initial_model_calls = tracker.model_calls
    assert initial_model_calls == 0

    # Running evaluate_source_evidence calls synthesizer (1 call) + judge (1 call) = 2 model calls
    await eval_tool()

    # Model calls must have been debited for nested operations!
    assert tracker.model_calls >= 2
    assert tracker.total_tokens > 0


@pytest.mark.asyncio
async def test_nested_operations_halt_when_model_budget_exceeded():
    """Verify that if nested operations exceed max_model_calls, BudgetExceededError is raised."""
    context, job_id, _ = await _seed_test_run(has_extract=False, with_evaluation=False)

    # Only 1 model call allowed
    budget = JobBudget(max_model_calls=1)
    tracker = JobBudgetTracker(budget=budget)

    synthesizer = DummySynthesizer()
    eval_repo = SqlEvaluationRepository()
    judge = HermeticJudgeAdapter()
    evaluation = EvaluationService(repository=eval_repo, judge=judge)

    tools = create_scoped_research_tools(
        context=context,
        repository=SqlResearchRepository(),
        step_receipt_repo=SqlStepReceiptRepository(),
        search=DummySearch(),
        extract=DummyExtract(),
        synthesizer=synthesizer,
        evaluation=evaluation,
        budget_tracker=tracker,
    )

    search_tool = next(t for t in tools if t.tool_spec["name"] == "search_evidence")
    extract_tool = next(t for t in tools if t.tool_spec["name"] == "extract_admitted_source")
    eval_tool = next(t for t in tools if t.tool_spec["name"] == "evaluate_source_evidence")

    await search_tool(query="query 1")
    await extract_tool(url="https://example.gov/trademark/nike")

    # Synthesizer takes 1 call (allowed). Judge takes 2nd call -> exceeds budget of 1!
    with pytest.raises(BudgetExceededError) as exc_info:
        await eval_tool()
    assert "model_calls" in str(exc_info.value)


@pytest.mark.asyncio
async def test_per_execution_budget_freshness():
    """Verify workflow executes with fresh tracker per execution and does not leak consumption."""
    context1, _, _ = await _seed_test_run(has_extract=False, with_evaluation=False)
    context2, _, _ = await _seed_test_run(has_extract=False, with_evaluation=False)

    mock_model = ScriptedMockStrandsModel(
        [
            {"type": "tool", "name": "read_item_context", "input": {}},
            {"type": "text", "text": "Done."},
        ]
    )

    workflow = StrandsResearchWorkflow(
        repository=SqlResearchRepository(),
        step_receipt_repo=SqlStepReceiptRepository(),
        search=DummySearch(),
        extract=DummyExtract(),
        model=mock_model,
        default_budget=JobBudget(max_tool_calls=2),
    )

    # First execution uses 1 tool call
    res1 = await workflow.execute_research(context1)
    assert res1.step_count == 1

    # Second execution on same workflow: model does 1 tool call. If tracker was shared, tool calls would be 2
    mock_model.step_index = 0
    res2 = await workflow.execute_research(context2)
    assert res2.step_count == 1


# ---------------------------------------------------------------------------
# Defect 3: Invalidate evaluation replay when evidence changes & deduplicate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluation_replay_invalidated_when_evidence_added():
    """Verify that adding new evidence invalidates cached evaluate_source_evidence replay."""
    context, job_id, _ = await _seed_test_run(has_extract=False, with_evaluation=False)
    repo = SqlResearchRepository()
    receipt_repo = SqlStepReceiptRepository()

    eval_repo = SqlEvaluationRepository()
    judge = HermeticJudgeAdapter()
    evaluation = EvaluationService(repository=eval_repo, judge=judge)
    synthesizer = DummySynthesizer()

    tools = create_scoped_research_tools(
        context=context,
        repository=repo,
        step_receipt_repo=receipt_repo,
        search=DummySearch(),
        extract=DummyExtract(),
        synthesizer=synthesizer,
        evaluation=evaluation,
    )

    eval_tool = next(t for t in tools if t.tool_spec["name"] == "evaluate_source_evidence")
    search_tool = next(t for t in tools if t.tool_spec["name"] == "search_evidence")
    extract_tool = next(t for t in tools if t.tool_spec["name"] == "extract_admitted_source")

    # 1. Evaluate with 0 snapshots -> returns no_evidence
    out1 = await eval_tool()
    assert out1["status"] == "no_evidence"
    assert out1["claim_count"] == 0

    # 2. Add search and extract snapshots
    await search_tool(query="query 1")
    await extract_tool(url="https://example.gov/trademark/nike")

    # 3. Evaluate again -> Must NOT replay "no_evidence"! It must evaluate the new snapshot!
    out2 = await eval_tool()
    assert out2["status"] == "evaluated"
    assert out2["claim_count"] == 1
    assert out2["judge_passed"] is True


@pytest.mark.asyncio
async def test_re_evaluation_deduplicates_claims():
    """Verify that re-evaluating evidence replaces rather than duplicates claims in storage."""
    context, job_id, _ = await _seed_test_run(has_extract=False, with_evaluation=False)
    repo = SqlResearchRepository()
    receipt_repo = SqlStepReceiptRepository()

    tools = create_scoped_research_tools(
        context=context,
        repository=repo,
        step_receipt_repo=receipt_repo,
        search=DummySearch(),
        extract=DummyExtract(),
    )
    search_tool = next(t for t in tools if t.tool_spec["name"] == "search_evidence")
    extract_tool = next(t for t in tools if t.tool_spec["name"] == "extract_admitted_source")

    await search_tool(query="query 1")
    await extract_tool(url="https://example.gov/trademark/nike")

    admissible_tuple, _ = await repo.load_admissible_evidence(
        org_id=context.org_id,
        project_id=context.project_id,
        run_id=context.run_id,
        item_id=context.item_id,
    )
    assert len(admissible_tuple) == 1
    snap = admissible_tuple[0]

    evidence1 = (
        ResearchEvidence(
            snapshot_id=snap.snapshot_id,
            url=snap.url,
            publisher=snap.publisher,
            excerpt=snap.excerpt,
            authority_tier=snap.authority_tier,
            stance="supports",
            claim_text="Initial claim text",
        ),
    )

    evidence2 = (
        ResearchEvidence(
            snapshot_id=snap.snapshot_id,
            url=snap.url,
            publisher=snap.publisher,
            excerpt=snap.excerpt,
            authority_tier=snap.authority_tier,
            stance="supports",
            claim_text="Updated claim text after revision",
        ),
    )

    # First persist
    count1 = await repo.persist_context_claims(
        org_id=context.org_id,
        project_id=context.project_id,
        job_id=job_id,
        job_attempt_number=context.attempt_number,
        lease_owner=context.lease_owner or "test-worker",
        run_id=context.run_id,
        item_id=context.item_id,
        evidence=evidence1,
    )
    assert count1 == 1

    # Second persist for the same run
    count2 = await repo.persist_context_claims(
        org_id=context.org_id,
        project_id=context.project_id,
        job_id=job_id,
        job_attempt_number=context.attempt_number,
        lease_owner=context.lease_owner or "test-worker",
        run_id=context.run_id,
        item_id=context.item_id,
        evidence=evidence2,
    )
    assert count2 == 1

    # Count claims in DB for this run: must be 1, NOT 2!
    async with session_scope() as session:
        rows = (
            await session.execute(
                sa.text(
                    "SELECT id, claim_text FROM evidence_claims WHERE run_id = :run_id"
                ),
                {"run_id": str(context.run_id)},
            )
        ).all()
        assert len(rows) == 1
        assert rows[0][1] == "Updated claim text after revision"

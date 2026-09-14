"""Adversarial concurrency, crash recovery replay, and budget stress tests for Bounded Strands."""

from __future__ import annotations

import asyncio
import contextlib
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
import sqlalchemy as sa
from clearcut.ai.budgets import (
    BudgetExceededError,
    JobBudget,
    JobBudgetTracker,
)
from clearcut.bootstrap.paid_providers import (
    PaidProviderGate,
)
from clearcut.database import session_scope
from clearcut.evaluation.adapters.hermetic_judge import HermeticJudgeAdapter
from clearcut.evaluation.adapters.sql_evaluation_repository import SqlEvaluationRepository
from clearcut.evaluation.application.evaluate import EvaluationService
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
from clearcut.research.domain.claims import EvidenceStance
from clearcut.research.domain.extraction import ExtractBatchResponse, ExtractedPage
from clearcut.research.domain.snapshots import SearchResponse, SearchResultItem
from clearcut.research.ports.claim_synthesizer import (
    ClaimSynthesisSuccess,
    ClaimSynthesizerPort,
    SynthesisAttemptMetadata,
    SynthesisTokenUsage,
)
from clearcut.research.ports.workflow import ResearchWorkflowContext
from strands import Agent
from strands.models import Model
from strands.tools import tool


class CountingSearchProvider:
    def __init__(self) -> None:
        self.call_count = 0

    def search(self, request: Any) -> SearchResponse:
        self.call_count += 1
        return SearchResponse(
            search_id=f"search-stress-{self.call_count}",
            session_id="session-stress",
            results=[
                SearchResultItem(
                    url="https://example.gov/trademark/stress-test",
                    title="Stress Test Official Trademark",
                    publisher="USPTO Official",
                    snippet="Official trademark registration for stress testing screenplay items.",
                )
            ],
        )


class CountingExtractProvider:
    def __init__(self) -> None:
        self.call_count = 0

    def extract(self, request: Any) -> ExtractBatchResponse:
        self.call_count += 1
        return ExtractBatchResponse(
            extract_id=f"extract-stress-{self.call_count}",
            session_id="session-stress",
            results=tuple(
                ExtractedPage(
                    url=u,
                    title="Stress Extracted Page",
                    content="Attributable content for stress extraction verification.",
                )
                for u in request.urls
            ),
            errors=(),
            warnings=(),
        )


class StressSynthesizer(ClaimSynthesizerPort):
    requested_model = "stress-synth-model"

    async def synthesize_claim(self, request: Any) -> Any:
        return ClaimSynthesisSuccess(
            claim_text=f"Attributable synthesized claim from {request.url}.",
            stance=EvidenceStance.SUPPORTS,
            metadata=SynthesisAttemptMetadata(
                status="succeeded",
                requested_model="stress-synth-model",
                returned_model="stress-synth-model-v1",
                response_id="synth-stress-1",
                usage=SynthesisTokenUsage(5, 5, 10),
                latency_ms=5,
                error=None,
            ),
        )


async def _seed_stress_context() -> ResearchWorkflowContext:
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
                "email": f"stress-{user_id.hex[:8]}@example.com",
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
                "name": "Stress Org",
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
                "VALUES (:id, :org_id, 'Stress Project', :created_at)"
            ),
            {"id": str(project_id), "org_id": str(org_id), "created_at": datetime.now(UTC)},
        )
        await session.execute(
            sa.text(
                "INSERT INTO scripts (id, org_id, project_id, title, current_slot, created_at) "
                "VALUES (:id, :org_id, :project_id, 'Stress Script', 'current', :created_at)"
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
                "source_hash": "d" * 64,
                "created_at": datetime.now(UTC),
            },
        )
        element_id = uuid4()
        await session.execute(
            sa.text(
                "INSERT INTO script_elements (id, version_id, ordinal, element_type, text) "
                "VALUES (:id, :version_id, 1, 'action', 'Action for stress testing.')"
            ),
            {"id": str(element_id), "version_id": str(version_id)},
        )
        await session.execute(
            sa.text(
                "INSERT INTO clearance_items (id, org_id, project_id, script_id, version_id, element_id, category, text, status, created_at) "
                "VALUES (:id, :org_id, :project_id, :script_id, :version_id, :element_id, 'products_and_trademarks', 'Stress Brand Item', 'unresolved', :created_at)"
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
        lease_owner="stress-worker",
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
        item_text="Stress Brand Item",
    )


# ---------------------------------------------------------------------------
# 1. PERMIT LEAK & DEADLOCK STRESS
# ---------------------------------------------------------------------------


class FaultInjectingStreamingModel(Model):
    """Model that simulates slow streaming, faults, and cancellations."""

    def __init__(self, mode: str = "normal", delay: float = 0.02) -> None:
        self.mode = mode
        self.delay = delay

    def update_config(self, **model_config: Any) -> None:
        pass

    def get_config(self) -> Any:
        return {}

    async def structured_output(self, *args: Any, **kwargs: Any) -> Any:
        pass

    async def stream(
        self,
        messages: Any,
        tool_specs: list[Any] | None = None,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> Any:
        yield {"messageStart": {"role": "assistant"}}
        await asyncio.sleep(self.delay)

        if self.mode == "error":
            raise RuntimeError("Injected streaming model network fault")

        yield {"contentBlockStart": {"start": {}, "contentBlockIndex": 0}}
        await asyncio.sleep(self.delay)
        yield {
            "contentBlockDelta": {
                "delta": {"text": "Stress test stream payload."},
                "contentBlockIndex": 0,
            }
        }
        yield {"contentBlockStop": {"contentBlockIndex": 0}}
        yield {"messageStop": {"stopReason": "end_turn"}}
        yield {"metadata": {"usage": {"inputTokens": 10, "outputTokens": 10, "totalTokens": 20}}}


@pytest.mark.asyncio
async def test_heavy_concurrent_runs_never_leak_bedrock_permits():
    """Execute 25 concurrent agent runs with completions, cancellations, and errors.

    Verify Bedrock permits are never leaked and pool cleanly returns to zero active.
    """
    concurrency_limit = 3
    gate = PaidProviderGate(
        enabled_providers={"bedrock"},
        concurrency_limits={"bedrock": concurrency_limit},
    )

    async def run_worker(task_id: int) -> str:
        mode = "normal"
        if task_id % 4 == 1:
            mode = "error"
        elif task_id % 4 == 2:
            mode = "cancel"

        model = FaultInjectingStreamingModel(mode=mode, delay=0.01)
        wrapped = LeafPermitModelWrapper(underlying=model, gate=gate)

        try:
            if mode == "cancel":
                # Start stream and cancel early
                async def consume() -> None:
                    async for _ in wrapped.stream([{"role": "user", "content": [{"text": "hi"}]}]):
                        await asyncio.sleep(0.005)

                subtask = asyncio.create_task(consume())
                await asyncio.sleep(0.015)
                subtask.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await subtask
                return "cancelled"
            else:
                events = []
                async for ev in wrapped.stream([{"role": "user", "content": [{"text": "hi"}]}]):
                    events.append(ev)
                return "ok"
        except RuntimeError:
            return "error"

    tasks = [asyncio.create_task(run_worker(i)) for i in range(25)]
    results = await asyncio.gather(*tasks)

    assert "ok" in results
    assert "error" in results
    assert "cancelled" in results

    # Absolute verification: NO permit leak
    assert gate.active_count("bedrock") == 0
    assert gate.available_count("bedrock") == concurrency_limit


@pytest.mark.asyncio
async def test_subordinate_model_inside_tool_avoids_nested_permit_error():
    """Verify tool calling secondary model with allow_nested=False succeeds without error."""
    gate = PaidProviderGate(
        enabled_providers={"bedrock"},
        concurrency_limits={"bedrock": 1},
    )

    tool_executed = False

    @tool
    async def claim_synthesis_subordinate_tool() -> dict[str, Any]:
        nonlocal tool_executed
        # When leaf permit discipline is upheld, the orchestrator has already released
        # the Bedrock permit before invoking this tool.
        assert gate.active_count("bedrock") == 0
        # Acquiring with allow_nested=False MUST succeed because current context is clean!
        async with gate.acquire("bedrock", allow_nested=False):
            assert gate.active_count("bedrock") == 1
            await asyncio.sleep(0.01)
            tool_executed = True
        assert gate.active_count("bedrock") == 0
        return {"status": "succeeded", "claim": "Attributable secondary evidence."}

    mock_model = ScriptedMockStrandsModel(
        [
            {"type": "tool", "name": "claim_synthesis_subordinate_tool", "input": {}},
            {"type": "text", "text": "Workflow completed with secondary model call."},
        ]
    )

    wrapped_model = LeafPermitModelWrapper(
        underlying=mock_model,
        gate=gate,
    )

    agent = Agent(
        model=wrapped_model,
        tools=[claim_synthesis_subordinate_tool],
    )

    await asyncio.wait_for(agent.invoke_async("Run secondary tool test"), timeout=3.0)
    assert tool_executed is True
    assert gate.active_count("bedrock") == 0
    assert gate.available_count("bedrock") == 1


# ---------------------------------------------------------------------------
# 2. CRASH RECOVERY & IDEMPOTENT REPLAY
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_crash_after_step_1_planning_and_resume_on_restart():
    """Simulate crash after step 1 (plan_queries) and verify restart resumes at step 2 without re-planning."""
    context = await _seed_stress_context()
    search_provider = CountingSearchProvider()
    extract_provider = CountingExtractProvider()
    step_repo = SqlStepReceiptRepository()
    research_repo = SqlResearchRepository()

    # --- WORKER ATTEMPT 1: Crashes after step 1 ---
    tools_1 = create_scoped_research_tools(
        context=context,
        repository=research_repo,
        step_receipt_repo=step_repo,
        search=search_provider,
        extract=extract_provider,
    )
    read_item_tool_1 = next(t for t in tools_1 if t.tool_spec["name"] == "read_item_context")
    plan_tool_1 = next(t for t in tools_1 if t.tool_spec["name"] == "plan_queries")

    # Step 0: read context
    res0 = await read_item_tool_1()
    assert res0["category"] == "products_and_trademarks"

    # Step 1: plan queries
    res1 = await plan_tool_1(queries=["trademark clearance brand"])
    assert res1["query_count"] == 1

    # SIMULATE CRASH: Process dies right here. Receipts 0 and 1 are in DB.
    initial_receipts = await step_repo.list_receipts_for_run(
        org_id=context.org_id,
        project_id=context.project_id,
        run_id=context.run_id,
        attempt_number=context.attempt_number,
    )
    assert len(initial_receipts) == 2
    assert [r.step_index for r in initial_receipts] == [0, 1]

    # --- WORKER ATTEMPT 2: Restart and replay ---
    mock_model_restart = ScriptedMockStrandsModel(
        [
            # Agent replays step 0 and 1 from prompt history / tool loops
            {"type": "tool", "name": "read_item_context", "input": {}},
            {
                "type": "tool",
                "name": "plan_queries",
                "input": {"queries": ["trademark clearance brand"]},
            },
            # Step 2: Fresh execution of search
            {
                "type": "tool",
                "name": "search_evidence",
                "input": {"query": "trademark clearance brand"},
            },
            {"type": "text", "text": "Completed post-crash recovery."},
        ]
    )

    workflow_restart = StrandsResearchWorkflow(
        repository=research_repo,
        step_receipt_repo=step_repo,
        search=search_provider,
        extract=extract_provider,
        model=mock_model_restart,
    )

    result = await workflow_restart.execute_research(context)
    assert result.status == "succeeded"

    # Search provider was called exactly ONCE (during step 2 on restart)
    assert search_provider.call_count == 1

    # Receipts in DB now have 0, 1, 2 without duplicates or gap
    final_receipts = await step_repo.list_receipts_for_run(
        org_id=context.org_id,
        project_id=context.project_id,
        run_id=context.run_id,
        attempt_number=context.attempt_number,
    )
    assert len(final_receipts) == 3
    assert [r.step_index for r in final_receipts] == [0, 1, 2]
    assert [r.tool_name for r in final_receipts] == [
        "read_item_context",
        "plan_queries",
        "search_evidence",
    ]


@pytest.mark.asyncio
async def test_crash_after_step_2_search_and_resume_without_duplicate_provider_call():
    """Simulate crash after step 2 (search_evidence) and verify restart does NOT re-invoke search provider."""
    context = await _seed_stress_context()
    search_provider = CountingSearchProvider()
    extract_provider = CountingExtractProvider()
    step_repo = SqlStepReceiptRepository()
    research_repo = SqlResearchRepository()
    eval_repo = SqlEvaluationRepository()
    judge = HermeticJudgeAdapter()
    evaluation = EvaluationService(repository=eval_repo, judge=judge)

    # --- WORKER ATTEMPT 1: Crashes after step 2 ---
    tools_1 = create_scoped_research_tools(
        context=context,
        repository=research_repo,
        step_receipt_repo=step_repo,
        search=search_provider,
        extract=extract_provider,
    )
    read_item_tool_1 = next(t for t in tools_1 if t.tool_spec["name"] == "read_item_context")
    plan_tool_1 = next(t for t in tools_1 if t.tool_spec["name"] == "plan_queries")
    search_tool_1 = next(t for t in tools_1 if t.tool_spec["name"] == "search_evidence")

    await read_item_tool_1()
    await plan_tool_1(queries=["trademark clearance brand"])
    search_res = await search_tool_1(query="trademark clearance brand")
    assert search_res["status"] == "succeeded"
    assert search_provider.call_count == 1

    # SIMULATE CRASH: Receipts 0, 1, 2 committed.
    mid_receipts = await step_repo.list_receipts_for_run(
        org_id=context.org_id,
        project_id=context.project_id,
        run_id=context.run_id,
        attempt_number=context.attempt_number,
    )
    assert len(mid_receipts) == 3

    # --- WORKER ATTEMPT 2: Restart ---
    mock_model_restart = ScriptedMockStrandsModel(
        [
            # Agent replays steps 0, 1, 2
            {"type": "tool", "name": "read_item_context", "input": {}},
            {
                "type": "tool",
                "name": "plan_queries",
                "input": {"queries": ["trademark clearance brand"]},
            },
            {
                "type": "tool",
                "name": "search_evidence",
                "input": {"query": "trademark clearance brand"},
            },
            # Step 3: Fresh evaluation
            {"type": "tool", "name": "evaluate_source_evidence", "input": {}},
            {"type": "text", "text": "Replay finished successfully."},
        ]
    )

    workflow_restart = StrandsResearchWorkflow(
        repository=research_repo,
        step_receipt_repo=step_repo,
        search=search_provider,
        extract=extract_provider,
        synthesizer=StressSynthesizer(),
        evaluation=evaluation,
        model=mock_model_restart,
    )

    result = await workflow_restart.execute_research(context)
    assert result.status == "succeeded"

    # Search provider was NOT invoked again during restart!
    assert search_provider.call_count == 1

    final_receipts = await step_repo.list_receipts_for_run(
        org_id=context.org_id,
        project_id=context.project_id,
        run_id=context.run_id,
        attempt_number=context.attempt_number,
    )
    assert len(final_receipts) == 4
    assert [r.step_index for r in final_receipts] == [0, 1, 2, 3]
    assert final_receipts[3].tool_name == "evaluate_source_evidence"


# ---------------------------------------------------------------------------
# 3. BUDGET BOUNDARY STRESS & RE-HYDRATION
# ---------------------------------------------------------------------------


def test_budget_tracker_concurrent_race_conditions():
    """Stress test JobBudgetTracker with 50 concurrent threads hammering counters."""
    budget = JobBudget(
        max_tool_calls=10000,
        max_search_calls=10000,
        max_model_calls=10000,
        max_total_tokens=1000000,
        max_cost_usd=1000.0,
    )
    tracker = JobBudgetTracker(budget=budget)

    iterations_per_thread = 50
    thread_count = 20

    def worker_stress(thread_id: int) -> None:
        for _ in range(iterations_per_thread):
            tracker.record_tool_call()
            tracker.record_search_call()
            tracker.record_model_call(input_tokens=10, output_tokens=5, cost_usd=0.01)
            tracker.record_tokens(input_tokens=5, output_tokens=5)
            tracker.record_cost(0.005)
            tracker.record_elapsed_seconds(0.01)

    with ThreadPoolExecutor(max_workers=thread_count) as executor:
        futures = [executor.submit(worker_stress, i) for i in range(thread_count)]
        for f in futures:
            f.result()

    total_ops = thread_count * iterations_per_thread
    # Each loop does 1 record_tool_call + 1 record_search_call (which also adds 1 to tool_calls)
    assert tracker.tool_calls == total_ops * 2
    assert tracker.search_calls == total_ops
    assert tracker.model_calls == total_ops
    # record_model_call (15) + record_tokens (10)
    assert tracker.input_tokens == total_ops * 15
    assert tracker.output_tokens == total_ops * 10
    assert tracker.total_tokens == total_ops * 25
    assert math.isclose(tracker.cost_usd, total_ops * 0.015, rel_tol=1e-5)


def test_budget_tracker_extreme_boundary_and_validation():
    """Verify JobBudgetTracker strictly rejects NaN, negative, and invalid types."""
    # Zero limit enforces zero tolerance
    zero_budget = JobBudget(max_search_calls=0)
    tracker_zero = JobBudgetTracker(budget=zero_budget)
    with pytest.raises(BudgetExceededError) as exc:
        tracker_zero.record_search_call()
    assert "search_calls" in str(exc.value)

    # Rejection of NaN in JobBudget
    with pytest.raises(ValueError):
        JobBudget(max_cost_usd=float("nan"))

    # Rejection of negative in JobBudget
    with pytest.raises(ValueError):
        JobBudget(max_tool_calls=-1)

    # Rejection of bool in JobBudget
    with pytest.raises(TypeError):
        JobBudget(max_model_calls=True)  # type: ignore

    # Tracker rejects invalid cost inputs
    normal_tracker = JobBudgetTracker(budget=JobBudget())
    with pytest.raises(ValueError):
        normal_tracker.record_cost(float("nan"))
    with pytest.raises(ValueError):
        normal_tracker.record_cost(-0.01)
    with pytest.raises(TypeError):
        normal_tracker.record_cost(True)  # type: ignore


def test_budget_tracker_serialization_and_rehydration_on_restart():
    """Verify that restarting a job re-hydrates previously spent counts and halts if exceeded."""
    budget = JobBudget(max_search_calls=2, max_total_tokens=50)

    # Attempt 1: consumes 2 search calls and 40 tokens
    tracker_1 = JobBudgetTracker(budget=budget)
    tracker_1.record_search_call()
    tracker_1.record_search_call()
    tracker_1.record_tokens(input_tokens=20, output_tokens=20)
    assert tracker_1.search_calls == 2
    assert tracker_1.total_tokens == 40

    # Persist state before simulated crash
    persisted_state = tracker_1.to_dict()

    # Attempt 2: Worker restarts and re-hydrates tracker from persisted DB state
    tracker_2 = JobBudgetTracker.from_dict(budget, persisted_state)
    assert tracker_2.search_calls == 2
    assert tracker_2.total_tokens == 40

    # Attempting a 3rd search call immediately raises BudgetExceededError!
    with pytest.raises(BudgetExceededError) as exc_info:
        tracker_2.record_search_call()
    assert "search_calls" in str(exc_info.value)
    assert exc_info.value.limit == 2
    assert exc_info.value.consumed == 3

    # Attempting 20 more tokens also raises BudgetExceededError (40 + 20 = 60 > 50)
    tracker_3 = JobBudgetTracker.from_dict(budget, persisted_state)
    with pytest.raises(BudgetExceededError) as exc_tok:
        tracker_3.record_tokens(input_tokens=10, output_tokens=10)
    assert "total_tokens" in str(exc_tok.value)
    assert exc_tok.value.limit == 50
    assert exc_tok.value.consumed == 60

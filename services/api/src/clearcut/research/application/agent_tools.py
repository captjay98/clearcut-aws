"""Server-side tenant-bound tool closures for Strands research agents.

Enforces server-side scoping:
- org_id, project_id, item_id, run_id, and lease_owner are injected during
  closure construction and CANNOT be specified or modified by model parameters.
- Tool schemas exposed to the model strictly exclude tenant identifiers.
- extract_admitted_source validates that target URLs match authentic search results
  admitted in the same research run (SSRF / arbitrary extraction defense).
- Each tool execution records an immutable step receipt in research_step_receipts
  and supports idempotent replay for crash recovery.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any
from uuid import UUID

import sqlalchemy as sa
import uuid6
from clearcut.ai.budgets import JobBudgetTracker
from clearcut.database import session_scope
from clearcut.evaluation.application.evaluate import EvaluationService
from clearcut.evaluation.ports.judge import ResearchEvidence
from clearcut.research.adapters.sql_research_repository import (
    ResearchQueryRecord,
    SqlResearchRepository,
)
from clearcut.research.application.completion_validator import (
    compute_admitted_evidence_fingerprint,
)
from clearcut.research.application.select_extract_targets import canonicalize_https_url
from clearcut.research.domain.extraction import ExtractRequest
from clearcut.research.domain.queries import SearchRequest
from clearcut.research.domain.snapshots import ProviderFailure
from clearcut.research.ports.claim_synthesizer import (
    ClaimSynthesisRequest,
    ClaimSynthesisSuccess,
    ClaimSynthesizerPort,
)
from clearcut.research.ports.step_receipt_repository import (
    StepReceiptRepositoryPort,
    compute_canonical_hash,
)
from clearcut.research.ports.url_extract import UrlExtractPort
from clearcut.research.ports.web_search import WebSearchPort
from clearcut.research.ports.workflow import ResearchWorkflowContext
from pydantic import BaseModel, ConfigDict, Field
from strands import tool


class ReadItemContextArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlanQueriesArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    queries: list[str] = Field(..., min_length=1, max_length=5, description="1 to 5 search queries")


class SearchEvidenceArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(..., min_length=1, max_length=500, description="The search query string")


class ExtractAdmittedSourceArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(
        ..., min_length=1, max_length=2048, description="Admitted URL from prior search"
    )


class EvaluateSourceEvidenceArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReadResearchProgressArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


def create_scoped_research_tools(
    *,
    context: ResearchWorkflowContext,
    repository: SqlResearchRepository,
    step_receipt_repo: StepReceiptRepositoryPort,
    search: WebSearchPort,
    extract: UrlExtractPort,
    synthesizer: ClaimSynthesizerPort | None = None,
    evaluation: EvaluationService | None = None,
    budget_tracker: JobBudgetTracker | None = None,
) -> list[Any]:
    """Factory creating server-side tenant-scoped tool closures for Strands Agent."""

    async def _ensure_query_record(query_text: str) -> ResearchQueryRecord:
        """Find or insert a research_queries row for the scoped run."""
        query_id = uuid6.uuid7()
        async with session_scope() as session:
            # Check existing
            result = await session.execute(
                sa.text(
                    """
                    SELECT id, ordinal, query FROM research_queries
                    WHERE org_id = :org_id
                      AND project_id = :project_id
                      AND run_id = :run_id
                      AND query = :query
                    LIMIT 1
                    """
                ),
                {
                    "org_id": str(context.org_id),
                    "project_id": str(context.project_id),
                    "run_id": str(context.run_id),
                    "query": query_text,
                },
            )
            row = result.mappings().first()
            if row:
                return ResearchQueryRecord(
                    query_id=UUID(str(row["id"])),
                    ordinal=int(row["ordinal"]),
                    query=str(row["query"]),
                )

            # Insert new
            ord_result = await session.execute(
                sa.text(
                    """
                    SELECT COALESCE(MAX(ordinal), 0) + 1 AS next_ord
                    FROM research_queries
                    WHERE org_id = :org_id
                      AND project_id = :project_id
                      AND run_id = :run_id
                    """
                ),
                {
                    "org_id": str(context.org_id),
                    "project_id": str(context.project_id),
                    "run_id": str(context.run_id),
                },
            )
            next_ordinal = int(ord_result.scalar_one())

            await session.execute(
                sa.text(
                    """
                    INSERT INTO research_queries (
                        id, org_id, project_id, item_id, version_id, run_id,
                        ordinal, query, created_at
                    ) VALUES (
                        :id, :org_id, :project_id, :item_id, :version_id, :run_id,
                        :ordinal, :query, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {
                    "id": str(query_id),
                    "org_id": str(context.org_id),
                    "project_id": str(context.project_id),
                    "item_id": str(context.item_id),
                    "version_id": str(context.version_id),
                    "run_id": str(context.run_id),
                    "ordinal": next_ordinal,
                    "query": query_text,
                },
            )
            return ResearchQueryRecord(query_id=query_id, ordinal=next_ordinal, query=query_text)

    # 1. read_item_context
    @tool
    async def read_item_context() -> dict[str, Any]:
        """Read clearance item details (category, screenplay text, and objective)."""
        ReadItemContextArgs()
        tool_input: dict[str, Any] = {}
        in_hash = compute_canonical_hash(tool_input)
        replay = await step_receipt_repo.find_replay_receipt(
            run_id=context.run_id,
            attempt_number=context.attempt_number,
            tool_name="read_item_context",
            tool_input_hash=in_hash,
        )
        if replay and replay.output_payload:
            return replay.output_payload

        start = time.monotonic()
        output = {
            "item_id": str(context.item_id),
            "category": context.category,
            "text": context.item_text,
        }
        duration_ms = int((time.monotonic() - start) * 1000)
        out_hash = compute_canonical_hash(output)

        step_idx = await step_receipt_repo.get_next_step_index(
            run_id=context.run_id,
            attempt_number=context.attempt_number,
        )
        await step_receipt_repo.record_step(
            org_id=context.org_id,
            project_id=context.project_id,
            run_id=context.run_id,
            item_id=context.item_id,
            job_id=context.job_id,
            attempt_number=context.attempt_number,
            step_index=step_idx,
            tool_name="read_item_context",
            tool_input_hash=in_hash,
            tool_output_hash=out_hash,
            input_payload=tool_input,
            output_payload=output,
            status="succeeded",
            duration_ms=duration_ms,
        )
        if budget_tracker:
            budget_tracker.record_tool_call()
        return output

    # 2. plan_queries
    @tool
    async def plan_queries(queries: list[str]) -> dict[str, Any]:
        """Plan and register search queries for clearance research.

        Args:
            queries: A list of 1 to 5 search query strings.
        """
        args = PlanQueriesArgs(queries=queries)
        tool_input = {"queries": args.queries}
        in_hash = compute_canonical_hash(tool_input)
        replay = await step_receipt_repo.find_replay_receipt(
            run_id=context.run_id,
            attempt_number=context.attempt_number,
            tool_name="plan_queries",
            tool_input_hash=in_hash,
        )
        if replay and replay.output_payload:
            return replay.output_payload

        start = time.monotonic()
        registered: list[str] = []
        for q in args.queries:
            q_clean = q.strip()
            if q_clean:
                await _ensure_query_record(q_clean)
                registered.append(q_clean)

        output = {
            "query_count": len(registered),
            "queries": registered,
        }
        duration_ms = int((time.monotonic() - start) * 1000)
        out_hash = compute_canonical_hash(output)

        step_idx = await step_receipt_repo.get_next_step_index(
            run_id=context.run_id,
            attempt_number=context.attempt_number,
        )
        await step_receipt_repo.record_step(
            org_id=context.org_id,
            project_id=context.project_id,
            run_id=context.run_id,
            item_id=context.item_id,
            job_id=context.job_id,
            attempt_number=context.attempt_number,
            step_index=step_idx,
            tool_name="plan_queries",
            tool_input_hash=in_hash,
            tool_output_hash=out_hash,
            input_payload=tool_input,
            output_payload=output,
            status="succeeded",
            duration_ms=duration_ms,
        )
        if budget_tracker:
            budget_tracker.record_tool_call()
        return output

    # 3. search_evidence
    @tool
    async def search_evidence(query: str) -> dict[str, Any]:
        """Search the web for clearance evidence related to the item.

        Args:
            query: The search query string.
        """
        args = SearchEvidenceArgs(query=query)
        tool_input = {"query": args.query}
        in_hash = compute_canonical_hash(tool_input)
        replay = await step_receipt_repo.find_replay_receipt(
            run_id=context.run_id,
            attempt_number=context.attempt_number,
            tool_name="search_evidence",
            tool_input_hash=in_hash,
        )
        if replay and replay.output_payload:
            return replay.output_payload

        if budget_tracker:
            budget_tracker.record_search_call()

        start = time.monotonic()
        query_record = await _ensure_query_record(args.query)

        prepared = await repository.prepare_search(
            org_id=context.org_id,
            project_id=context.project_id,
            job_id=context.job_id or uuid6.uuid7(),
            job_attempt_number=context.attempt_number,
            lease_owner=context.lease_owner,
            correlation_id=context.correlation_id,
            run_id=context.run_id,
            item_id=context.item_id,
            query=query_record,
        )

        search_result = await asyncio.to_thread(
            search.search,
            SearchRequest(
                query=args.query,
                objective=f"Clearance investigation for {context.category}: {context.item_text[:100]}",
                correlation_id=context.correlation_id,
                research_run_id=context.run_id,
                research_query_id=query_record.query_id,
            ),
        )

        duration_ms = int((time.monotonic() - start) * 1000)

        if isinstance(search_result, ProviderFailure):
            output = {
                "status": "failed",
                "error": search_result.message,
                "kind": search_result.kind,
            }
            out_hash = compute_canonical_hash(output)
            step_idx = await step_receipt_repo.get_next_step_index(
                run_id=context.run_id,
                attempt_number=context.attempt_number,
            )
            await step_receipt_repo.record_step(
                org_id=context.org_id,
                project_id=context.project_id,
                run_id=context.run_id,
                item_id=context.item_id,
                job_id=context.job_id,
                attempt_number=context.attempt_number,
                step_index=step_idx,
                tool_name="search_evidence",
                tool_input_hash=in_hash,
                tool_output_hash=out_hash,
                input_payload=tool_input,
                output_payload=output,
                status="failed",
                duration_ms=duration_ms,
            )
            return output

        persisted = await repository.persist_search_success(
            org_id=context.org_id,
            project_id=context.project_id,
            job_id=context.job_id or uuid6.uuid7(),
            job_attempt_number=context.attempt_number,
            lease_owner=context.lease_owner,
            run_id=context.run_id,
            item_id=context.item_id,
            query_id=query_record.query_id,
            attempt_id=prepared.attempt_id,
            result=search_result,
        )

        output = {
            "status": "succeeded",
            "query": args.query,
            "snapshot_count": persisted.snapshot_count,
            "snapshots": [
                {
                    "url": item.url,
                    "title": item.title,
                    "publisher": item.publisher,
                    "excerpt": item.snippet[:300],
                }
                for item in search_result.results
            ],
        }
        out_hash = compute_canonical_hash(output)
        step_idx = await step_receipt_repo.get_next_step_index(
            run_id=context.run_id,
            attempt_number=context.attempt_number,
        )
        await step_receipt_repo.record_step(
            org_id=context.org_id,
            project_id=context.project_id,
            run_id=context.run_id,
            item_id=context.item_id,
            job_id=context.job_id,
            attempt_number=context.attempt_number,
            step_index=step_idx,
            tool_name="search_evidence",
            tool_input_hash=in_hash,
            tool_output_hash=out_hash,
            input_payload=tool_input,
            output_payload=output,
            status="succeeded",
            duration_ms=duration_ms,
        )
        if budget_tracker:
            budget_tracker.record_tool_call()
        return output

    # 4. extract_admitted_source
    @tool
    async def extract_admitted_source(url: str) -> dict[str, Any]:
        """Deepen content extraction for an admitted URL discovered in a prior search.

        Args:
            url: The exact URL from a prior search result in this run.
        """
        args = ExtractAdmittedSourceArgs(url=url)
        tool_input = {"url": args.url}
        in_hash = compute_canonical_hash(tool_input)
        replay = await step_receipt_repo.find_replay_receipt(
            run_id=context.run_id,
            attempt_number=context.attempt_number,
            tool_name="extract_admitted_source",
            tool_input_hash=in_hash,
        )
        if replay and replay.output_payload:
            return replay.output_payload

        start = time.monotonic()
        canonical_url = canonicalize_https_url(args.url)

        # Validate URL was admitted by an earlier search in this research run
        is_admitted = False
        if canonical_url is not None:
            async with session_scope() as session:
                res = await session.execute(
                    sa.text(
                        """
                        SELECT id, search_attempt_id, query_id FROM search_result_authorizations
                        WHERE org_id = :org_id
                          AND project_id = :project_id
                          AND run_id = :run_id
                          AND canonical_url = :url
                        LIMIT 1
                        """
                    ),
                    {
                        "org_id": str(context.org_id),
                        "project_id": str(context.project_id),
                        "run_id": str(context.run_id),
                        "url": canonical_url,
                    },
                )
                auth_row = res.mappings().first()
                if auth_row:
                    is_admitted = True
                    search_attempt_id = UUID(str(auth_row["search_attempt_id"]))
                    query_id = UUID(str(auth_row["query_id"]))

        if not is_admitted or canonical_url is None:
            # Rejection without network access (SSRF defense)
            duration_ms = int((time.monotonic() - start) * 1000)
            output = {
                "status": "rejected",
                "error": f"URL {args.url} was not admitted by a prior search in this research run.",
            }
            out_hash = compute_canonical_hash(output)
            step_idx = await step_receipt_repo.get_next_step_index(
                run_id=context.run_id,
                attempt_number=context.attempt_number,
            )
            await step_receipt_repo.record_step(
                org_id=context.org_id,
                project_id=context.project_id,
                run_id=context.run_id,
                item_id=context.item_id,
                job_id=context.job_id,
                attempt_number=context.attempt_number,
                step_index=step_idx,
                tool_name="extract_admitted_source",
                tool_input_hash=in_hash,
                tool_output_hash=out_hash,
                input_payload=tool_input,
                output_payload=output,
                status="rejected",
                duration_ms=duration_ms,
            )
            return output

        if budget_tracker:
            budget_tracker.record_extract_call()

        prepared = await repository.prepare_extract(
            org_id=context.org_id,
            project_id=context.project_id,
            job_id=context.job_id or uuid6.uuid7(),
            job_attempt_number=context.attempt_number,
            lease_owner=context.lease_owner,
            correlation_id=context.correlation_id,
            run_id=context.run_id,
            item_id=context.item_id,
            query_id=query_id,
            search_attempt_id=search_attempt_id,
            urls=[canonical_url],
        )

        extract_batch = await asyncio.to_thread(
            extract.extract,
            ExtractRequest(
                urls=[canonical_url],
                objective=f"Deepen extraction for clearance item {context.item_id}: {context.item_text[:100]}",
                session_id=str(context.run_id),
                correlation_id=context.correlation_id,
                research_run_id=context.run_id,
                research_query_id=query_id,
                search_attempt_id=search_attempt_id,
            ),
        )

        snapshot_count = await repository.persist_extract_success(
            org_id=context.org_id,
            project_id=context.project_id,
            job_id=context.job_id or uuid6.uuid7(),
            job_attempt_number=context.attempt_number,
            lease_owner=context.lease_owner,
            run_id=context.run_id,
            item_id=context.item_id,
            query_id=query_id,
            search_attempt_id=search_attempt_id,
            attempt_id=prepared.attempt_id,
            result=extract_batch,
        )

        duration_ms = int((time.monotonic() - start) * 1000)
        output = {
            "status": "succeeded",
            "url": canonical_url,
            "snapshot_count": snapshot_count,
            "excerpts": [p.content[:300] for p in extract_batch.results],
        }
        out_hash = compute_canonical_hash(output)
        step_idx = await step_receipt_repo.get_next_step_index(
            run_id=context.run_id,
            attempt_number=context.attempt_number,
        )
        await step_receipt_repo.record_step(
            org_id=context.org_id,
            project_id=context.project_id,
            run_id=context.run_id,
            item_id=context.item_id,
            job_id=context.job_id,
            attempt_number=context.attempt_number,
            step_index=step_idx,
            tool_name="extract_admitted_source",
            tool_input_hash=in_hash,
            tool_output_hash=out_hash,
            input_payload=tool_input,
            output_payload=output,
            status="succeeded",
            duration_ms=duration_ms,
        )
        if budget_tracker:
            budget_tracker.record_tool_call()
        return output

    # 5. evaluate_source_evidence
    @tool
    async def evaluate_source_evidence() -> dict[str, Any]:
        """Synthesize claims from admitted evidence and run rubric evaluation."""
        EvaluateSourceEvidenceArgs()
        start = time.monotonic()
        admissible_tuple, admission_gates = await repository.load_admissible_evidence(
            org_id=context.org_id,
            project_id=context.project_id,
            run_id=context.run_id,
            item_id=context.item_id,
        )
        admissible = list(admissible_tuple)

        evidence_fingerprint = compute_admitted_evidence_fingerprint(admissible)
        rubric_version = "clearcut-ten-dimension-rubric-v1"
        tool_input: dict[str, Any] = {
            "evidence_fingerprint": evidence_fingerprint,
            "prompt_version": str(context.prompt_version),
            "policy_version": str(context.policy_version),
            "rubric_version": rubric_version,
            "admissible_count": len(admissible),
        }
        in_hash = compute_canonical_hash(tool_input)

        replay = await step_receipt_repo.find_replay_receipt(
            run_id=context.run_id,
            attempt_number=context.attempt_number,
            tool_name="evaluate_source_evidence",
            tool_input_hash=in_hash,
        )
        if replay and replay.output_payload:
            return replay.output_payload

        if not admissible:
            duration_ms = int((time.monotonic() - start) * 1000)
            output = {
                "status": "no_evidence",
                "claim_count": 0,
                "message": "No admissible search snapshots were found to evaluate.",
            }
            out_hash = compute_canonical_hash(output)
            step_idx = await step_receipt_repo.get_next_step_index(
                run_id=context.run_id,
                attempt_number=context.attempt_number,
            )
            await step_receipt_repo.record_step(
                org_id=context.org_id,
                project_id=context.project_id,
                run_id=context.run_id,
                item_id=context.item_id,
                job_id=context.job_id,
                attempt_number=context.attempt_number,
                step_index=step_idx,
                tool_name="evaluate_source_evidence",
                tool_input_hash=in_hash,
                tool_output_hash=out_hash,
                input_payload=tool_input,
                output_payload=output,
                status="succeeded",
                duration_ms=duration_ms,
            )
            if budget_tracker:
                budget_tracker.record_tool_call()
            return output

        # Synthesize claims if synthesizer provided
        claims: list[ResearchEvidence] = []
        if synthesizer:
            for item in admissible:
                if budget_tracker:
                    budget_tracker.check_budget()
                synth_result = await synthesizer.synthesize_claim(
                    ClaimSynthesisRequest(
                        item_id=context.item_id,
                        snapshot_id=item.snapshot_id,
                        category=context.category,
                        item_text=context.item_text,
                        url=item.url,
                        publisher=item.publisher,
                        excerpt=item.excerpt,
                        correlation_id=context.correlation_id,
                        research_run_id=context.run_id,
                    )
                )
                if budget_tracker:
                    in_tok = 0
                    out_tok = 0
                    tot_tok = 0
                    meta = getattr(synth_result, "metadata", None) or getattr(synth_result, "attempt", None)
                    if meta and getattr(meta, "usage", None):
                        u = meta.usage
                        in_tok = getattr(u, "input_tokens", 0) or 0
                        out_tok = getattr(u, "output_tokens", 0) or 0
                        tot_tok = getattr(u, "total_tokens", 0) or 0
                    budget_tracker.record_model_call(
                        input_tokens=in_tok,
                        output_tokens=out_tok,
                        total_tokens=tot_tok,
                    )
                if isinstance(synth_result, ClaimSynthesisSuccess):
                    stance_val = (
                        synth_result.stance.value
                        if hasattr(synth_result.stance, "value")
                        else str(synth_result.stance)
                    )
                    claims.append(
                        ResearchEvidence(
                            snapshot_id=item.snapshot_id,
                            url=item.url,
                            publisher=item.publisher,
                            excerpt=item.excerpt,
                            stance=stance_val,
                            authority_tier=item.authority_tier,
                            claim_text=synth_result.claim_text,
                        )
                    )
        else:
            claims = list(admissible)

        judge_passed = True
        headline_score = 1.0
        evaluation_id = None
        if evaluation and claims:
            from clearcut.evaluation.ports.judge import JudgeBindings

            if budget_tracker:
                budget_tracker.check_budget()

            bindings = JudgeBindings(
                rubric_version=rubric_version,
                prompt_version=str(context.prompt_version),
                policy_version=str(context.policy_version),
                input_sha256=evidence_fingerprint,
            )
            eval_record = await evaluation.evaluate_research_run(
                org_id=context.org_id,
                project_id=context.project_id,
                run_id=context.job_id or context.run_id,
                job_attempt_number=context.attempt_number,
                evidence=tuple(claims),
                gate_results=admission_gates,
                bindings=bindings,
            )
            judge_passed = eval_record.blockers_count == 0
            headline_score = (
                eval_record.headline_score if eval_record.headline_score is not None else 1.0
            )
            evaluation_id = str(eval_record.evaluation_id)

            if budget_tracker:
                budget_tracker.record_model_call(
                    input_tokens=0,
                    output_tokens=0,
                    total_tokens=0,
                )

        if claims and context.job_id:
            await repository.persist_context_claims(
                org_id=context.org_id,
                project_id=context.project_id,
                job_id=context.job_id,
                job_attempt_number=context.attempt_number,
                lease_owner=context.lease_owner,
                run_id=context.run_id,
                item_id=context.item_id,
                evidence=tuple(claims),
            )

        duration_ms = int((time.monotonic() - start) * 1000)
        output = {
            "status": "evaluated",
            "claim_count": len(claims),
            "judge_passed": judge_passed,
            "headline_score": headline_score,
            "evaluation_id": evaluation_id,
        }
        out_hash = compute_canonical_hash(output)
        step_idx = await step_receipt_repo.get_next_step_index(
            run_id=context.run_id,
            attempt_number=context.attempt_number,
        )
        await step_receipt_repo.record_step(
            org_id=context.org_id,
            project_id=context.project_id,
            run_id=context.run_id,
            item_id=context.item_id,
            job_id=context.job_id,
            attempt_number=context.attempt_number,
            step_index=step_idx,
            tool_name="evaluate_source_evidence",
            tool_input_hash=in_hash,
            tool_output_hash=out_hash,
            input_payload=tool_input,
            output_payload=output,
            status="succeeded",
            duration_ms=duration_ms,
        )
        if budget_tracker:
            budget_tracker.record_tool_call()
        return output

    # 6. read_research_progress
    @tool
    async def read_research_progress() -> dict[str, Any]:
        """Read current execution step receipts, budget usage, and snapshot counts."""
        ReadResearchProgressArgs()
        tool_input: dict[str, Any] = {}
        in_hash = compute_canonical_hash(tool_input)
        replay = await step_receipt_repo.find_replay_receipt(
            run_id=context.run_id,
            attempt_number=context.attempt_number,
            tool_name="read_research_progress",
            tool_input_hash=in_hash,
        )
        if replay and replay.output_payload:
            return replay.output_payload

        start = time.monotonic()
        tool_counts = await step_receipt_repo.count_steps_by_tool(
            org_id=context.org_id,
            project_id=context.project_id,
            run_id=context.run_id,
            attempt_number=context.attempt_number,
        )
        receipts = await step_receipt_repo.list_receipts_for_run(
            org_id=context.org_id,
            project_id=context.project_id,
            run_id=context.run_id,
            attempt_number=context.attempt_number,
        )

        output = {
            "step_count": len(receipts),
            "tool_counts": tool_counts,
            "budget": budget_tracker.to_dict() if budget_tracker else None,
        }
        duration_ms = int((time.monotonic() - start) * 1000)
        out_hash = compute_canonical_hash(output)

        step_idx = await step_receipt_repo.get_next_step_index(
            run_id=context.run_id,
            attempt_number=context.attempt_number,
        )
        await step_receipt_repo.record_step(
            org_id=context.org_id,
            project_id=context.project_id,
            run_id=context.run_id,
            item_id=context.item_id,
            job_id=context.job_id,
            attempt_number=context.attempt_number,
            step_index=step_idx,
            tool_name="read_research_progress",
            tool_input_hash=in_hash,
            tool_output_hash=out_hash,
            input_payload=tool_input,
            output_payload=output,
            status="succeeded",
            duration_ms=duration_ms,
        )
        if budget_tracker:
            budget_tracker.record_tool_call()
        return output

    tools = [
        read_item_context,
        plan_queries,
        search_evidence,
        extract_admitted_source,
        evaluate_source_evidence,
        read_research_progress,
    ]

    for t in tools:
        if hasattr(t, "tool_spec") and isinstance(t.tool_spec, dict):
            input_schema = t.tool_spec.get("inputSchema", {}).get("json", {})
            if isinstance(input_schema, dict):
                input_schema["additionalProperties"] = False

    return tools


build_tenant_bound_tools = create_scoped_research_tools

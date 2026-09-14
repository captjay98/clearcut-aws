"""Bounded Strands agent research workflow with leaf-only permit acquisition.

Implements ResearchWorkflowPort using Strands Agents SDK.
Enforces:
1. Server-side tenant scoping: tools are built via closures with authenticated context.
2. Leaf-only permit discipline: Bedrock permit is held only during inference stream,
   strictly released before tool execution to eliminate nested deadlocks.
3. Thread-safe budget enforcement via JobBudgetTracker.
4. Immutable step receipt recording and idempotent replay.
5. Deterministic post-agent completion validation.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
import uuid6
from clearcut.ai.budgets import JobBudgetTracker
from clearcut.bootstrap.paid_providers import PaidProviderGate
from clearcut.database import session_scope
from clearcut.evaluation.application.evaluate import EvaluationService
from clearcut.research.adapters.sql_research_repository import SqlResearchRepository
from clearcut.research.application.agent_tools import create_scoped_research_tools
from clearcut.research.application.completion_validator import (
    CompletionValidationError,
    DeterministicCompletionValidator,
    ValidationOutcome,
)
from clearcut.research.ports.claim_synthesizer import ClaimSynthesizerPort
from clearcut.research.ports.planner import ResearchPlannerPort
from clearcut.research.ports.step_receipt_repository import (
    StepReceiptRepositoryPort,
)
from clearcut.research.ports.url_extract import UrlExtractPort
from clearcut.research.ports.web_search import WebSearchPort
from clearcut.research.ports.workflow import (
    ResearchWorkflowContext,
    ResearchWorkflowPort,
    ResearchWorkflowResult,
)
from strands import Agent
from strands.models import Model
from strands.types.streaming import StreamEvent


class LeafPermitModelWrapper(Model):
    """Wraps any Strands Model with leaf-only PaidProviderGate permit acquisition."""

    def __init__(
        self,
        underlying: Model,
        gate: PaidProviderGate | None = None,
        budget_tracker: JobBudgetTracker | None = None,
        provider_name: str = "bedrock",
    ) -> None:
        self._underlying = underlying
        self._gate = gate
        self._budget_tracker = budget_tracker
        self._provider_name = provider_name

    def update_config(self, **model_config: Any) -> None:
        self._underlying.update_config(**model_config)

    def get_config(self) -> Any:
        return self._underlying.get_config()

    def structured_output(self, *args: Any, **kwargs: Any) -> Any:
        return self._underlying.structured_output(*args, **kwargs)

    async def stream(
        self,
        messages: Any,
        tool_specs: list[Any] | None = None,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[StreamEvent, None]:
        if self._budget_tracker:
            self._budget_tracker.record_model_call()

        if self._gate:
            async with self._gate.acquire(self._provider_name):
                async for event in self._underlying.stream(
                    messages, tool_specs, system_prompt, **kwargs
                ):
                    if self._budget_tracker and "metadata" in event:
                        usage = event["metadata"].get("usage")
                        if usage:
                            in_tokens = usage.get("inputTokens") or 0
                            out_tokens = usage.get("outputTokens") or 0
                            if in_tokens or out_tokens:
                                self._budget_tracker.record_tokens(
                                    input_tokens=in_tokens,
                                    output_tokens=out_tokens,
                                )
                    yield event
        else:
            async for event in self._underlying.stream(
                messages, tool_specs, system_prompt, **kwargs
            ):
                if self._budget_tracker and "metadata" in event:
                    usage = event["metadata"].get("usage")
                    if usage:
                        in_tokens = usage.get("inputTokens") or 0
                        out_tokens = usage.get("outputTokens") or 0
                        if in_tokens or out_tokens:
                            self._budget_tracker.record_tokens(
                                input_tokens=in_tokens,
                                output_tokens=out_tokens,
                            )
                yield event


class ScriptedMockStrandsModel(Model):
    """Deterministic, hermetic model double for unit and adversarial testing without AWS."""

    def __init__(self, steps: list[dict[str, Any]]) -> None:
        self.steps = steps
        self.step_index = 0
        self.invocations: list[Any] = []

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
    ) -> AsyncGenerator[StreamEvent, None]:
        self.invocations.append(messages)
        if self.step_index < len(self.steps):
            step = self.steps[self.step_index]
            self.step_index += 1

            if step.get("type") == "tool":
                call_id = f"call_{self.step_index}_{uuid6.uuid7().hex[:6]}"
                yield {"messageStart": {"role": "assistant"}}
                yield {
                    "contentBlockStart": {
                        "start": {
                            "toolUse": {
                                "toolUseId": call_id,
                                "name": step["name"],
                            }
                        },
                        "contentBlockIndex": 0,
                    }
                }
                yield {
                    "contentBlockDelta": {
                        "delta": {"toolUse": {"input": json.dumps(step.get("input", {}))}},
                        "contentBlockIndex": 0,
                    }
                }
                yield {"contentBlockStop": {"contentBlockIndex": 0}}
                yield {"messageStop": {"stopReason": "tool_use"}}
                yield {
                    "metadata": {
                        "usage": {"inputTokens": 10, "outputTokens": 10, "totalTokens": 20}
                    }
                }
            else:
                text = step.get("text", "Research complete.")
                yield {"messageStart": {"role": "assistant"}}
                yield {"contentBlockStart": {"start": {}, "contentBlockIndex": 0}}
                yield {"contentBlockDelta": {"delta": {"text": text}, "contentBlockIndex": 0}}
                yield {"contentBlockStop": {"contentBlockIndex": 0}}
                yield {"messageStop": {"stopReason": "end_turn"}}
                yield {
                    "metadata": {
                        "usage": {"inputTokens": 15, "outputTokens": 15, "totalTokens": 30}
                    }
                }
        else:
            yield {"messageStart": {"role": "assistant"}}
            yield {"contentBlockStart": {"start": {}, "contentBlockIndex": 0}}
            yield {
                "contentBlockDelta": {
                    "delta": {"text": "All planned steps completed."},
                    "contentBlockIndex": 0,
                }
            }
            yield {"contentBlockStop": {"contentBlockIndex": 0}}
            yield {"messageStop": {"stopReason": "end_turn"}}
            yield {"metadata": {"usage": {"inputTokens": 5, "outputTokens": 5, "totalTokens": 10}}}


class _SessionAlignedExtract(UrlExtractPort):
    """Wraps extract port to align session_id with authorizing search attempt when available."""

    def __init__(self, underlying: UrlExtractPort, loop: asyncio.AbstractEventLoop) -> None:
        self._underlying = underlying
        self._loop = loop

    def extract(self, request: Any) -> Any:
        res = self._underlying.extract(request)
        if getattr(request, "search_attempt_id", None) is not None:
            async def _get_search_session() -> str | None:
                async with session_scope() as session:
                    row = (
                        await session.execute(
                            sa.text(
                                "SELECT provider_session_id FROM provider_attempts "
                                "WHERE id = :id AND operation_kind = 'search'"
                            ),
                            {"id": str(request.search_attempt_id)},
                        )
                    ).scalar_one_or_none()
                    return str(row) if row is not None else None

            try:
                fut = asyncio.run_coroutine_threadsafe(_get_search_session(), self._loop)
                expected_session = fut.result(timeout=5)
                if expected_session and res.session_id != expected_session:
                    from clearcut.research.domain.extraction import ExtractBatchResponse

                    return ExtractBatchResponse(
                        extract_id=res.extract_id,
                        session_id=expected_session,
                        results=res.results,
                        errors=res.errors,
                        warnings=res.warnings,
                    )
            except Exception:
                pass
        return res


class StrandsResearchWorkflow(ResearchWorkflowPort):
    """Orchestrates clearance research using bounded Strands Agents SDK."""

    def __init__(
        self,
        *,
        repository: SqlResearchRepository,
        step_receipt_repo: StepReceiptRepositoryPort,
        search: WebSearchPort,
        extract: UrlExtractPort,
        gate: PaidProviderGate | None = None,
        planner: ResearchPlannerPort | None = None,
        synthesizer: ClaimSynthesizerPort | None = None,
        evaluation: EvaluationService | None = None,
        validator: DeterministicCompletionValidator | None = None,
        model: Model | None = None,
        budget_tracker: JobBudgetTracker | None = None,
        provider_name: str = "bedrock",
    ) -> None:
        self._repository = repository
        self._step_receipt_repo = step_receipt_repo
        self._search = search
        self._extract = extract
        self._gate = gate
        self._planner = planner
        self._synthesizer = synthesizer
        self._evaluation = evaluation
        self._validator = validator or DeterministicCompletionValidator()
        self._model = model
        self._budget_tracker = budget_tracker
        self._provider_name = provider_name

    async def execute_research(
        self,
        context: ResearchWorkflowContext,
    ) -> ResearchWorkflowResult:
        # 1. Build server-side scoped tools
        loop = asyncio.get_running_loop()
        aligned_extract = _SessionAlignedExtract(self._extract, loop)
        tools = create_scoped_research_tools(
            context=context,
            repository=self._repository,
            step_receipt_repo=self._step_receipt_repo,
            search=self._search,
            extract=aligned_extract,
            synthesizer=self._synthesizer,
            evaluation=self._evaluation,
            budget_tracker=self._budget_tracker,
        )

        # 2. Resolve model with leaf-only permit acquisition wrapper
        if isinstance(self._model, LeafPermitModelWrapper):
            wrapped_model = self._model
        elif self._model is not None:
            wrapped_model = LeafPermitModelWrapper(
                underlying=self._model,
                gate=self._gate,
                budget_tracker=self._budget_tracker,
                provider_name=self._provider_name,
            )
        elif self._provider_name == "gemini":
            from strands.models.gemini import GeminiModel

            adc_path = os.path.expanduser("~/.config/gcloud/application_default_credentials.json")
            if "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ and os.path.exists(adc_path):
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = adc_path

            raw_model = GeminiModel(
                client_args={
                    "vertexai": True,
                    "project": (
                        os.getenv("GOOGLE_CLOUD_PROJECT")
                        or os.getenv("CLEARCUT_GCP_PROJECT")
                        or os.getenv("GCP_PROJECT_ID", "clearcut-workspace")
                    ),
                    "location": os.getenv("CLEARCUT_VERTEX_LOCATION") or os.getenv("VERTEX_LOCATION", "global"),
                },
                model_id=os.getenv("CLEARCUT_GEMINI_RESEARCH_MODEL", "gemini-3.5-flash-lite"),
                params={
                    "max_output_tokens": 1024,
                    "temperature": 0,
                },
            )
            wrapped_model = LeafPermitModelWrapper(
                underlying=raw_model,
                gate=self._gate,
                budget_tracker=self._budget_tracker,
                provider_name="gemini",
            )
        else:
            from strands.models.bedrock import BedrockModel

            raw_model = BedrockModel()
            wrapped_model = LeafPermitModelWrapper(
                underlying=raw_model,
                gate=self._gate,
                budget_tracker=self._budget_tracker,
                provider_name="bedrock",
            )

        # 3. Create Strands Agent
        system_prompt = (
            f"You are the ClearCut Research Agent investigating a screenplay element.\n"
            f"Category: {context.category}\n"
            f"Passage: {context.item_text}\n"
            f"Guidelines:\n"
            f"1. Read item context first.\n"
            f"2. Plan 1-3 search queries and execute search_evidence.\n"
            f"3. Optionally extract admitted sources if deeper content is needed.\n"
            f"4. Synthesize and evaluate evidence claims.\n"
            f"5. You cannot self-certify legal clearance."
        )

        agent = Agent(
            model=wrapped_model,
            tools=tools,
            system_prompt=system_prompt,
        )

        prompt = (
            f"Please conduct clearance research for item {context.item_id} "
            f"in category '{context.category}':\n\n{context.item_text}"
        )

        # Ensure research_runs is marked running if it was prepared in planning state
        async with session_scope() as session:
            await session.execute(
                sa.text(
                    "UPDATE research_runs SET status = 'running' "
                    "WHERE id = :run_id AND status = 'planning' "
                    "AND org_id = :org_id AND project_id = :project_id"
                ),
                {
                    "run_id": str(context.run_id),
                    "org_id": str(context.org_id),
                    "project_id": str(context.project_id),
                },
            )

        # 4. Invoke the Strands agent loop
        workflow_error: str | None = None
        try:
            agent_result = await agent.invoke_async(prompt)
            agent_text = (
                agent_result.message.get("content", [{}])[0].get("text", "")
                if agent_result and agent_result.message
                else ""
            )
        except Exception as err:
            agent_text = f"Agent failed with exception: {err}"
            workflow_error = str(err)

        # 5. Fetch step receipts and database state
        receipts = await self._step_receipt_repo.list_receipts_for_run(
            org_id=context.org_id,
            project_id=context.project_id,
            run_id=context.run_id,
            attempt_number=context.attempt_number,
        )

        async with session_scope() as session:
            # Query counts
            q_res = await session.execute(
                sa.text("SELECT COUNT(*) FROM research_queries WHERE run_id = :run_id"),
                {"run_id": str(context.run_id)},
            )
            query_count = int(q_res.scalar_one())

            s_res = await session.execute(
                sa.text(
                    """
                    SELECT COUNT(*) FROM provider_attempts
                    WHERE run_id = :run_id AND operation_kind = 'search'
                    """
                ),
                {"run_id": str(context.run_id)},
            )
            search_attempt_count = int(s_res.scalar_one())

            e_res = await session.execute(
                sa.text(
                    """
                    SELECT COUNT(*) FROM provider_attempts
                    WHERE run_id = :run_id AND operation_kind = 'extract'
                    """
                ),
                {"run_id": str(context.run_id)},
            )
            extract_attempt_count = int(e_res.scalar_one())

            snap_res = await session.execute(
                sa.text("SELECT COUNT(*) FROM source_snapshots WHERE run_id = :run_id"),
                {"run_id": str(context.run_id)},
            )
            snapshot_count = int(snap_res.scalar_one())

            claim_res = await session.execute(
                sa.text(
                    """
                    SELECT id, snapshot_id, stance, authority_tier, claim_text
                    FROM evidence_claims
                    WHERE org_id = :org_id AND project_id = :project_id
                      AND item_id = :item_id
                      AND (run_id = :run_id OR run_id IS NULL)
                    """
                ),
                {
                    "org_id": str(context.org_id),
                    "project_id": str(context.project_id),
                    "item_id": str(context.item_id),
                    "run_id": str(context.run_id),
                },
            )
            persisted_claims = [
                {
                    "id": UUID(str(row[0])),
                    "snapshot_id": UUID(str(row[1])),
                    "stance": row[2],
                    "authority_tier": row[3],
                    "claim_text": row[4],
                }
                for row in claim_res.all()
            ]
            claim_count = len(persisted_claims)

        raw_summary: dict[str, Any] = {
            "agent_text": agent_text,
            "snapshot_count": snapshot_count,
            "claim_count": claim_count,
        }
        if agent_text:
            cleaned = agent_text.strip()
            if "```json" in cleaned:
                try:
                    start_pos = cleaned.find("```json") + 7
                    end_pos = cleaned.find("```", start_pos)
                    parsed_summary = json.loads(cleaned[start_pos:end_pos].strip())
                    if isinstance(parsed_summary, dict):
                        for k, v in parsed_summary.items():
                            if k not in raw_summary:
                                raw_summary[k] = v
                except Exception:
                    pass
            elif cleaned.startswith("{") and cleaned.endswith("}"):
                try:
                    parsed_summary = json.loads(cleaned)
                    if isinstance(parsed_summary, dict):
                        for k, v in parsed_summary.items():
                            if k not in raw_summary:
                                raw_summary[k] = v
                except Exception:
                    pass
        if workflow_error is not None:
            raw_summary["error"] = workflow_error
            raw_summary["refused"] = True

        # 6. Run Deterministic Completion Validator
        try:
            validation = await self._validator.validate(
                org_id=context.org_id,
                project_id=context.project_id,
                run_id=context.run_id,
                item_id=context.item_id,
                step_receipts=receipts,
                claims=persisted_claims,
                raw_summary=raw_summary,
                raise_exc=False,
            )
        except CompletionValidationError as err:
            validation = ValidationOutcome(
                valid=False,
                review_status="unresolved",
                reason=err.code,
                needs_human_review=True,
                cleared=False,
                error=err.code,
                sanitized_summary={
                    "cleared": False,
                    "needs_human_review": True,
                    "error": str(err),
                },
            )

        # 7. Update run status in repository conditionally based on validation outcome
        if validation.valid:
            if context.job_id is not None:
                await self._repository.complete_run(
                    org_id=context.org_id,
                    project_id=context.project_id,
                    job_id=context.job_id,
                    job_attempt_number=context.attempt_number,
                    lease_owner=context.lease_owner,
                    run_id=context.run_id,
                    item_id=context.item_id,
                )
            else:
                async with session_scope() as session:
                    await session.execute(
                        sa.text(
                            "UPDATE research_runs SET status = 'succeeded', "
                            "completed_at = :completed_at WHERE id = :run_id "
                            "AND org_id = :org_id AND project_id = :project_id "
                            "AND item_id = :item_id AND status = 'running'"
                        ),
                        {
                            "completed_at": datetime.now(UTC),
                            "run_id": str(context.run_id),
                            "org_id": str(context.org_id),
                            "project_id": str(context.project_id),
                            "item_id": str(context.item_id),
                        },
                    )
                    await session.execute(
                        sa.text(
                            "UPDATE clearance_items SET research_status = 'completed' "
                            "WHERE id = :item_id AND org_id = :org_id "
                            "AND project_id = :project_id"
                        ),
                        {
                            "item_id": str(context.item_id),
                            "org_id": str(context.org_id),
                            "project_id": str(context.project_id),
                        },
                    )
        else:
            error_msg = validation.error or "Deterministic completion validation failed"
            if context.job_id is not None:
                await self._repository.fail_run(
                    org_id=context.org_id,
                    project_id=context.project_id,
                    job_id=context.job_id,
                    job_attempt_number=context.attempt_number,
                    lease_owner=context.lease_owner or "",
                    run_id=context.run_id,
                    item_id=context.item_id,
                    code="validation_failed",
                    message=error_msg,
                    retryable=False,
                )
            else:
                async with session_scope() as session:
                    await session.execute(
                        sa.text(
                            "UPDATE research_runs SET status = 'failed', "
                            "safe_error = :error, "
                            "completed_at = :completed_at WHERE id = :run_id "
                            "AND org_id = :org_id AND project_id = :project_id "
                            "AND item_id = :item_id"
                        ).bindparams(sa.bindparam("error", type_=sa.JSON())),
                        {
                            "error": {
                                "code": "validation_failed",
                                "message": error_msg,
                                "retryable": False,
                            },
                            "completed_at": datetime.now(UTC),
                            "run_id": str(context.run_id),
                            "org_id": str(context.org_id),
                            "project_id": str(context.project_id),
                            "item_id": str(context.item_id),
                        },
                    )
                    await session.execute(
                        sa.text(
                            "UPDATE clearance_items SET research_status = 'failed' "
                            "WHERE id = :item_id AND org_id = :org_id "
                            "AND project_id = :project_id"
                        ),
                        {
                            "item_id": str(context.item_id),
                            "org_id": str(context.org_id),
                            "project_id": str(context.project_id),
                        },
                    )

        summary = {
            "clearanceItemId": str(context.item_id),
            "scriptVersionId": str(context.version_id),
            "queryCount": query_count,
            "searchAttemptCount": search_attempt_count,
            "extractAttemptCount": extract_attempt_count,
            "snapshotCount": snapshot_count,
            "claimCount": claim_count,
            "stepCount": len(receipts),
            "reviewStatus": validation.review_status,
            "reason": validation.reason,
            "needsHumanReview": validation.needs_human_review,
            "cleared": validation.cleared,
        }
        if validation.error:
            summary["error"] = validation.error

        return ResearchWorkflowResult(
            run_id=context.run_id,
            item_id=context.item_id,
            status="succeeded" if validation.valid else "failed",
            query_count=query_count,
            search_attempt_count=search_attempt_count,
            extract_attempt_count=extract_attempt_count,
            snapshot_count=snapshot_count,
            claim_count=claim_count,
            review_status=validation.review_status,
            reason=validation.reason,
            needs_human_review=validation.needs_human_review,
            cleared=validation.cleared,
            error=validation.error,
            step_count=len(receipts),
            summary=summary,
        )

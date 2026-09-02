"""Execute one scoped research job through persisted provider boundaries."""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any
from uuid import UUID

from clearcut.evaluation.application.evaluate import (
    EvaluationExecutionError,
    EvaluationService,
)
from clearcut.evaluation.domain.gates import GateResult
from clearcut.evaluation.domain.rubric import DimensionStatus
from clearcut.evaluation.ports.judge import JudgeBindings, ResearchEvidence
from clearcut.evaluation.ports.repository import EvaluationPersistenceError
from clearcut.operations.application.run_job import JobExecutionError, JobExecutionResult
from clearcut.operations.domain.jobs import RunStatus
from clearcut.operations.ports.job_repository import JobRecord, SafeJobError
from clearcut.research.adapters.sql_research_repository import (
    ResearchAttemptState,
    ResearchPersistenceError,
    ResearchQueryRecord,
    SqlResearchRepository,
)
from clearcut.research.application.select_extract_targets import select_extract_targets
from clearcut.research.domain.extraction import ExtractRequest
from clearcut.research.domain.queries import SearchRequest
from clearcut.research.domain.snapshots import ProviderFailure
from clearcut.research.ports.planner import (
    ResearchPlannerPort,
    ResearchPlanningFailure,
    ResearchPlanningRequest,
)
from clearcut.research.ports.url_extract import UrlExtractPort
from clearcut.research.ports.web_search import WebSearchPort


class RunResearchJobService:
    def __init__(
        self,
        *,
        repository: SqlResearchRepository,
        planner: ResearchPlannerPort,
        search: WebSearchPort,
        extract: UrlExtractPort,
        evaluation: EvaluationService,
    ) -> None:
        self._repository = repository
        self._planner = planner
        self._search = search
        self._extract = extract
        self._evaluation = evaluation

    async def __call__(self, job: JobRecord) -> JobExecutionResult:
        item_id = self._item_id(job)
        lease_owner = job.lease_owner
        if lease_owner is None:
            raise self._job_error(
                "invalid_research_job",
                "The research job has no active lease owner.",
                False,
            )
        try:
            research_input = await self._repository.load_input(
                org_id=job.org_id,
                project_id=job.project_id,
                item_id=item_id,
            )
            policy_version, prompt_version = (
                await self._repository.load_active_judge_configuration(
                    org_id=job.org_id,
                )
            )
            prepared = await self._repository.prepare_planning(
                org_id=job.org_id,
                project_id=job.project_id,
                job_id=job.job_id,
                job_attempt_number=job.attempt_count,
                lease_owner=lease_owner,
                correlation_id=job.correlation_id,
                research_input=research_input,
                requested_model=self._planner.requested_model,
                input_sha256=self._planning_input_hash(research_input),
            )

            if prepared.state is ResearchAttemptState.READY:
                planning_result = await self._planner.plan_research(
                    ResearchPlanningRequest(
                        item_id=item_id,
                        version_id=research_input.version_id,
                        category=research_input.category,
                        text=research_input.text,
                        correlation_id=job.correlation_id,
                        research_run_id=prepared.run_id,
                    )
                )
                if isinstance(planning_result, ResearchPlanningFailure):
                    await self._repository.persist_planning_failure(
                        org_id=job.org_id,
                        project_id=job.project_id,
                        job_id=job.job_id,
                        job_attempt_number=job.attempt_count,
                        lease_owner=lease_owner,
                        run_id=prepared.run_id,
                        attempt_id=prepared.attempt_id,
                        result=planning_result,
                    )
                    await self._repository.fail_run(
                        org_id=job.org_id,
                        project_id=job.project_id,
                        job_id=job.job_id,
                        job_attempt_number=job.attempt_count,
                        lease_owner=lease_owner,
                        run_id=prepared.run_id,
                        item_id=item_id,
                        code=planning_result.error.code,
                        message=planning_result.error.message,
                        retryable=planning_result.error.retryable,
                    )
                    raise self._job_error(
                        "research_planning_failed",
                        planning_result.error.message,
                        planning_result.error.retryable,
                    )
                queries = await self._repository.persist_planning_success(
                    org_id=job.org_id,
                    project_id=job.project_id,
                    job_id=job.job_id,
                    job_attempt_number=job.attempt_count,
                    lease_owner=lease_owner,
                    run_id=prepared.run_id,
                    attempt_id=prepared.attempt_id,
                    result=planning_result,
                )
                plan = planning_result.plan
            elif prepared.state is ResearchAttemptState.SUCCEEDED:
                if prepared.result is None:
                    raise ResearchPersistenceError(
                        "A succeeded planning attempt has no persisted plan."
                    )
                plan = prepared.result.plan
                queries = await self._repository.load_queries(
                    org_id=job.org_id,
                    project_id=job.project_id,
                    run_id=prepared.run_id,
                )
            elif prepared.state is ResearchAttemptState.FAILED:
                if prepared.error is None:
                    raise ResearchPersistenceError(
                        "A failed planning attempt has no persisted safe error."
                    )
                raise self._job_error(
                    "research_planning_failed",
                    prepared.error.message,
                    prepared.error.retryable,
                )
            else:
                raise self._job_error(
                    "research_planning_pending",
                    "This job attempt already has a pending research plan.",
                    False,
                )

            return await self._execute_queries(
                job=job,
                lease_owner=lease_owner,
                item_id=item_id,
                version_id=research_input.version_id,
                run_id=prepared.run_id,
                objective=plan.objective,
                queries=queries,
                policy_version=policy_version,
                prompt_version=prompt_version,
            )
        except JobExecutionError:
            raise
        except (ResearchPersistenceError, EvaluationPersistenceError) as error:
            raise self._job_error(
                "research_persistence_failed",
                "Research output could not be persisted safely.",
                False,
            ) from error

    async def _execute_queries(
        self,
        *,
        job: JobRecord,
        lease_owner: str,
        item_id: UUID,
        version_id: UUID,
        run_id: UUID,
        objective: str,
        queries: tuple[ResearchQueryRecord, ...],
        policy_version: str,
        prompt_version: str,
    ) -> JobExecutionResult:
        search_attempt_count = 0
        extract_attempt_count = 0
        snapshot_count = 0
        for query in queries:
            search_attempt = await self._repository.prepare_search(
                org_id=job.org_id,
                project_id=job.project_id,
                job_id=job.job_id,
                job_attempt_number=job.attempt_count,
                lease_owner=lease_owner,
                correlation_id=job.correlation_id,
                run_id=run_id,
                item_id=item_id,
                query=query,
            )
            search_attempt_count += 1
            search_result = await asyncio.to_thread(
                self._search.search,
                SearchRequest(
                    query=query.query,
                    objective=objective,
                    correlation_id=job.correlation_id,
                    research_run_id=run_id,
                    research_query_id=query.query_id,
                ),
            )
            if isinstance(search_result, ProviderFailure):
                await self._repository.persist_provider_failure(
                    org_id=job.org_id,
                    project_id=job.project_id,
                    job_id=job.job_id,
                    job_attempt_number=job.attempt_count,
                    lease_owner=lease_owner,
                    run_id=run_id,
                    attempt_id=search_attempt.attempt_id,
                    operation_kind="search",
                    result=search_result,
                )
                await self._repository.fail_run(
                    org_id=job.org_id,
                    project_id=job.project_id,
                    job_id=job.job_id,
                    job_attempt_number=job.attempt_count,
                    lease_owner=lease_owner,
                    run_id=run_id,
                    item_id=item_id,
                    code=search_result.kind,
                    message=search_result.message,
                    retryable=search_result.kind in {"retryable", "rate_limited"},
                )
                raise self._job_error(
                    "research_search_failed",
                    search_result.message,
                    search_result.kind in {"retryable", "rate_limited"},
                )

            persisted = await self._repository.persist_search_success(
                org_id=job.org_id,
                project_id=job.project_id,
                job_id=job.job_id,
                job_attempt_number=job.attempt_count,
                lease_owner=lease_owner,
                run_id=run_id,
                item_id=item_id,
                query_id=query.query_id,
                attempt_id=search_attempt.attempt_id,
                result=search_result,
            )
            snapshot_count += persisted.snapshot_count
            targets = select_extract_targets(search_result.results)
            if not targets:
                continue

            extract_attempt = await self._repository.prepare_extract(
                org_id=job.org_id,
                project_id=job.project_id,
                job_id=job.job_id,
                job_attempt_number=job.attempt_count,
                lease_owner=lease_owner,
                correlation_id=job.correlation_id,
                run_id=run_id,
                item_id=item_id,
                query_id=query.query_id,
                search_attempt_id=search_attempt.attempt_id,
                urls=targets,
            )
            extract_attempt_count += 1
            extract_result = await asyncio.to_thread(
                self._extract.extract,
                ExtractRequest(
                    urls=targets,
                    objective=objective,
                    session_id=search_result.session_id,
                    correlation_id=job.correlation_id,
                    research_run_id=run_id,
                    research_query_id=query.query_id,
                    search_attempt_id=search_attempt.attempt_id,
                ),
            )
            if isinstance(extract_result, ProviderFailure):
                await self._repository.persist_provider_failure(
                    org_id=job.org_id,
                    project_id=job.project_id,
                    job_id=job.job_id,
                    job_attempt_number=job.attempt_count,
                    lease_owner=lease_owner,
                    run_id=run_id,
                    attempt_id=extract_attempt.attempt_id,
                    operation_kind="extract",
                    result=extract_result,
                )
                await self._repository.fail_run(
                    org_id=job.org_id,
                    project_id=job.project_id,
                    job_id=job.job_id,
                    job_attempt_number=job.attempt_count,
                    lease_owner=lease_owner,
                    run_id=run_id,
                    item_id=item_id,
                    code=extract_result.kind,
                    message=extract_result.message,
                    retryable=extract_result.kind in {"retryable", "rate_limited"},
                )
                raise self._job_error(
                    "research_extract_failed",
                    extract_result.message,
                    extract_result.kind in {"retryable", "rate_limited"},
                )
            snapshot_count += await self._repository.persist_extract_success(
                org_id=job.org_id,
                project_id=job.project_id,
                job_id=job.job_id,
                job_attempt_number=job.attempt_count,
                lease_owner=lease_owner,
                run_id=run_id,
                item_id=item_id,
                query_id=query.query_id,
                search_attempt_id=search_attempt.attempt_id,
                attempt_id=extract_attempt.attempt_id,
                result=extract_result,
            )

        claim_count = 0
        evaluation = None
        judge_passed = False
        if snapshot_count > 0:
            evidence, admission_gates = await self._repository.load_admissible_evidence(
                org_id=job.org_id,
                project_id=job.project_id,
                run_id=run_id,
                item_id=item_id,
            )
            if evidence:
                bindings = JudgeBindings(
                    rubric_version="clearcut-ten-dimension-rubric-v1",
                    prompt_version=prompt_version,
                    policy_version=policy_version,
                    input_sha256=self._research_judge_input_hash(
                        run_id,
                        evidence,
                        admission_gates,
                    ),
                )
                try:
                    evaluation = await self._evaluation.evaluate_research_run(
                        org_id=job.org_id,
                        project_id=job.project_id,
                        run_id=job.job_id,
                        job_attempt_number=job.attempt_count,
                        evidence=evidence,
                        gate_results=admission_gates,
                        bindings=bindings,
                    )
                except EvaluationExecutionError as error:
                    await self._repository.fail_run(
                        org_id=job.org_id,
                        project_id=job.project_id,
                        job_id=job.job_id,
                        job_attempt_number=job.attempt_count,
                        lease_owner=lease_owner,
                        run_id=run_id,
                        item_id=item_id,
                        code=error.error.code,
                        message=error.error.message,
                        retryable=error.error.retryable,
                    )
                    raise self._job_error(
                        error.error.code,
                        error.error.message,
                        error.error.retryable,
                    ) from error
                judge_passed = all(
                    verdict.status
                    not in {DimensionStatus.FAILED, DimensionStatus.INCOMPLETE}
                    for verdict in evaluation.verdicts
                )
                if not judge_passed:
                    message = (
                        "The bounded research quality judge rejected this evidence "
                        "for accountable human review."
                    )
                    await self._repository.fail_run(
                        org_id=job.org_id,
                        project_id=job.project_id,
                        job_id=job.job_id,
                        job_attempt_number=job.attempt_count,
                        lease_owner=lease_owner,
                        run_id=run_id,
                        item_id=item_id,
                        code="judge_rejected",
                        message=message,
                        retryable=False,
                    )
                    raise self._job_error("judge_rejected", message, False)
                claim_count = await self._repository.persist_context_claims(
                    org_id=job.org_id,
                    project_id=job.project_id,
                    job_id=job.job_id,
                    job_attempt_number=job.attempt_count,
                    lease_owner=lease_owner,
                    run_id=run_id,
                    item_id=item_id,
                    evidence=evidence,
                )

        await self._repository.complete_run(
            org_id=job.org_id,
            project_id=job.project_id,
            job_id=job.job_id,
            job_attempt_number=job.attempt_count,
            lease_owner=lease_owner,
            run_id=run_id,
            item_id=item_id,
        )
        summary: dict[str, Any] = {
            "clearanceItemId": str(item_id),
            "scriptVersionId": str(version_id),
            "queryCount": len(queries),
            "searchAttemptCount": search_attempt_count,
            "extractAttemptCount": extract_attempt_count,
            "snapshotCount": snapshot_count,
            "claimCount": claim_count,
            "reviewStatus": "unresolved",
            "reason": (
                "no_search_results"
                if snapshot_count == 0
                else "human_review_required"
            ),
        }
        if evaluation is not None:
            summary.update(
                {
                    "evaluationId": str(evaluation.evaluation_id),
                    "headlineScore": evaluation.headline_score,
                    "judgePassed": judge_passed,
                }
            )
        return JobExecutionResult(summary=summary)

    @staticmethod
    def _item_id(job: JobRecord) -> UUID:
        payload = job.payload
        target = payload.get("target")
        target_id = target.get("id") if isinstance(target, dict) else None
        valid = (
            job.job_type == "research"
            and job.status is RunStatus.RUNNING
            and job.attempt_count > 0
            and set(payload) == {"schemaVersion", "target"}
            and payload.get("schemaVersion") == 1
            and not isinstance(payload.get("schemaVersion"), bool)
            and isinstance(target, dict)
            and set(target) == {"type", "id"}
            and target.get("type") == "clearance_item"
            and isinstance(target_id, str)
        )
        if not valid:
            raise RunResearchJobService._job_error(
                "invalid_research_job",
                "The research job payload or active attempt is invalid.",
                False,
            )
        try:
            return UUID(target_id)
        except ValueError as error:
            raise RunResearchJobService._job_error(
                "invalid_research_job",
                "The research job target is invalid.",
                False,
            ) from error

    @staticmethod
    def _planning_input_hash(research_input: Any) -> str:
        return hashlib.sha256(
            json.dumps(
                {
                    "itemId": str(research_input.item_id),
                    "versionId": str(research_input.version_id),
                    "category": research_input.category,
                    "text": research_input.text,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

    @staticmethod
    def _research_judge_input_hash(
        run_id: UUID,
        evidence: tuple[ResearchEvidence, ...],
        gates: list[GateResult],
    ) -> str:
        return hashlib.sha256(
            json.dumps(
                {
                    "researchRunId": str(run_id),
                    "evidence": [
                        {
                            "snapshotId": str(item.snapshot_id),
                            "url": item.url,
                            "publisher": item.publisher,
                            "excerpt": item.excerpt,
                            "authorityTier": item.authority_tier,
                            "stance": item.stance,
                            "claimText": item.claim_text,
                        }
                        for item in evidence
                    ],
                    "gates": [
                        {
                            "snapshotId": str(gate.candidate_id),
                            "name": gate.gate_name,
                            "passed": gate.passed,
                            "severity": gate.severity.value,
                            "details": gate.details,
                        }
                        for gate in gates
                    ],
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

    @staticmethod
    def _job_error(code: str, message: str, retryable: bool) -> JobExecutionError:
        return JobExecutionError(
            SafeJobError(code=code, message=message, retryable=retryable)
        )

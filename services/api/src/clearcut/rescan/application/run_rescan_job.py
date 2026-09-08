"""Durable, checkpointed selective-rescan staged execution.

:class:`RunSelectiveRescanJobService` is a job processor for the ``selective_rescan``
job kind. It advances through the seven approved
:class:`~clearcut.rescan.application.models.RescanStage` values in exact order,
persisting a succeeded checkpoint for each stage *before* the next stage runs so a
reload through a fresh process replays only stages that have not yet succeeded.

Governance invariants:

* only modified/added elements reach child detection, and only the resulting
  affected items reach child research;
* evidence is carried forward only for exact/contextual unchanged or moved
  elements, referencing the original claim provenance — never synthesized, and
  zero results never become clearance;
* a typed provider/stage failure maps to a :class:`SafeJobError` and no later
  stage runs;
* child work is requested through stable idempotency keys, and completed stages
  are skipped on replay so a reload never duplicates jobs, items, evidence, or
  provider calls;
* strict payload projection rejects any non-``script_version`` target or
  unsupported schema before any stage runs.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from clearcut.operations.application.run_job import JobExecutionError, JobExecutionResult
from clearcut.operations.domain.jobs import RunStatus
from clearcut.operations.ports.job_repository import (
    JobRecord,
    JobRepositoryPort,
    SafeJobError,
)
from clearcut.rescan.application.models import (
    CarryableElement,
    RescanSafeError,
    RescanStage,
    RevisionPlan,
)
from clearcut.rescan.ports.repository import (
    RescanChildWorkPort,
    RescanEvidenceWorkPort,
    RescanItemLineageWorkPort,
    SelectiveRescanRepositoryPort,
)
from clearcut.rescan.ports.revision_plan import RevisionPlanPort

_SUPPORTED_SCHEMA_VERSION = 1
_EXPECTED_TARGET_TYPE = "script_version"

# Monotonic progress checkpoints per stage in workflow order. Terminal success
# forces progress to 100 in the job kernel, so the final stage stays below it.
_STAGE_SEQUENCE: tuple[tuple[RescanStage, float], ...] = (
    (RescanStage.MATERIALIZING_LINEAGE, 15.0),
    (RescanStage.CARRYING_EVIDENCE, 35.0),
    (RescanStage.DETECTING_AFFECTED_PASSAGES, 55.0),
    (RescanStage.RESEARCHING_AFFECTED_ITEMS, 75.0),
    (RescanStage.AWAITING_CONFIRMATION, 90.0),
    (RescanStage.COMPLETED, 99.0),
)


class RunSelectiveRescanJobService:
    """Executes a durable selective rescan as ordered, checkpointed stages."""

    def __init__(
        self,
        *,
        revision_plan: RevisionPlanPort,
        materialize_items: RescanItemLineageWorkPort,
        carry_evidence: RescanEvidenceWorkPort,
        child_work: RescanChildWorkPort,
        repository: SelectiveRescanRepositoryPort,
        job_repository: JobRepositoryPort,
    ) -> None:
        self._revision_plan = revision_plan
        self._materialize_items = materialize_items
        self._carry_evidence = carry_evidence
        self._child_work = child_work
        self._repository = repository
        self._job_repository = job_repository

    async def __call__(self, job: JobRecord) -> JobExecutionResult:
        after_version_id = self._require_valid_target(job)
        completed = await self._repository.completed_stages(
            org_id=job.org_id,
            project_id=job.project_id,
            job_id=job.job_id,
        )

        try:
            plan = await self._revision_plan.load_revision_plan(
                org_id=job.org_id,
                project_id=job.project_id,
                after_version_id=after_version_id,
            )
        except RescanSafeError as error:
            await self._record_failure(job, RescanStage.MATERIALIZING_LINEAGE, error)
            raise self._as_execution_error(error) from error

        summary: dict[str, Any] = {
            "afterVersionId": str(after_version_id),
            "carriedItemCount": 0,
            "carriedEvidenceEdgeCount": 0,
            "affectedItemCount": 0,
        }
        carried_mappings: tuple[Any, ...] = ()
        affected_item_ids: tuple[UUID, ...] = ()

        for stage, progress in _STAGE_SEQUENCE:
            if stage in completed:
                # A prior attempt already succeeded this stage: skip its writes,
                # provider calls, and child work so a replay never duplicates.
                continue
            try:
                stage_result, carried_mappings, affected_item_ids = await self._run_stage(
                    job,
                    stage,
                    plan=plan,
                    after_version_id=after_version_id,
                    carried_mappings=carried_mappings,
                    affected_item_ids=affected_item_ids,
                    summary=summary,
                )
            except RescanSafeError as error:
                await self._record_failure(job, stage, error)
                raise self._as_execution_error(error) from error

            await self._repository.record_stage_success(
                org_id=job.org_id,
                project_id=job.project_id,
                job_id=job.job_id,
                stage=stage,
                attempt_number=job.attempt_count,
                result=stage_result,
            )
            await self._advance_progress(job, stage=stage, progress=progress)

        return JobExecutionResult(summary=summary)

    async def _run_stage(
        self,
        job: JobRecord,
        stage: RescanStage,
        *,
        plan: RevisionPlan,
        after_version_id: UUID,
        carried_mappings: tuple[Any, ...],
        affected_item_ids: tuple[UUID, ...],
        summary: dict[str, Any],
    ) -> tuple[dict[str, Any], tuple[Any, ...], tuple[UUID, ...]]:
        if stage is RescanStage.MATERIALIZING_LINEAGE:
            elements = self._carryable_elements(plan)
            carried_mappings = await self._materialize_items.materialize(
                org_id=job.org_id,
                project_id=job.project_id,
                script_id=plan.script_id,
                before_version_id=plan.before_version_id,
                after_version_id=after_version_id,
                carryable_elements=elements,
            )
            summary["carriedItemCount"] = len(carried_mappings)
            return (
                {"carriedItemCount": len(carried_mappings)},
                carried_mappings,
                affected_item_ids,
            )

        if stage is RescanStage.CARRYING_EVIDENCE:
            edge_count = 0
            for mapping in carried_mappings:
                edges = await self._carry_evidence.carry_forward(
                    org_id=job.org_id,
                    project_id=job.project_id,
                    new_item_id=mapping.new_item_id,
                    source_item_id=mapping.predecessor_item_id,
                )
                edge_count += len(edges)
            summary["carriedEvidenceEdgeCount"] = edge_count
            return ({"carriedEvidenceEdgeCount": edge_count}, carried_mappings, affected_item_ids)

        if stage is RescanStage.DETECTING_AFFECTED_PASSAGES:
            affected_item_ids = await self._child_work.list_affected_items(
                org_id=job.org_id,
                project_id=job.project_id,
                before_version_id=plan.before_version_id,
                affected_element_ids=tuple(plan.affected_element_ids),
            )
            summary["affectedItemCount"] = len(affected_item_ids)
            if affected_item_ids:
                await self._child_work.request_detection(
                    org_id=job.org_id,
                    project_id=job.project_id,
                    after_version_id=after_version_id,
                    affected_item_ids=affected_item_ids,
                    actor_id=self._actor_id(job),
                )
            return (
                {"affectedItemCount": len(affected_item_ids)},
                carried_mappings,
                affected_item_ids,
            )

        if stage is RescanStage.RESEARCHING_AFFECTED_ITEMS:
            if affected_item_ids:
                await self._child_work.request_research(
                    org_id=job.org_id,
                    project_id=job.project_id,
                    after_version_id=after_version_id,
                    affected_item_ids=affected_item_ids,
                    actor_id=self._actor_id(job),
                )
            return (
                {"researchRequestedCount": len(affected_item_ids)},
                carried_mappings,
                affected_item_ids,
            )

        if stage is RescanStage.AWAITING_CONFIRMATION:
            # Carried items require accountable human confirmation before their
            # carried evidence is treated as current; no provider work happens.
            return ({"awaitingConfirmation": True}, carried_mappings, affected_item_ids)

        # RescanStage.COMPLETED
        return ({"completed": True}, carried_mappings, affected_item_ids)

    @staticmethod
    def _carryable_elements(plan: RevisionPlan) -> tuple[CarryableElement, ...]:
        # The scripts diff yields element-only pairs; the orchestration joins each
        # with its predecessor item to build a carryable element. ``before_element_id``
        # is the stable join key the item-lineage adapter resolves the predecessor,
        # category, and text from, so no fabricated evidence identity is introduced.
        return tuple(
            CarryableElement(
                before_element_id=pair.before_element_id,
                after_element_id=pair.after_element_id,
                predecessor_item_id=pair.before_element_id,
                category="",
                text=pair.after_text,
            )
            for pair in plan.carryable_elements
        )

    def _require_valid_target(self, job: JobRecord) -> UUID:
        payload = job.payload
        target = payload.get("target") if isinstance(payload, dict) else None
        if (
            job.status is not RunStatus.RUNNING
            or job.attempt_count <= 0
            or not isinstance(payload, dict)
            or payload.get("schemaVersion") != _SUPPORTED_SCHEMA_VERSION
            or not isinstance(target, dict)
            or target.get("type") != _EXPECTED_TARGET_TYPE
            or job.target.type != _EXPECTED_TARGET_TYPE
        ):
            raise JobExecutionError(
                SafeJobError(
                    code="invalid_selective_rescan_job",
                    message="Selective rescan job payload is not a valid script-version target.",
                    retryable=False,
                )
            )
        return job.target.id

    async def _advance_progress(
        self, job: JobRecord, *, stage: RescanStage, progress: float
    ) -> None:
        if job.lease_owner is None:
            return
        await self._job_repository.update_progress(
            org_id=job.org_id,
            project_id=job.project_id,
            job_id=job.job_id,
            attempt_number=job.attempt_count,
            lease_owner=job.lease_owner,
            progress=progress,
            stage=stage.value,
        )

    async def _record_failure(
        self, job: JobRecord, stage: RescanStage, error: RescanSafeError
    ) -> None:
        await self._repository.record_stage_failure(
            org_id=job.org_id,
            project_id=job.project_id,
            job_id=job.job_id,
            stage=stage,
            attempt_number=job.attempt_count,
            error_code=error.code,
            error_message=error.message,
            retryable=error.retryable,
        )

    @staticmethod
    def _as_execution_error(error: RescanSafeError) -> JobExecutionError:
        return JobExecutionError(
            SafeJobError(code=error.code, message=error.message, retryable=error.retryable)
        )

    @staticmethod
    def _actor_id(job: JobRecord) -> UUID:
        if job.actor_id is None:
            raise JobExecutionError(
                SafeJobError(
                    code="invalid_selective_rescan_job",
                    message="Selective rescan job has no accountable actor.",
                    retryable=False,
                )
            )
        return job.actor_id


__all__ = ["RunSelectiveRescanJobService"]

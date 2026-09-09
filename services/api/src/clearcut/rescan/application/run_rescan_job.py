"""Durable, checkpointed selective-rescan staged execution.

:class:`RunSelectiveRescanJobService` is a job processor for the ``selective_rescan``
job kind. It advances through the six processed
:class:`~clearcut.rescan.application.models.RescanStage` values (the ordered
stages after the initial persisted ``QUEUED`` state) in exact order,
persisting a succeeded checkpoint for each stage *before* the next stage runs so a
reload through a fresh process replays only stages that have not yet succeeded.

Governance invariants:

* only modified/added elements reach child detection, and only the resulting
  affected items reach child research; added passages are freshly detected on the
  after version into brand-new unresolved items (no predecessor, no carried
  evidence, no copied decision) and then reach research like any newly detected
  item;
* evidence is carried forward only for exact/contextual unchanged or moved
  elements, referencing the original claim provenance — never synthesized, and
  zero results never become clearance;
* a typed provider/stage failure maps to a :class:`SafeJobError` and no later
  stage runs;
* child work is requested through stable idempotency keys, and completed stages
  are skipped on replay so a reload never duplicates jobs, items, evidence, or
  provider calls;
* a skipped stage's OUTPUT is restored from its persisted checkpoint before the
  next stage runs, so a resumed run never carries zero evidence or researches
  zero items while reporting success; a completed stage whose output cannot be
  restored fails the job closed instead;
* the final summary reports the restored totals, so a resumed run reports the
  work earlier attempts actually completed rather than zeros;
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
    ADDED_ITEM_IDS_KEY,
    AFFECTED_ITEM_IDS_KEY,
    CARRIED_EVIDENCE_EDGE_COUNT_KEY,
    CARRIED_MAPPINGS_KEY,
    CarriedItemMapping,
    CarryableElement,
    RescanSafeError,
    RescanStage,
    RestoredRescanProgress,
    RevisionPlan,
    encode_carried_mappings,
    encode_item_ids,
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
_STAGE_ORDER: tuple[RescanStage, ...] = tuple(stage for stage, _progress in _STAGE_SEQUENCE)


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
        # A resumed run skips the SIDE EFFECTS of an already-succeeded stage, but
        # it must still receive that stage's OUTPUTS: the carried mappings feed
        # evidence carry-forward and the affected item ids feed research. They are
        # restored from the persisted checkpoints before any stage runs.
        restored = await self._repository.load_restored_progress(
            org_id=job.org_id,
            project_id=job.project_id,
            job_id=job.job_id,
        )
        self._require_restorable(restored)
        completed = restored.completed_stages

        try:
            plan = await self._revision_plan.load_revision_plan(
                org_id=job.org_id,
                project_id=job.project_id,
                after_version_id=after_version_id,
            )
        except RescanSafeError as error:
            await self._record_failure(job, RescanStage.MATERIALIZING_LINEAGE, error)
            raise self._as_execution_error(error) from error

        # The summary starts from the restored totals, so a resumed run reports the
        # work a previous attempt actually completed instead of zeros.
        summary: dict[str, Any] = {
            "afterVersionId": str(after_version_id),
            "carriedItemCount": len(restored.carried_mappings),
            "carriedEvidenceEdgeCount": restored.carried_evidence_edge_count,
            "affectedItemCount": len(restored.affected_item_ids),
            "addedItemCount": len(restored.added_item_ids),
        }
        carried_mappings: tuple[CarriedItemMapping, ...] = restored.carried_mappings
        affected_item_ids: tuple[UUID, ...] = restored.affected_item_ids

        for stage, progress in _STAGE_SEQUENCE:
            if stage in completed:
                # A prior attempt already succeeded this stage: skip its writes,
                # provider calls, and child work so a replay never duplicates. Its
                # outputs were restored above, so the next stage still runs against
                # real inputs rather than empty ones.
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
        carried_mappings: tuple[CarriedItemMapping, ...],
        affected_item_ids: tuple[UUID, ...],
        summary: dict[str, Any],
    ) -> tuple[dict[str, Any], tuple[CarriedItemMapping, ...], tuple[UUID, ...]]:
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
                {
                    "carriedItemCount": len(carried_mappings),
                    # The mapping identities are the evidence stage's input, so
                    # they are persisted with the checkpoint: the successor item
                    # ids are generated during materialization and cannot be
                    # recomputed by a later attempt.
                    CARRIED_MAPPINGS_KEY: encode_carried_mappings(carried_mappings),
                },
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
            return (
                {CARRIED_EVIDENCE_EDGE_COUNT_KEY: edge_count},
                carried_mappings,
                affected_item_ids,
            )

        if stage is RescanStage.DETECTING_AFFECTED_PASSAGES:
            affected_item_ids = await self._child_work.list_affected_items(
                org_id=job.org_id,
                project_id=job.project_id,
                before_version_id=plan.before_version_id,
                affected_element_ids=tuple(plan.affected_element_ids),
            )
            if affected_item_ids:
                await self._child_work.request_detection(
                    org_id=job.org_id,
                    project_id=job.project_id,
                    after_version_id=after_version_id,
                    affected_item_ids=affected_item_ids,
                    actor_id=self._actor_id(job),
                )
            # Added passages have no predecessor item, so they are freshly
            # detected on the after version, producing brand-new unresolved items
            # (no predecessor, no carried evidence, no copied decision). Their ids
            # join the affected set so they flow into research like any newly
            # detected item. Detection is scoped to exactly the added elements, so
            # the whole version is never re-detected.
            added_item_ids: tuple[UUID, ...] = ()
            if plan.added_after_element_ids:
                added_item_ids = await self._child_work.detect_added_items(
                    org_id=job.org_id,
                    project_id=job.project_id,
                    after_version_id=after_version_id,
                    added_after_element_ids=tuple(plan.added_after_element_ids),
                    actor_id=self._actor_id(job),
                )
            affected_item_ids = tuple(dict.fromkeys((*affected_item_ids, *added_item_ids)))
            summary["affectedItemCount"] = len(affected_item_ids)
            summary["addedItemCount"] = len(added_item_ids)
            return (
                {
                    "affectedItemCount": len(affected_item_ids),
                    "addedItemCount": len(added_item_ids),
                    # The research stage's input is these exact item ids. Added
                    # items are freshly created by scoped detection, so a later
                    # attempt cannot recompute them without repeating that child
                    # work; both id sets are persisted with the checkpoint.
                    AFFECTED_ITEM_IDS_KEY: encode_item_ids(affected_item_ids),
                    ADDED_ITEM_IDS_KEY: encode_item_ids(added_item_ids),
                },
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

    @staticmethod
    def _require_restorable(restored: RestoredRescanProgress) -> None:
        """Fail closed when a completed stage's output cannot be restored.

        Continuing past such a stage would run the next stage against empty
        inputs — zero evidence carried, zero research targets — and still report
        completion. That silent incorrectness is worse than a visible failure, so
        the job fails with a typed, non-retryable error naming the stage.
        """
        if not restored.unrecoverable_stages:
            return
        stage = min(restored.unrecoverable_stages, key=_STAGE_ORDER.index)
        raise JobExecutionError(
            SafeJobError(
                code="unrestorable_rescan_checkpoint",
                message=(
                    f"The completed '{stage.value}' stage has no restorable output, so a "
                    "resumed selective rescan cannot continue correctly."
                ),
                retryable=False,
            )
        )

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

"""Execute one scoped detection job through durable provider boundaries."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from clearcut.detection.adapters.sql_candidate_repository import (
    DetectionInvocationState,
    DetectionPersistenceError,
    SqlCandidateRepository,
)
from clearcut.detection.domain.candidates import CandidateItem
from clearcut.detection.ports.model_runtime import DetectionFailure, ModelRuntimePort
from clearcut.evaluation.application.evaluate import (
    EvaluationExecutionError,
    EvaluationService,
)
from clearcut.evaluation.domain.gates import run_deterministic_gates
from clearcut.evaluation.domain.rubric import DimensionStatus
from clearcut.evaluation.ports.judge import JudgeBindings
from clearcut.evaluation.ports.repository import EvaluationPersistenceError
from clearcut.operations.application.run_job import (
    JobExecutionError,
    JobExecutionResult,
)
from clearcut.operations.domain.jobs import RunStatus
from clearcut.operations.ports.job_repository import (
    JobNotFoundError,
    JobRecord,
    JobRepositoryPort,
    JobTransitionError,
    SafeJobError,
)
from clearcut.scripts.domain.elements import ScriptElement

_RUBRIC_VERSION = "clearcut-ten-dimension-rubric-v1"


class RunDetectionJobService:
    def __init__(
        self,
        *,
        repository: SqlCandidateRepository,
        job_repository: JobRepositoryPort,
        runtime: ModelRuntimePort,
        evaluation: EvaluationService,
    ) -> None:
        self._repository = repository
        self._job_repository = job_repository
        self._runtime = runtime
        self._evaluation = evaluation

    async def __call__(self, job: JobRecord) -> JobExecutionResult:
        version_id = self._version_id(job)
        element_scope = self._element_scope(job)
        lease_owner = job.lease_owner
        if lease_owner is None:
            raise JobExecutionError(
                SafeJobError(
                    code="invalid_detection_job",
                    message="The detection job has no active lease owner.",
                    retryable=False,
                )
            )
        await self._update_progress(job, progress=5, stage="reading_persisted_elements")
        try:
            detection_input = await self._repository.load_input(
                org_id=job.org_id,
                project_id=job.project_id,
                version_id=version_id,
                element_ids=element_scope,
            )
            policy_version, prompt_version = await self._repository.load_active_judge_configuration(
                org_id=job.org_id,
            )
        except DetectionPersistenceError as error:
            raise JobExecutionError(
                SafeJobError(
                    code="detection_configuration_unavailable",
                    message=str(error),
                    retryable=False,
                )
            ) from error

        await self._update_progress(job, progress=20, stage="detecting_candidates")
        candidates: list[CandidateItem] = []
        processed = 0
        skipped = 0
        detectable_count = sum(1 for element in detection_input.elements if element.text.strip())
        for element in detection_input.elements:
            if not element.text.strip():
                skipped += 1
                continue
            processed += 1
            candidates.extend(
                await self._detect_element(
                    job=job,
                    version_id=version_id,
                    element=element,
                )
            )
            await self._update_progress(
                job,
                progress=20 + (40 * processed / max(1, detectable_count)),
                stage="detecting_candidates",
            )

        if detectable_count == 0:
            await self._update_progress(
                job,
                progress=60,
                stage="detecting_candidates",
            )
        await self._update_progress(job, progress=65, stage="evaluating_findings")

        bindings = JudgeBindings(
            rubric_version=_RUBRIC_VERSION,
            prompt_version=prompt_version,
            policy_version=policy_version,
            input_sha256=self._judge_input_hash(version_id, candidates),
        )
        element_texts = {element.element_id: element.text for element in detection_input.elements}
        try:
            gate_results = run_deterministic_gates(candidates, element_texts)
            await self._repository.persist_gate_results(
                org_id=job.org_id,
                project_id=job.project_id,
                run_id=job.job_id,
                job_attempt_number=job.attempt_count,
                lease_owner=lease_owner,
                results=gate_results,
            )
            await self._update_progress(
                job,
                progress=75,
                stage="persisting_unresolved_findings",
            )
            item_count = await self._repository.materialize_unresolved_items(
                org_id=job.org_id,
                project_id=job.project_id,
                run_id=job.job_id,
                job_attempt_number=job.attempt_count,
                lease_owner=lease_owner,
                script_id=detection_input.script_id,
                version_id=version_id,
                candidates=candidates,
            )
            await self._update_progress(job, progress=85, stage="evaluating_findings")
            _evaluated_gates, evaluation = await self._evaluation.evaluate_detection_run(
                org_id=job.org_id,
                project_id=job.project_id,
                run_id=job.job_id,
                job_attempt_number=job.attempt_count,
                candidates=candidates,
                element_texts=element_texts,
                bindings=bindings,
                gate_results=gate_results,
            )
            judge_passed = all(
                verdict.status not in {DimensionStatus.FAILED, DimensionStatus.INCOMPLETE}
                for verdict in evaluation.verdicts
            )
            if not judge_passed:
                raise JobExecutionError(
                    SafeJobError(
                        code="judge_rejected",
                        message=(
                            "The bounded detection quality judge rejected this output "
                            "for accountable human review."
                        ),
                        retryable=False,
                    )
                )
        except EvaluationExecutionError as error:
            raise JobExecutionError(
                SafeJobError(
                    code=error.error.code,
                    message=error.error.message,
                    retryable=error.error.retryable,
                )
            ) from error
        except (DetectionPersistenceError, EvaluationPersistenceError) as error:
            raise JobExecutionError(
                SafeJobError(
                    code="detection_persistence_failed",
                    message="Detection output could not be persisted safely.",
                    retryable=False,
                )
            ) from error

        await self._update_progress(
            job,
            progress=95,
            stage="finalizing_detected_findings",
        )
        return JobExecutionResult(
            summary={
                "scriptVersionId": str(version_id),
                "elementsProcessed": processed,
                "elementsSkipped": skipped,
                "candidateCount": len(candidates),
                "gateResultCount": len(gate_results),
                "blockerCount": evaluation.blockers_count,
                "clearanceItemCount": item_count,
                "evaluationId": str(evaluation.evaluation_id),
                "headlineScore": evaluation.headline_score,
                "judgePassed": bool(candidates) and judge_passed,
                "reviewStatus": "unresolved",
                "reason": ("human_review_required" if candidates else "no_candidates_detected"),
            }
        )

    async def _update_progress(
        self,
        job: JobRecord,
        *,
        progress: float,
        stage: str,
    ) -> None:
        lease_owner = job.lease_owner
        if lease_owner is None:
            raise JobExecutionError(
                SafeJobError(
                    code="job_lease_lost",
                    message="The detection attempt is no longer active.",
                    retryable=False,
                )
            )
        try:
            await self._job_repository.update_progress(
                org_id=job.org_id,
                project_id=job.project_id,
                job_id=job.job_id,
                attempt_number=job.attempt_count,
                lease_owner=lease_owner,
                progress=progress,
                stage=stage,
            )
        except (JobNotFoundError, JobTransitionError) as error:
            raise JobExecutionError(
                SafeJobError(
                    code="job_lease_lost",
                    message="The detection attempt is no longer active.",
                    retryable=False,
                )
            ) from error

    async def _detect_element(
        self,
        *,
        job: JobRecord,
        version_id: UUID,
        element: ScriptElement,
    ) -> tuple[CandidateItem, ...]:
        try:
            prepared = await self._repository.prepare_invocation(
                org_id=job.org_id,
                project_id=job.project_id,
                run_id=job.job_id,
                job_attempt_number=job.attempt_count,
                version_id=version_id,
                element_id=element.element_id,
                requested_model=self._runtime.requested_model,
                input_sha256=self._element_input_hash(element),
            )
            if prepared.state is DetectionInvocationState.SUCCEEDED:
                if prepared.result is None:
                    raise DetectionPersistenceError(
                        "A succeeded detection invocation has no persisted result."
                    )
                return prepared.result.candidates
            if prepared.state is DetectionInvocationState.FAILED:
                if prepared.error is None:
                    raise DetectionPersistenceError(
                        "A failed detection invocation has no persisted safe error."
                    )
                raise JobExecutionError(
                    SafeJobError(
                        code=prepared.error.code,
                        message=prepared.error.message,
                        retryable=prepared.error.retryable,
                    )
                )
            if prepared.state is DetectionInvocationState.PENDING:
                raise JobExecutionError(
                    SafeJobError(
                        code="detection_invocation_pending",
                        message=(
                            "This job attempt already has a pending detection invocation; "
                            "manual review or an explicit later attempt is required."
                        ),
                        retryable=False,
                    )
                )

            result = await self._runtime.detect_element(element)
            if isinstance(result, DetectionFailure):
                await self._repository.persist_failure(
                    invocation_id=prepared.invocation_id,
                    org_id=job.org_id,
                    project_id=job.project_id,
                    run_id=job.job_id,
                    version_id=version_id,
                    element_id=element.element_id,
                    result=result,
                )
                raise JobExecutionError(
                    SafeJobError(
                        code=result.error.code,
                        message=result.error.message,
                        retryable=result.error.retryable,
                    )
                )
            return await self._repository.persist_success(
                invocation_id=prepared.invocation_id,
                org_id=job.org_id,
                project_id=job.project_id,
                run_id=job.job_id,
                version_id=version_id,
                element_id=element.element_id,
                result=result,
            )
        except JobExecutionError:
            raise
        except DetectionPersistenceError as error:
            raise JobExecutionError(
                SafeJobError(
                    code="detection_persistence_failed",
                    message="Detection output could not be persisted safely.",
                    retryable=False,
                )
            ) from error

    @staticmethod
    def _version_id(job: JobRecord) -> UUID:
        payload = job.payload
        target = payload.get("target")
        target_id = target.get("id") if isinstance(target, dict) else None
        valid_payload = (
            job.job_type == "detection"
            and job.status is RunStatus.RUNNING
            and job.attempt_count > 0
            and set(payload) <= {"schemaVersion", "target", "elementIds"}
            and {"schemaVersion", "target"} <= set(payload)
            and payload.get("schemaVersion") == 1
            and not isinstance(payload.get("schemaVersion"), bool)
            and isinstance(target, dict)
            and set(target) == {"type", "id"}
            and target.get("type") == "script_version"
            and isinstance(target_id, str)
            and RunDetectionJobService._element_ids_shape_valid(payload.get("elementIds"))
        )
        if not valid_payload:
            raise JobExecutionError(
                SafeJobError(
                    code="invalid_detection_job",
                    message="The detection job payload or active attempt is invalid.",
                    retryable=False,
                )
            )
        try:
            return UUID(target_id)
        except ValueError as error:
            raise JobExecutionError(
                SafeJobError(
                    code="invalid_detection_job",
                    message="The detection job target is invalid.",
                    retryable=False,
                )
            ) from error

    @staticmethod
    def _element_ids_shape_valid(element_ids: Any) -> bool:
        # ``elementIds`` is optional. When present it must be a non-empty list of
        # UUID strings scoping detection to explicit after-version elements (a
        # selective rescan detecting only changed/added passages). Its absence
        # preserves whole-version detection.
        if element_ids is None:
            return True
        if not isinstance(element_ids, list) or not element_ids:
            return False
        for element_id in element_ids:
            if not isinstance(element_id, str):
                return False
            try:
                UUID(element_id)
            except ValueError:
                return False
        return True

    @staticmethod
    def _element_scope(job: JobRecord) -> tuple[UUID, ...] | None:
        raw = job.payload.get("elementIds")
        if raw is None:
            return None
        return tuple(UUID(str(element_id)) for element_id in raw)

    @staticmethod
    def _element_input_hash(element: ScriptElement) -> str:
        return RunDetectionJobService._hash(
            {
                "elementId": str(element.element_id),
                "versionId": str(element.version_id),
                "ordinal": element.ordinal,
                "elementType": element.element_type.value,
                "text": element.text,
            }
        )

    @staticmethod
    def _judge_input_hash(
        version_id: UUID,
        candidates: list[CandidateItem],
    ) -> str:
        return RunDetectionJobService._hash(
            {
                "versionId": str(version_id),
                "candidates": [
                    {
                        "candidateId": str(candidate.item_id),
                        "elementId": str(candidate.element_id),
                        "category": candidate.category.value,
                        "spanStart": candidate.span_start,
                        "spanEnd": candidate.span_end,
                        "text": candidate.text,
                        "rationale": candidate.rationale,
                        "uncertainty": candidate.uncertainty,
                    }
                    for candidate in candidates
                ],
            }
        )

    @staticmethod
    def _hash(value: dict[str, Any]) -> str:
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

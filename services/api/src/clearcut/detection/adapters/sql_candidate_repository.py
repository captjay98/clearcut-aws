"""SQL authority for scoped, replay-safe detection invocations and candidates."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

import sqlalchemy as sa
import uuid6
from clearcut.database import database_wall_clock_sql, session_scope
from clearcut.detection.domain.candidates import (
    CandidateItem,
    ClearanceCategory,
    UncertaintyLevel,
)
from clearcut.detection.ports.model_runtime import (
    DetectionAttemptMetadata,
    DetectionFailure,
    DetectionSafeError,
    DetectionSuccess,
    DetectionTokenUsage,
)
from clearcut.evaluation.domain.gates import GateResult
from clearcut.scripts.domain.elements import ElementType, ScriptElement
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


class DetectionPersistenceError(RuntimeError):
    pass


class DetectionInvocationState(StrEnum):
    READY = "ready"
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True)
class DetectionInput:
    script_id: UUID
    version_id: UUID
    elements: tuple[ScriptElement, ...]


@dataclass(frozen=True)
class PreparedDetectionInvocation:
    invocation_id: UUID
    state: DetectionInvocationState
    result: DetectionSuccess | None = None
    error: DetectionSafeError | None = None


class SqlCandidateRepository:
    async def load_input(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        version_id: UUID,
    ) -> DetectionInput:
        async with session_scope() as session:
            version = (
                await session.execute(
                    sa.text(
                        "SELECT script_id FROM script_versions "
                        "WHERE id = :version_id AND org_id = :org_id "
                        "AND project_id = :project_id"
                    ),
                    {
                        "version_id": str(version_id),
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                    },
                )
            ).mappings().first()
            if version is None:
                raise DetectionPersistenceError(
                    "The script version was not found in the scoped project."
                )
            rows = (
                await session.execute(
                    sa.text(
                        "SELECT * FROM script_elements WHERE version_id = :version_id "
                        "ORDER BY ordinal, id"
                    ),
                    {"version_id": str(version_id)},
                )
            ).mappings().all()
        return DetectionInput(
            script_id=self._uuid(version["script_id"]),
            version_id=version_id,
            elements=tuple(
                ScriptElement(
                    element_id=self._uuid(row["id"]),
                    version_id=self._uuid(row["version_id"]),
                    ordinal=int(row["ordinal"]),
                    element_type=ElementType(str(row["element_type"])),
                    text=str(row["text"]),
                    scene_number=(
                        int(row["scene_number"])
                        if row["scene_number"] is not None
                        else None
                    ),
                    page_number=(
                        int(row["page_number"])
                        if row["page_number"] is not None
                        else None
                    ),
                )
                for row in rows
            ),
        )

    async def load_active_judge_configuration(
        self,
        *,
        org_id: UUID,
    ) -> tuple[str, str]:
        async with session_scope() as session:
            rows = (
                await session.execute(
                    sa.text(
                        "SELECT policy_version, prompt_version "
                        "FROM protected_configurations "
                        "WHERE org_id = :org_id AND lifecycle = 'active' "
                        "ORDER BY created_at DESC, id DESC"
                    ),
                    {"org_id": str(org_id)},
                )
            ).mappings().all()
        if len(rows) != 1:
            raise DetectionPersistenceError(
                "Exactly one active organization policy and prompt binding is required."
            )
        policy_version = str(rows[0]["policy_version"]).strip()
        prompt_version = str(rows[0]["prompt_version"]).strip()
        if not policy_version or not prompt_version:
            raise DetectionPersistenceError(
                "The active organization policy or prompt binding is incomplete."
            )
        return policy_version, prompt_version

    async def prepare_invocation(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        run_id: UUID,
        job_attempt_number: int,
        version_id: UUID,
        element_id: UUID,
        requested_model: str,
        input_sha256: str,
    ) -> PreparedDetectionInvocation:
        self._validate_identity(job_attempt_number, requested_model, input_sha256)
        invocation_id = uuid6.uuid7()
        now = datetime.now(UTC)
        try:
            async with session_scope() as session:
                lease_owner = await self._validate_active_input(
                    session,
                    org_id=org_id,
                    project_id=project_id,
                    run_id=run_id,
                    job_attempt_number=job_attempt_number,
                    version_id=version_id,
                    element_id=element_id,
                )
                await self._fence_active_lease(
                    session,
                    org_id=org_id,
                    project_id=project_id,
                    run_id=run_id,
                    job_attempt_number=job_attempt_number,
                    lease_owner=lease_owner,
                )
                row = (
                    await session.execute(
                        sa.text(
                            """
                            INSERT INTO detection_invocations (
                                id, org_id, project_id, run_id, job_attempt_number,
                                lease_owner, script_version_id, element_id, status,
                                requested_model, input_sha256, created_at
                            ) VALUES (
                                :id, :org_id, :project_id, :run_id,
                                :job_attempt_number, :lease_owner, :version_id, :element_id,
                                'pending', :requested_model, :input_sha256, :created_at
                            )
                            ON CONFLICT (
                                org_id, project_id, run_id,
                                job_attempt_number, element_id
                            ) DO NOTHING
                            RETURNING *
                            """
                        ),
                        {
                            "id": str(invocation_id),
                            "org_id": str(org_id),
                            "project_id": str(project_id),
                            "run_id": str(run_id),
                            "job_attempt_number": job_attempt_number,
                            "lease_owner": lease_owner,
                            "version_id": str(version_id),
                            "element_id": str(element_id),
                            "requested_model": requested_model,
                            "input_sha256": input_sha256,
                            "created_at": now,
                        },
                    )
                ).mappings().first()
                if row is not None:
                    await self._fence_active_lease(
                        session,
                        org_id=org_id,
                        project_id=project_id,
                        run_id=run_id,
                        job_attempt_number=job_attempt_number,
                        lease_owner=lease_owner,
                    )
                    return PreparedDetectionInvocation(
                        invocation_id=self._uuid(row["id"]),
                        state=DetectionInvocationState.READY,
                    )
                row = (
                    await session.execute(
                        sa.text(
                            "SELECT * FROM detection_invocations "
                            "WHERE org_id = :org_id AND project_id = :project_id "
                            "AND run_id = :run_id "
                            "AND job_attempt_number = :job_attempt_number "
                            "AND element_id = :element_id"
                        ),
                        {
                            "org_id": str(org_id),
                            "project_id": str(project_id),
                            "run_id": str(run_id),
                            "job_attempt_number": job_attempt_number,
                            "element_id": str(element_id),
                        },
                    )
                ).mappings().one()
                self._validate_immutable_identity(
                    row,
                    version_id=version_id,
                    requested_model=requested_model,
                    input_sha256=input_sha256,
                )
                state = DetectionInvocationState(str(row["status"]))
                if state is DetectionInvocationState.SUCCEEDED:
                    return PreparedDetectionInvocation(
                        invocation_id=self._uuid(row["id"]),
                        state=state,
                        result=await self._load_success(session, row),
                    )
                if state is DetectionInvocationState.FAILED:
                    error = self._safe_error(row["safe_error"])
                    if error is None:
                        raise DetectionPersistenceError(
                            "A failed detection invocation has no safe error."
                        )
                    return PreparedDetectionInvocation(
                        invocation_id=self._uuid(row["id"]),
                        state=state,
                        error=error,
                    )
                return PreparedDetectionInvocation(
                    invocation_id=self._uuid(row["id"]),
                    state=state,
                )
        except IntegrityError as error:
            raise DetectionPersistenceError(
                "Detection invocation intent conflicts with scoped database state."
            ) from error

    async def persist_success(
        self,
        *,
        invocation_id: UUID,
        org_id: UUID,
        project_id: UUID,
        run_id: UUID,
        version_id: UUID,
        element_id: UUID,
        result: DetectionSuccess,
    ) -> tuple[CandidateItem, ...]:
        self._validate_success(result, element_id)
        now = datetime.now(UTC)
        try:
            async with session_scope() as session:
                invocation = await self._require_pending(
                    session,
                    invocation_id=invocation_id,
                    org_id=org_id,
                    project_id=project_id,
                    run_id=run_id,
                    version_id=version_id,
                    element_id=element_id,
                    requested_model=result.metadata.requested_model,
                )
                rows = [
                    {
                        "id": str(candidate.item_id),
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                        "run_id": str(run_id),
                        "invocation_id": str(invocation_id),
                        "version_id": str(version_id),
                        "element_id": str(element_id),
                        "ordinal": ordinal,
                        "category": candidate.category.value,
                        "span_start": candidate.span_start,
                        "span_end": candidate.span_end,
                        "text": candidate.text,
                        "rationale": candidate.rationale,
                        "uncertainty": candidate.uncertainty,
                        "candidate_fingerprint": self.candidate_fingerprint(
                            version_id,
                            candidate,
                        ),
                        "created_at": now,
                    }
                    for ordinal, candidate in enumerate(result.candidates, start=1)
                ]
                if rows:
                    await session.execute(
                        sa.text(
                            """
                            INSERT INTO detection_candidates (
                                id, org_id, project_id, run_id, invocation_id,
                                script_version_id, element_id, ordinal, category,
                                span_start, span_end, text, rationale, uncertainty,
                                candidate_fingerprint, created_at
                            ) VALUES (
                                :id, :org_id, :project_id, :run_id, :invocation_id,
                                :version_id, :element_id, :ordinal, :category,
                                :span_start, :span_end, :text, :rationale, :uncertainty,
                                :candidate_fingerprint, :created_at
                            )
                            """
                        ),
                        rows,
                    )
                metadata = result.metadata
                updated = (
                    await session.execute(
                        sa.text(
                            """
                            UPDATE detection_invocations SET
                                status = 'succeeded',
                                returned_model = :returned_model,
                                response_id = :response_id,
                                input_tokens = :input_tokens,
                                output_tokens = :output_tokens,
                                total_tokens = :total_tokens,
                                latency_ms = :latency_ms,
                                candidate_count = :candidate_count,
                                completed_at = :completed_at
                            WHERE id = :invocation_id AND org_id = :org_id
                                AND project_id = :project_id AND run_id = :run_id
                                AND status = 'pending'
                            RETURNING id
                            """
                        ),
                        {
                            "invocation_id": str(invocation_id),
                            "org_id": str(org_id),
                            "project_id": str(project_id),
                            "run_id": str(run_id),
                            "returned_model": metadata.returned_model,
                            "response_id": metadata.response_id,
                            "input_tokens": metadata.usage.input_tokens,
                            "output_tokens": metadata.usage.output_tokens,
                            "total_tokens": metadata.usage.total_tokens,
                            "latency_ms": metadata.latency_ms,
                            "candidate_count": len(result.candidates),
                            "completed_at": now,
                        },
                    )
                ).first()
                if updated is None:
                    raise DetectionPersistenceError(
                        "The detection invocation was already finalized."
                    )
                if str(invocation["input_sha256"]) == "":
                    raise DetectionPersistenceError(
                        "The detection invocation input binding is missing."
                    )
                await self._fence_active_lease(
                    session,
                    org_id=org_id,
                    project_id=project_id,
                    run_id=run_id,
                    job_attempt_number=int(invocation["job_attempt_number"]),
                    lease_owner=str(invocation["lease_owner"]),
                )
        except IntegrityError as error:
            raise DetectionPersistenceError(
                "Detection candidate provenance conflicts with scoped database state."
            ) from error
        return result.candidates

    async def persist_failure(
        self,
        *,
        invocation_id: UUID,
        org_id: UUID,
        project_id: UUID,
        run_id: UUID,
        version_id: UUID,
        element_id: UUID,
        result: DetectionFailure,
    ) -> None:
        if result.attempt.error != result.error:
            raise DetectionPersistenceError(
                "Detection failure metadata does not match its safe error."
            )
        now = datetime.now(UTC)
        try:
            async with session_scope() as session:
                invocation = await self._require_pending(
                    session,
                    invocation_id=invocation_id,
                    org_id=org_id,
                    project_id=project_id,
                    run_id=run_id,
                    version_id=version_id,
                    element_id=element_id,
                    requested_model=result.attempt.requested_model,
                )
                statement = sa.text(
                    """
                    UPDATE detection_invocations SET
                        status = 'failed', returned_model = :returned_model,
                        response_id = :response_id,
                        input_tokens = :input_tokens,
                        output_tokens = :output_tokens,
                        total_tokens = :total_tokens,
                        latency_ms = :latency_ms,
                        safe_error = :safe_error,
                        completed_at = :completed_at
                    WHERE id = :invocation_id AND org_id = :org_id
                        AND project_id = :project_id AND run_id = :run_id
                        AND status = 'pending'
                    RETURNING id
                    """
                ).bindparams(sa.bindparam("safe_error", type_=sa.JSON()))
                updated = (
                    await session.execute(
                        statement,
                        {
                            "invocation_id": str(invocation_id),
                            "org_id": str(org_id),
                            "project_id": str(project_id),
                            "run_id": str(run_id),
                            "returned_model": result.attempt.returned_model,
                            "response_id": result.attempt.response_id,
                            "input_tokens": result.attempt.usage.input_tokens,
                            "output_tokens": result.attempt.usage.output_tokens,
                            "total_tokens": result.attempt.usage.total_tokens,
                            "latency_ms": result.attempt.latency_ms,
                            "safe_error": asdict(result.error),
                            "completed_at": now,
                        },
                    )
                ).first()
                if updated is None:
                    raise DetectionPersistenceError(
                        "The detection invocation was already finalized."
                    )
                await self._fence_active_lease(
                    session,
                    org_id=org_id,
                    project_id=project_id,
                    run_id=run_id,
                    job_attempt_number=int(invocation["job_attempt_number"]),
                    lease_owner=str(invocation["lease_owner"]),
                )
        except IntegrityError as error:
            raise DetectionPersistenceError(
                "Detection failure provenance conflicts with scoped database state."
            ) from error

    async def persist_gate_results(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        run_id: UUID,
        job_attempt_number: int,
        lease_owner: str,
        results: list[GateResult],
    ) -> None:
        try:
            async with session_scope() as session:
                job = (
                    await session.execute(
                        sa.text(
                            "SELECT status, attempt_count, lease_owner, "
                            "lease_expires_at > CURRENT_TIMESTAMP AS lease_active FROM jobs "
                            "WHERE id = :run_id AND org_id = :org_id "
                            "AND project_id = :project_id"
                        ),
                        {
                            "run_id": str(run_id),
                            "org_id": str(org_id),
                            "project_id": str(project_id),
                        },
                    )
                ).mappings().first()
                if (
                    job is None
                    or str(job["status"]) != "running"
                    or int(job["attempt_count"]) != job_attempt_number
                    or str(job["lease_owner"] or "") != lease_owner
                    or not bool(job["lease_active"])
                ):
                    raise DetectionPersistenceError(
                        "Gate results do not match the active detection job attempt."
                    )
                await self._fence_active_lease(
                    session,
                    org_id=org_id,
                    project_id=project_id,
                    run_id=run_id,
                    job_attempt_number=job_attempt_number,
                    lease_owner=lease_owner,
                )
                if not results:
                    return
                candidate_ids = {result.candidate_id for result in results}
                persisted_candidate_ids = {
                    self._uuid(row["id"])
                    for row in (
                        await session.execute(
                            sa.text(
                                "SELECT id FROM detection_candidates "
                                "WHERE org_id = :org_id AND project_id = :project_id "
                                "AND run_id = :run_id"
                            ),
                            {
                                "org_id": str(org_id),
                                "project_id": str(project_id),
                                "run_id": str(run_id),
                            },
                        )
                    ).mappings()
                }
                if not candidate_ids.issubset(persisted_candidate_ids):
                    raise DetectionPersistenceError(
                        "A gate result references a candidate outside the scoped run."
                    )
                await session.execute(
                    sa.text(
                        """
                        INSERT INTO deterministic_gate_results (
                            id, org_id, project_id, run_id, candidate_id,
                            gate_name, passed, severity, details, created_at
                        ) VALUES (
                            :id, :org_id, :project_id, :run_id, :candidate_id,
                            :gate_name, :passed, :severity, :details, :created_at
                        )
                        ON CONFLICT (
                            org_id, project_id, run_id, candidate_id, gate_name
                        ) DO NOTHING
                        """
                    ),
                    [
                        {
                            "id": str(result.gate_id),
                            "org_id": str(org_id),
                            "project_id": str(project_id),
                            "run_id": str(run_id),
                            "candidate_id": str(result.candidate_id),
                            "gate_name": result.gate_name,
                            "passed": result.passed,
                            "severity": result.severity.value,
                            "details": result.details,
                            "created_at": result.created_at,
                        }
                        for result in results
                    ],
                )
                await self._fence_active_lease(
                    session,
                    org_id=org_id,
                    project_id=project_id,
                    run_id=run_id,
                    job_attempt_number=job_attempt_number,
                    lease_owner=lease_owner,
                )
        except IntegrityError as error:
            raise DetectionPersistenceError(
                "Gate result provenance conflicts with scoped database state."
            ) from error

    async def materialize_unresolved_items(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        run_id: UUID,
        job_attempt_number: int,
        lease_owner: str,
        script_id: UUID,
        version_id: UUID,
        candidates: list[CandidateItem],
    ) -> int:
        try:
            async with session_scope() as session:
                job = (
                    await session.execute(
                        sa.text(
                            "SELECT status, attempt_count, lease_owner, "
                            "lease_expires_at > CURRENT_TIMESTAMP AS lease_active FROM jobs "
                            "WHERE id = :run_id AND org_id = :org_id "
                            "AND project_id = :project_id"
                        ),
                        {
                            "run_id": str(run_id),
                            "org_id": str(org_id),
                            "project_id": str(project_id),
                        },
                    )
                ).mappings().first()
                if (
                    job is None
                    or str(job["status"]) != "running"
                    or int(job["attempt_count"]) != job_attempt_number
                    or str(job["lease_owner"] or "") != lease_owner
                    or not bool(job["lease_active"])
                ):
                    raise DetectionPersistenceError(
                        "Clearance items do not match the active detection job attempt."
                    )
                await self._fence_active_lease(
                    session,
                    org_id=org_id,
                    project_id=project_id,
                    run_id=run_id,
                    job_attempt_number=job_attempt_number,
                    lease_owner=lease_owner,
                )
                if not candidates:
                    return 0
                persisted = {
                    self._uuid(row["id"]): row
                    for row in (
                        await session.execute(
                            sa.text(
                                "SELECT id, element_id, category, text, "
                                "candidate_fingerprint FROM detection_candidates "
                                "WHERE org_id = :org_id AND project_id = :project_id "
                                "AND run_id = :run_id "
                                "AND script_version_id = :version_id"
                            ),
                            {
                                "org_id": str(org_id),
                                "project_id": str(project_id),
                                "run_id": str(run_id),
                                "version_id": str(version_id),
                            },
                        )
                    ).mappings()
                }
                candidate_ids = {candidate.item_id for candidate in candidates}
                if not candidate_ids.issubset(persisted):
                    raise DetectionPersistenceError(
                        "A clearance item candidate is outside the scoped detection run."
                    )
                now = datetime.now(UTC)
                await session.execute(
                    sa.text(
                        """
                        INSERT INTO clearance_items (
                            id, org_id, project_id, script_id, version_id,
                            element_id, category, text, status, created_at,
                            detection_candidate_id, detection_run_id,
                            candidate_fingerprint
                        ) VALUES (
                            :id, :org_id, :project_id, :script_id, :version_id,
                            :element_id, :category, :text, 'unresolved', :created_at,
                            :candidate_id, :run_id, :candidate_fingerprint
                        )
                        ON CONFLICT (
                            org_id, project_id, version_id, candidate_fingerprint
                        ) DO NOTHING
                        """
                    ),
                    [
                        {
                            "id": str(uuid6.uuid7()),
                            "org_id": str(org_id),
                            "project_id": str(project_id),
                            "script_id": str(script_id),
                            "version_id": str(version_id),
                            "element_id": str(persisted[candidate.item_id]["element_id"]),
                            "category": str(persisted[candidate.item_id]["category"]),
                            "text": str(persisted[candidate.item_id]["text"]),
                            "created_at": now,
                            "candidate_id": str(candidate.item_id),
                            "run_id": str(run_id),
                            "candidate_fingerprint": str(
                                persisted[candidate.item_id]["candidate_fingerprint"]
                            ),
                        }
                        for candidate in candidates
                    ],
                )
                item_fingerprints = {
                    str(row["candidate_fingerprint"])
                    for row in (
                        await session.execute(
                            sa.text(
                                "SELECT candidate_fingerprint FROM clearance_items "
                                "WHERE org_id = :org_id AND project_id = :project_id "
                                "AND version_id = :version_id "
                                "AND candidate_fingerprint IS NOT NULL"
                            ),
                            {
                                "org_id": str(org_id),
                                "project_id": str(project_id),
                                "version_id": str(version_id),
                            },
                        )
                    ).mappings()
                }
                expected_fingerprints = {
                    str(persisted[candidate.item_id]["candidate_fingerprint"])
                    for candidate in candidates
                }
                item_count = len(item_fingerprints & expected_fingerprints)
                await self._fence_active_lease(
                    session,
                    org_id=org_id,
                    project_id=project_id,
                    run_id=run_id,
                    job_attempt_number=job_attempt_number,
                    lease_owner=lease_owner,
                )
                return item_count
        except IntegrityError as error:
            raise DetectionPersistenceError(
                "Clearance item projection conflicts with scoped detection provenance."
            ) from error

    async def _fence_active_lease(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        run_id: UUID,
        job_attempt_number: int,
        lease_owner: str,
    ) -> None:
        clock_sql = database_wall_clock_sql(session.get_bind().dialect.name)
        fenced = (
            await session.execute(
                sa.text(
                    f"UPDATE jobs SET updated_at = {clock_sql} "
                    "WHERE id = :run_id AND org_id = :org_id "
                    "AND project_id = :project_id AND status = 'running' "
                    "AND attempt_count = :job_attempt_number "
                    "AND lease_owner = :lease_owner "
                    f"AND lease_expires_at > {clock_sql} RETURNING id"
                ),
                {
                    "run_id": str(run_id),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                    "job_attempt_number": job_attempt_number,
                    "lease_owner": lease_owner,
                },
            )
        ).first()
        if fenced is None:
            raise DetectionPersistenceError(
                "The detection write does not match an active job lease."
            )

    async def _validate_active_input(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        run_id: UUID,
        job_attempt_number: int,
        version_id: UUID,
        element_id: UUID,
    ) -> str:
        row = (
            await session.execute(
                sa.text(
                    """
                    SELECT j.status, j.attempt_count, j.lease_owner,
                           j.lease_expires_at > CURRENT_TIMESTAMP AS lease_active
                    FROM jobs j
                    JOIN script_versions v
                      ON v.id = :version_id
                     AND v.org_id = j.org_id
                     AND v.project_id = j.project_id
                    JOIN script_elements e
                      ON e.id = :element_id
                     AND e.version_id = v.id
                    WHERE j.id = :run_id AND j.org_id = :org_id
                      AND j.project_id = :project_id
                    """
                ),
                {
                    "run_id": str(run_id),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                    "version_id": str(version_id),
                    "element_id": str(element_id),
                },
            )
        ).mappings().first()
        if row is None:
            raise DetectionPersistenceError(
                "The detection invocation input is outside the scoped job."
            )
        if (
            str(row["status"]) != "running"
            or int(row["attempt_count"]) != job_attempt_number
        ):
            raise DetectionPersistenceError(
                "The detection invocation does not match the active job attempt."
            )
        if row["lease_owner"] is None or not bool(row["lease_active"]):
            raise DetectionPersistenceError(
                "The detection invocation does not match an active job lease."
            )
        return str(row["lease_owner"])

    async def _require_pending(
        self,
        session: AsyncSession,
        *,
        invocation_id: UUID,
        org_id: UUID,
        project_id: UUID,
        run_id: UUID,
        version_id: UUID,
        element_id: UUID,
        requested_model: str,
    ) -> RowMapping:
        row = (
            await session.execute(
                sa.text(
                    "SELECT * FROM detection_invocations "
                    "WHERE id = :invocation_id AND org_id = :org_id "
                    "AND project_id = :project_id AND run_id = :run_id"
                ),
                {
                    "invocation_id": str(invocation_id),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                    "run_id": str(run_id),
                },
            )
        ).mappings().first()
        if row is None:
            raise DetectionPersistenceError(
                "The scoped detection invocation does not exist."
            )
        self._validate_immutable_identity(
            row,
            version_id=version_id,
            requested_model=requested_model,
            input_sha256=str(row["input_sha256"]),
        )
        if self._uuid(row["element_id"]) != element_id:
            raise DetectionPersistenceError(
                "The detection invocation element binding does not match."
            )
        if DetectionInvocationState(str(row["status"])) is not DetectionInvocationState.PENDING:
            raise DetectionPersistenceError(
                "The detection invocation was already finalized."
            )
        job = (
            await session.execute(
                sa.text(
                    "SELECT status, attempt_count, lease_owner, "
                    "lease_expires_at > CURRENT_TIMESTAMP AS lease_active FROM jobs "
                    "WHERE id = :run_id AND org_id = :org_id "
                    "AND project_id = :project_id"
                ),
                {
                    "run_id": str(run_id),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                },
            )
        ).mappings().first()
        if (
            job is None
            or str(job["status"]) != "running"
            or int(job["attempt_count"]) != int(row["job_attempt_number"])
        ):
            raise DetectionPersistenceError(
                "The detection invocation does not match the active job attempt."
            )
        if (
            job["lease_owner"] is None
            or str(job["lease_owner"]) != str(row["lease_owner"])
            or not bool(job["lease_active"])
        ):
            raise DetectionPersistenceError(
                "The detection invocation does not match an active job lease."
            )
        await self._fence_active_lease(
            session,
            org_id=org_id,
            project_id=project_id,
            run_id=run_id,
            job_attempt_number=int(row["job_attempt_number"]),
            lease_owner=str(row["lease_owner"]),
        )
        return row

    async def _load_success(
        self,
        session: AsyncSession,
        invocation: RowMapping,
    ) -> DetectionSuccess:
        rows = (
            await session.execute(
                sa.text(
                    "SELECT * FROM detection_candidates "
                    "WHERE invocation_id = :invocation_id "
                    "AND org_id = :org_id AND project_id = :project_id "
                    "ORDER BY ordinal"
                ),
                {
                    "invocation_id": str(invocation["id"]),
                    "org_id": str(invocation["org_id"]),
                    "project_id": str(invocation["project_id"]),
                },
            )
        ).mappings().all()
        candidates = tuple(
            CandidateItem(
                item_id=self._uuid(row["id"]),
                category=ClearanceCategory(str(row["category"])),
                element_id=self._uuid(row["element_id"]),
                span_start=int(row["span_start"]),
                span_end=int(row["span_end"]),
                text=str(row["text"]),
                rationale=str(row["rationale"]),
                uncertainty=self._uncertainty(row["uncertainty"]),
            )
            for row in rows
        )
        if len(candidates) != int(invocation["candidate_count"]):
            raise DetectionPersistenceError(
                "Detection candidate count does not match terminal provenance."
            )
        metadata = DetectionAttemptMetadata(
            status="succeeded",
            requested_model=str(invocation["requested_model"]),
            returned_model=str(invocation["returned_model"]),
            response_id=str(invocation["response_id"]),
            usage=DetectionTokenUsage(
                input_tokens=self._optional_int(invocation["input_tokens"]),
                output_tokens=self._optional_int(invocation["output_tokens"]),
                total_tokens=self._optional_int(invocation["total_tokens"]),
            ),
            latency_ms=int(invocation["latency_ms"]),
            error=None,
        )
        return DetectionSuccess(candidates=candidates, metadata=metadata)

    @staticmethod
    def _validate_identity(
        job_attempt_number: int,
        requested_model: str,
        input_sha256: str,
    ) -> None:
        if job_attempt_number <= 0 or not requested_model.strip():
            raise DetectionPersistenceError(
                "A detection invocation requires a positive attempt and model."
            )
        if len(input_sha256) != 64 or any(
            character not in "0123456789abcdef"
            for character in input_sha256.lower()
        ):
            raise DetectionPersistenceError(
                "The detection invocation input hash is invalid."
            )

    @staticmethod
    def _validate_immutable_identity(
        row: RowMapping,
        *,
        version_id: UUID,
        requested_model: str,
        input_sha256: str,
    ) -> None:
        if (
            UUID(str(row["script_version_id"])) != version_id
            or str(row["requested_model"]) != requested_model
            or str(row["input_sha256"]) != input_sha256
        ):
            raise DetectionPersistenceError(
                "A replay cannot change immutable input or model bindings."
            )

    @staticmethod
    def _validate_success(result: DetectionSuccess, element_id: UUID) -> None:
        metadata = result.metadata
        if (
            metadata.status != "succeeded"
            or metadata.error is not None
            or not metadata.requested_model.strip()
            or metadata.returned_model is None
            or not metadata.returned_model.strip()
            or metadata.response_id is None
            or not metadata.response_id.strip()
            or metadata.latency_ms < 0
        ):
            raise DetectionPersistenceError(
                "Successful detection provider metadata is incomplete."
            )
        if any(candidate.element_id != element_id for candidate in result.candidates):
            raise DetectionPersistenceError(
                "A detection candidate does not match the invocation element."
            )

    @staticmethod
    def candidate_fingerprint(version_id: UUID, candidate: CandidateItem) -> str:
        payload = {
            "versionId": str(version_id),
            "elementId": str(candidate.element_id),
            "category": candidate.category.value,
            "spanStart": candidate.span_start,
            "spanEnd": candidate.span_end,
            "text": candidate.text,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    @staticmethod
    def _safe_error(value: Any) -> DetectionSafeError | None:
        if value is None:
            return None
        try:
            payload = json.loads(value) if isinstance(value, str) else value
        except (TypeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        code = payload.get("code")
        message = payload.get("message")
        retryable = payload.get("retryable")
        if (
            not isinstance(code, str)
            or not isinstance(message, str)
            or not isinstance(retryable, bool)
        ):
            return None
        return DetectionSafeError(code=code, message=message, retryable=retryable)

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        return int(value) if value is not None else None

    @staticmethod
    def _uuid(value: Any) -> UUID:
        return value if isinstance(value, UUID) else UUID(str(value))

    @staticmethod
    def _uncertainty(value: Any) -> UncertaintyLevel:
        text = str(value)
        if text == "low":
            return "low"
        if text == "medium":
            return "medium"
        if text == "high":
            return "high"
        raise ValueError(f"Unexpected uncertainty level: {text!r}")

"""SQL authority for tenant-scoped observable job lifecycles."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import sqlalchemy as sa
import uuid6
from clearcut.database import database_wall_clock_sql, session_scope
from clearcut.operations.domain.jobs import RunStatus
from clearcut.operations.ports.job_repository import (
    EnqueueJob,
    EnqueueResult,
    JobAttempt,
    JobLeaseLostError,
    JobLifecycleEvent,
    JobNotFoundError,
    JobPage,
    JobRecord,
    JobTransitionError,
    SafeJobError,
    validated_persisted_job_target,
)
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

_ATTEMPT_ACTIONS = (
    "job.attempt.started",
    "job.attempt.succeeded",
    "job.attempt.failed",
    "job.attempt.cancelled",
    "job.attempt.interrupted",
)
_LIFECYCLE_ACTIONS = {
    "job.cancelled": "cancelled",
    "job.retry.requested": "retry_requested",
}


class SqlJobRepository:
    def __init__(
        self,
        *,
        lease_duration: timedelta = timedelta(minutes=15),
        recovery_batch_size: int = 100,
    ) -> None:
        if lease_duration.total_seconds() <= 0:
            raise ValueError("Job lease duration must be positive.")
        if recovery_batch_size <= 0:
            raise ValueError("Recovery batch size must be positive.")
        self._lease_seconds = lease_duration.total_seconds()
        self._recovery_batch_size = recovery_batch_size

    async def enqueue(self, command: EnqueueJob) -> EnqueueResult:
        now = datetime.now(UTC)
        proposed_job_id = uuid6.uuid7()
        correlation_id = uuid6.uuid7()
        insert_job = sa.text(
            """
            INSERT INTO jobs (
                id, org_id, project_id, job_type, status, idempotency_key,
                payload, progress, stage, actor_id, correlation_id,
                attempt_count, available_at, created_at, updated_at
            ) VALUES (
                :id, :org_id, :project_id, :job_type, 'queued', :idempotency_key,
                :payload, 0, 'queued', :actor_id, :correlation_id,
                0, :available_at, :created_at, :updated_at
            )
            ON CONFLICT (org_id, project_id, idempotency_key) DO NOTHING
            RETURNING *
            """
        ).bindparams(sa.bindparam("payload", type_=sa.JSON()))

        async with session_scope() as session:
            row = (
                (
                    await session.execute(
                        insert_job,
                        {
                            "id": str(proposed_job_id),
                            "org_id": str(command.org_id),
                            "project_id": str(command.project_id),
                            "job_type": command.job_type,
                            "idempotency_key": command.idempotency_key,
                            "payload": command.payload,
                            "actor_id": str(command.actor_id),
                            "correlation_id": str(correlation_id),
                            "available_at": now,
                            "created_at": now,
                            "updated_at": now,
                        },
                    )
                )
                .mappings()
                .first()
            )
            created = row is not None
            if row is None:
                row = (
                    (
                        await session.execute(
                            sa.text(
                                "SELECT * FROM jobs WHERE org_id = :org_id "
                                "AND project_id = :project_id "
                                "AND idempotency_key = :idempotency_key"
                            ),
                            {
                                "org_id": str(command.org_id),
                                "project_id": str(command.project_id),
                                "idempotency_key": command.idempotency_key,
                            },
                        )
                    )
                    .mappings()
                    .one()
                )
            else:
                await self._insert_audit(
                    session,
                    org_id=command.org_id,
                    project_id=command.project_id,
                    actor_id=command.actor_id,
                    correlation_id=correlation_id,
                    action=command.audit_action,
                    target_type=command.target_type,
                    target_id=command.target_id,
                    payload={
                        "jobId": str(proposed_job_id),
                        "jobType": command.job_type,
                        "correlationId": str(correlation_id),
                    },
                    occurred_at=now,
                )
            job = await self._record_from_row(session, row)
        return EnqueueResult(job=job, created=created)

    async def list(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        limit: int = 50,
        cursor: UUID | None = None,
    ) -> JobPage:
        if limit < 1 or limit > 100:
            raise ValueError("Job page limit must be between 1 and 100.")
        parameters = {
            "org_id": str(org_id),
            "project_id": str(project_id),
            "cursor_id": str(cursor) if cursor else None,
            "fetch_limit": limit + 1,
        }
        async with session_scope() as session:
            total_count = int(
                (
                    await session.execute(
                        sa.text(
                            "SELECT count(*) FROM jobs WHERE org_id = :org_id "
                            "AND project_id = :project_id"
                        ),
                        parameters,
                    )
                ).scalar_one()
            )
            rows = (
                (
                    await session.execute(
                        sa.text(
                            "SELECT job.* FROM jobs job "
                            "LEFT JOIN jobs cursor_job ON cursor_job.id = :cursor_id "
                            "AND cursor_job.org_id = :org_id "
                            "AND cursor_job.project_id = :project_id "
                            "WHERE job.org_id = :org_id "
                            "AND job.project_id = :project_id "
                            "AND (:cursor_id IS NULL OR ("
                            "cursor_job.id IS NOT NULL AND ("
                            "job.created_at < cursor_job.created_at OR ("
                            "job.created_at = cursor_job.created_at "
                            "AND job.id < cursor_job.id)))) "
                            "ORDER BY job.created_at DESC, job.id DESC "
                            "LIMIT :fetch_limit"
                        ),
                        parameters,
                    )
                )
                .mappings()
                .all()
            )
            has_more = len(rows) > limit
            page_rows = rows[:limit]
            job_ids = tuple(self._uuid(row["id"]) for row in page_rows)
            attempts_by_job = await self._load_attempts_by_job(
                session,
                org_id=org_id,
                project_id=project_id,
                job_ids=job_ids,
            )
            history_by_job = await self._load_history_by_job(
                session,
                org_id=org_id,
                project_id=project_id,
                job_ids=job_ids,
            )
            jobs = tuple(
                self._record_from_row_with_lifecycle(
                    row,
                    attempts=attempts_by_job.get(self._uuid(row["id"]), ()),
                    history=history_by_job.get(self._uuid(row["id"]), ()),
                )
                for row in page_rows
            )
            return JobPage(
                jobs=jobs,
                next_cursor=jobs[-1].job_id if has_more else None,
                total_count=total_count,
            )

    async def get(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        job_id: UUID,
    ) -> JobRecord | None:
        async with session_scope() as session:
            row = await self._get_row(session, org_id, project_id, job_id)
            if row is None:
                return None
            return await self._record_from_row(session, row)

    async def claim(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        job_id: UUID,
        lease_owner: str,
    ) -> JobRecord | None:
        async with session_scope() as session:
            dialect_name = session.get_bind().dialect.name
            clock_sql = database_wall_clock_sql(dialect_name)
            lease_expiry_sql = self._lease_expiry_sql(dialect_name)
            row = (
                (
                    await session.execute(
                        sa.text(
                            f"""
                        UPDATE jobs SET
                            status = 'running', stage = 'running',
                            attempt_count = attempt_count + 1,
                            lease_owner = :lease_owner,
                            lease_expires_at = {lease_expiry_sql},
                            updated_at = {clock_sql}
                        WHERE id = :job_id AND org_id = :org_id
                            AND project_id = :project_id
                            AND status IN ('queued', 'retry_wait')
                            AND available_at <= {clock_sql}
                        RETURNING *
                        """
                        ),
                        {
                            "job_id": str(job_id),
                            "org_id": str(org_id),
                            "project_id": str(project_id),
                            "lease_owner": lease_owner,
                            "lease_seconds": self._lease_seconds,
                        },
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            actor_id = self._required_actor(row)
            await self._insert_attempt_audit(
                session,
                row=row,
                actor_id=actor_id,
                action="job.attempt.started",
                status="running",
                occurred_at=self._datetime(row["updated_at"]),
            )
            return await self._record_from_row(session, row)

    async def renew_lease(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        job_id: UUID,
        attempt_number: int,
        lease_owner: str,
    ) -> JobRecord:
        async with session_scope() as session:
            dialect_name = session.get_bind().dialect.name
            clock_sql = database_wall_clock_sql(dialect_name)
            lease_expiry_sql = self._lease_expiry_sql(dialect_name)
            row = (
                (
                    await session.execute(
                        sa.text(
                            f"""
                        UPDATE jobs SET
                            lease_expires_at = {lease_expiry_sql},
                            updated_at = {clock_sql}
                        WHERE id = :job_id AND org_id = :org_id
                            AND project_id = :project_id AND status = 'running'
                            AND attempt_count = :attempt_number
                            AND lease_owner = :lease_owner
                            AND lease_expires_at > {clock_sql}
                        RETURNING *
                        """
                        ),
                        {
                            "job_id": str(job_id),
                            "org_id": str(org_id),
                            "project_id": str(project_id),
                            "attempt_number": attempt_number,
                            "lease_owner": lease_owner,
                            "lease_seconds": self._lease_seconds,
                        },
                    )
                )
                .mappings()
                .first()
            )
            if row is not None:
                return await self._record_from_row(session, row)
            current = await self._get_row(session, org_id, project_id, job_id)
            if current is None:
                raise JobNotFoundError("Job was not found.")
            raise JobLeaseLostError("Lease renewal does not match the active leased attempt.")

    async def update_progress(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        job_id: UUID,
        attempt_number: int,
        lease_owner: str,
        progress: float,
        stage: str,
    ) -> JobRecord:
        if progress < 0 or progress >= 100:
            raise JobTransitionError("Active job progress must be between 0 and 100.")
        if not stage.strip():
            raise JobTransitionError("Active job progress requires a named stage.")
        async with session_scope() as session:
            clock_sql = database_wall_clock_sql(session.get_bind().dialect.name)
            row = (
                (
                    await session.execute(
                        sa.text(
                            f"""
                        UPDATE jobs SET
                            progress = :progress, stage = :stage, updated_at = {clock_sql}
                        WHERE id = :job_id AND org_id = :org_id
                            AND project_id = :project_id AND status = 'running'
                            AND attempt_count = :attempt_number
                            AND lease_owner = :lease_owner
                            AND lease_expires_at > {clock_sql}
                            AND progress <= :progress
                        RETURNING *
                        """
                        ),
                        {
                            "job_id": str(job_id),
                            "org_id": str(org_id),
                            "project_id": str(project_id),
                            "attempt_number": attempt_number,
                            "lease_owner": lease_owner,
                            "progress": progress,
                            "stage": stage,
                        },
                    )
                )
                .mappings()
                .first()
            )
            if row is not None:
                return await self._record_from_row(session, row)
            current = await self._get_row(session, org_id, project_id, job_id)
            if current is None:
                raise JobNotFoundError("Job was not found.")
            if (
                str(current["status"]) == RunStatus.RUNNING.value
                and int(current["attempt_count"]) == attempt_number
                and str(current["lease_owner"] or "") == lease_owner
                and float(current["progress"]) > progress
            ):
                raise JobTransitionError("Job progress must be monotonic.")
            raise JobTransitionError("Progress update does not match the active leased attempt.")

    async def succeed(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        job_id: UUID,
        attempt_number: int,
        lease_owner: str,
        summary: dict[str, Any],
    ) -> JobRecord:
        async with session_scope() as session:
            clock_sql = database_wall_clock_sql(session.get_bind().dialect.name)
            statement = sa.text(
                f"""
                UPDATE jobs SET
                    status = 'succeeded', stage = 'succeeded', progress = 100,
                    result = :result, error = NULL, lease_owner = NULL,
                    lease_expires_at = NULL, updated_at = {clock_sql}
                WHERE id = :job_id AND org_id = :org_id AND project_id = :project_id
                    AND status = 'running' AND attempt_count = :attempt_number
                    AND lease_owner = :lease_owner
                    AND lease_expires_at > {clock_sql}
                RETURNING *
                """
            ).bindparams(sa.bindparam("result", type_=sa.JSON()))
            row = (
                (
                    await session.execute(
                        statement,
                        {
                            "job_id": str(job_id),
                            "org_id": str(org_id),
                            "project_id": str(project_id),
                            "attempt_number": attempt_number,
                            "lease_owner": lease_owner,
                            "result": summary,
                        },
                    )
                )
                .mappings()
                .first()
            )
            if row is not None:
                await self._insert_attempt_audit(
                    session,
                    row=row,
                    actor_id=self._required_actor(row),
                    action="job.attempt.succeeded",
                    status="succeeded",
                    occurred_at=self._datetime(row["updated_at"]),
                )
                return await self._record_from_row(session, row)
            current = await self._get_row(session, org_id, project_id, job_id)
            if current is None:
                raise JobNotFoundError("Job was not found.")
            return await self._record_from_row(session, current)

    async def fail(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        job_id: UUID,
        attempt_number: int,
        lease_owner: str,
        error: SafeJobError,
    ) -> JobRecord:
        async with session_scope() as session:
            clock_sql = database_wall_clock_sql(session.get_bind().dialect.name)
            row = (
                (
                    await session.execute(
                        sa.text(
                            f"""
                        UPDATE jobs SET
                            status = 'failed', stage = 'failed', error = :error,
                            lease_owner = NULL, lease_expires_at = NULL,
                            updated_at = {clock_sql}
                        WHERE id = :job_id AND org_id = :org_id
                            AND project_id = :project_id
                            AND status = 'running' AND attempt_count = :attempt_number
                            AND lease_owner = :lease_owner
                            AND lease_expires_at > {clock_sql}
                        RETURNING *
                        """
                        ),
                        {
                            "job_id": str(job_id),
                            "org_id": str(org_id),
                            "project_id": str(project_id),
                            "attempt_number": attempt_number,
                            "lease_owner": lease_owner,
                            "error": self._serialize_error(error),
                        },
                    )
                )
                .mappings()
                .first()
            )
            if row is not None:
                await self._insert_attempt_audit(
                    session,
                    row=row,
                    actor_id=self._required_actor(row),
                    action="job.attempt.failed",
                    status="failed",
                    occurred_at=self._datetime(row["updated_at"]),
                    error=error,
                )
                return await self._record_from_row(session, row)
            current = await self._get_row(session, org_id, project_id, job_id)
            if current is None:
                raise JobNotFoundError("Job was not found.")
            return await self._record_from_row(session, current)

    async def retry(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        job_id: UUID,
        actor_id: UUID,
    ) -> JobRecord:
        now = datetime.now(UTC)
        async with session_scope() as session:
            current = await self._get_row(session, org_id, project_id, job_id)
            if current is None:
                raise JobNotFoundError("Job was not found.")
            status = RunStatus(str(current["status"]))
            target = validated_persisted_job_target(
                job_type=str(current["job_type"]),
                payload=self._json_object(current["payload"]) or {},
                fallback_id=job_id,
            )
            if target.type == "legacy_unknown":
                raise JobTransitionError("A job without a typed target cannot be retried.")
            retryable_failure = (
                status is RunStatus.FAILED
                and (error := self._deserialize_error(current["error"])) is not None
                and error.retryable
            )
            cancelled_retryable = status is RunStatus.CANCELLED and str(current["job_type"]) in (
                "detection",
                "selective_rescan",
            )
            if not (retryable_failure or status is RunStatus.MANUAL_RETRY or cancelled_retryable):
                raise JobTransitionError(f"A job in status '{status.value}' cannot be retried.")
            row = (
                (
                    await session.execute(
                        sa.text(
                            """
                        UPDATE jobs SET
                            status = 'queued', stage = 'queued', progress = 0,
                            result = NULL, error = NULL, available_at = :available_at,
                            actor_id = :actor_id,
                            lease_owner = NULL, lease_expires_at = NULL,
                            updated_at = :updated_at
                        WHERE id = :job_id AND org_id = :org_id
                            AND project_id = :project_id
                            AND (
                                status IN ('failed', 'manual_retry')
                                OR (
                                    status = 'cancelled'
                                    AND job_type IN ('detection', 'selective_rescan')
                                )
                            )
                        RETURNING *
                        """
                        ),
                        {
                            "job_id": str(job_id),
                            "org_id": str(org_id),
                            "project_id": str(project_id),
                            "actor_id": str(actor_id),
                            "available_at": now,
                            "updated_at": now,
                        },
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise JobTransitionError("The job changed before it could be retried.")
            await self._insert_audit(
                session,
                org_id=org_id,
                project_id=project_id,
                actor_id=actor_id,
                correlation_id=self._uuid(row["correlation_id"]),
                action="job.retry.requested",
                target_type="job",
                target_id=job_id,
                payload={"jobId": str(job_id), "attemptCount": row["attempt_count"]},
                occurred_at=now,
            )
            return await self._record_from_row(session, row)

    async def cancel(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        job_id: UUID,
        actor_id: UUID,
    ) -> JobRecord:
        now = datetime.now(UTC)
        cancellable = {
            RunStatus.QUEUED,
            RunStatus.CLAIMED,
            RunStatus.RUNNING,
            RunStatus.RETRY_WAIT,
            RunStatus.MANUAL_RETRY,
        }
        async with session_scope() as session:
            current = await self._get_row(session, org_id, project_id, job_id)
            for _attempt in range(3):
                if current is None:
                    raise JobNotFoundError("Job was not found.")
                current_status = RunStatus(str(current["status"]))
                # A succeeded selective rescan awaits accountable human
                # confirmation; an accountable request may cancel it to force a
                # governed re-run. This parity is limited to selective_rescan so
                # other terminal jobs stay non-cancellable.
                stage_scoped_cancellable = cancellable
                if str(current["job_type"]) == "selective_rescan":
                    stage_scoped_cancellable = cancellable | {RunStatus.SUCCEEDED}
                if current_status not in stage_scoped_cancellable:
                    raise JobTransitionError(
                        f"A job in status '{current_status.value}' cannot be cancelled."
                    )
                row = (
                    (
                        await session.execute(
                            sa.text(
                                """
                            UPDATE jobs SET
                                status = 'cancelled', stage = 'cancelled',
                                lease_owner = NULL, lease_expires_at = NULL,
                                updated_at = :updated_at
                            WHERE id = :job_id AND org_id = :org_id
                                AND project_id = :project_id
                                AND status = :expected_status
                            RETURNING *
                            """
                            ),
                            {
                                "job_id": str(job_id),
                                "org_id": str(org_id),
                                "project_id": str(project_id),
                                "expected_status": current_status.value,
                                "updated_at": now,
                            },
                        )
                    )
                    .mappings()
                    .first()
                )
                if row is None:
                    current = await self._get_row(
                        session,
                        org_id,
                        project_id,
                        job_id,
                    )
                    continue
                await self._insert_audit(
                    session,
                    org_id=org_id,
                    project_id=project_id,
                    actor_id=actor_id,
                    correlation_id=self._uuid(row["correlation_id"]),
                    action="job.cancelled",
                    target_type="job",
                    target_id=job_id,
                    payload={
                        "jobId": str(job_id),
                        "previousStatus": current_status.value,
                    },
                    occurred_at=now,
                )
                if current_status in {RunStatus.CLAIMED, RunStatus.RUNNING}:
                    await self._insert_attempt_audit(
                        session,
                        row=row,
                        actor_id=actor_id,
                        action="job.attempt.cancelled",
                        status="cancelled",
                        occurred_at=now,
                    )
                return await self._record_from_row(session, row)
            raise JobTransitionError("The job changed before it could be cancelled.")

    async def recover_interrupted_local_jobs(self) -> tuple[JobRecord, ...]:
        error = SafeJobError(
            code="interrupted",
            message="Local execution was interrupted before completion.",
            retryable=True,
        )
        recovered: list[JobRecord] = []
        async with session_scope() as session:
            clock_sql = database_wall_clock_sql(session.get_bind().dialect.name)
            rows = (
                (
                    await session.execute(
                        sa.text(
                            "SELECT * FROM jobs WHERE status IN ('claimed', 'running') "
                            f"AND (lease_expires_at IS NULL OR lease_expires_at <= {clock_sql}) "
                            "ORDER BY created_at, id LIMIT :recovery_batch_size"
                        ),
                        {"recovery_batch_size": self._recovery_batch_size},
                    )
                )
                .mappings()
                .all()
            )
            for current in rows:
                actor_id = self._uuid(current["actor_id"]) if current["actor_id"] else None
                row = (
                    (
                        await session.execute(
                            sa.text(
                                f"""
                            UPDATE jobs SET
                                status = 'manual_retry', stage = 'interrupted',
                                error = :error, lease_owner = NULL,
                                lease_expires_at = NULL, updated_at = {clock_sql}
                            WHERE id = :job_id AND org_id = :org_id
                                AND project_id = :project_id
                                AND status IN ('claimed', 'running')
                                AND (
                                    lease_expires_at IS NULL
                                    OR lease_expires_at <= {clock_sql}
                                )
                            RETURNING *
                            """
                            ),
                            {
                                "job_id": str(current["id"]),
                                "org_id": str(current["org_id"]),
                                "project_id": str(current["project_id"]),
                                "error": self._serialize_error(error),
                            },
                        )
                    )
                    .mappings()
                    .first()
                )
                if row is None:
                    continue
                if actor_id is not None:
                    await self._insert_attempt_audit(
                        session,
                        row=row,
                        actor_id=actor_id,
                        action="job.attempt.interrupted",
                        status="interrupted",
                        occurred_at=self._datetime(row["updated_at"]),
                        error=error,
                    )
                recovered.append(await self._record_from_row(session, row))
        return tuple(recovered)

    async def _record_from_row(
        self,
        session: AsyncSession,
        row: RowMapping,
    ) -> JobRecord:
        org_id = self._uuid(row["org_id"])
        project_id = self._uuid(row["project_id"])
        job_id = self._uuid(row["id"])
        attempts = await self._load_attempts(
            session,
            org_id=org_id,
            project_id=project_id,
            job_id=job_id,
        )
        history = await self._load_history(
            session,
            org_id=org_id,
            project_id=project_id,
            job_id=job_id,
        )
        return self._record_from_row_with_lifecycle(
            row,
            attempts=attempts,
            history=history,
        )

    def _record_from_row_with_lifecycle(
        self,
        row: RowMapping,
        *,
        attempts: tuple[JobAttempt, ...],
        history: tuple[JobLifecycleEvent, ...],
    ) -> JobRecord:
        payload = self._json_object(row["payload"]) or {}
        return JobRecord(
            job_id=self._uuid(row["id"]),
            org_id=self._uuid(row["org_id"]),
            project_id=self._uuid(row["project_id"]),
            actor_id=self._uuid(row["actor_id"]) if row["actor_id"] else None,
            correlation_id=self._uuid(row["correlation_id"]),
            job_type=str(row["job_type"]),
            target=validated_persisted_job_target(
                job_type=str(row["job_type"]),
                payload=payload,
                fallback_id=self._uuid(row["id"]),
            ),
            status=RunStatus(str(row["status"])),
            idempotency_key=str(row["idempotency_key"]),
            payload=payload,
            progress=float(row["progress"]),
            stage=str(row["stage"]),
            result_summary=self._json_object(row["result"]),
            error=self._deserialize_error(row["error"]),
            attempt_count=int(row["attempt_count"]),
            attempts=attempts,
            history=history,
            available_at=self._datetime(row["available_at"]),
            created_at=self._datetime(row["created_at"]),
            updated_at=self._datetime(row["updated_at"]),
            lease_owner=str(row["lease_owner"]) if row["lease_owner"] else None,
            lease_expires_at=(
                self._datetime(row["lease_expires_at"]) if row["lease_expires_at"] else None
            ),
        )

    async def _load_history_by_job(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        job_ids: tuple[UUID, ...],
    ) -> dict[UUID, tuple[JobLifecycleEvent, ...]]:
        if not job_ids:
            return {}
        job_placeholders = ", ".join(f":job_id_{index}" for index in range(len(job_ids)))
        parameters = {
            "org_id": str(org_id),
            "project_id": str(project_id),
            **{f"job_id_{index}": str(job_id) for index, job_id in enumerate(job_ids)},
        }
        events = (
            (
                await session.execute(
                    sa.text(
                        "SELECT event.target_id, event.action, event.actor_id, "
                        "event.occurred_at FROM authoritative_audit_events event "
                        "JOIN jobs job ON job.id = event.target_id "
                        "AND job.org_id = event.org_id "
                        "AND job.project_id = event.project_id "
                        "WHERE event.org_id = :org_id "
                        "AND event.project_id = :project_id "
                        "AND event.target_type = 'job' "
                        f"AND event.target_id IN ({job_placeholders}) "
                        "AND event.action IN ('job.cancelled', 'job.retry.requested') "
                        "ORDER BY event.target_id, event.occurred_at, event.id"
                    ),
                    parameters,
                )
            )
            .mappings()
            .all()
        )
        grouped: dict[UUID, list[RowMapping]] = {}
        for event in events:
            grouped.setdefault(self._uuid(event["target_id"]), []).append(event)
        return {
            job_id: self._history_from_events(job_events) for job_id, job_events in grouped.items()
        }

    async def _load_attempts_by_job(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        job_ids: tuple[UUID, ...],
    ) -> dict[UUID, tuple[JobAttempt, ...]]:
        if not job_ids:
            return {}
        placeholders = ", ".join(f":action_{index}" for index in range(len(_ATTEMPT_ACTIONS)))
        job_placeholders = ", ".join(f":job_id_{index}" for index in range(len(job_ids)))
        parameters: dict[str, Any] = {
            "org_id": str(org_id),
            "project_id": str(project_id),
        }
        parameters.update(
            {f"action_{index}": action for index, action in enumerate(_ATTEMPT_ACTIONS)}
        )
        parameters.update({f"job_id_{index}": str(job_id) for index, job_id in enumerate(job_ids)})
        events = (
            (
                await session.execute(
                    sa.text(
                        "SELECT event.target_id, event.action, event.payload_redacted, "
                        "event.occurred_at FROM authoritative_audit_events event "
                        "JOIN jobs job ON job.id = event.target_id "
                        "AND job.org_id = event.org_id "
                        "AND job.project_id = event.project_id "
                        "WHERE event.org_id = :org_id "
                        "AND event.project_id = :project_id "
                        "AND event.target_type = 'job' "
                        f"AND event.target_id IN ({job_placeholders}) "
                        f"AND event.action IN ({placeholders}) "
                        "ORDER BY event.target_id, event.occurred_at, event.id"
                    ),
                    parameters,
                )
            )
            .mappings()
            .all()
        )
        grouped: dict[UUID, list[RowMapping]] = {}
        for event in events:
            grouped.setdefault(self._uuid(event["target_id"]), []).append(event)
        return {
            job_id: self._attempts_from_events(job_events) for job_id, job_events in grouped.items()
        }

    async def _load_history(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        job_id: UUID,
    ) -> tuple[JobLifecycleEvent, ...]:
        events = (
            (
                await session.execute(
                    sa.text(
                        "SELECT action, actor_id, occurred_at FROM authoritative_audit_events "
                        "WHERE org_id = :org_id AND project_id = :project_id "
                        "AND target_type = 'job' AND target_id = :job_id "
                        "AND action IN ('job.cancelled', 'job.retry.requested') "
                        "ORDER BY occurred_at, id"
                    ),
                    {
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                        "job_id": str(job_id),
                    },
                )
            )
            .mappings()
            .all()
        )
        return self._history_from_events(events)

    def _history_from_events(
        self,
        events: Sequence[RowMapping],
    ) -> tuple[JobLifecycleEvent, ...]:
        return tuple(
            JobLifecycleEvent(
                action=_LIFECYCLE_ACTIONS[str(event["action"])],
                actor_id=self._uuid(event["actor_id"]),
                occurred_at=self._datetime(event["occurred_at"]),
            )
            for event in events
        )

    async def _load_attempts(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        job_id: UUID,
    ) -> tuple[JobAttempt, ...]:
        placeholders = ", ".join(f":action_{index}" for index in range(len(_ATTEMPT_ACTIONS)))
        parameters: dict[str, Any] = {
            "org_id": str(org_id),
            "project_id": str(project_id),
            "job_id": str(job_id),
        }
        parameters.update(
            {f"action_{index}": action for index, action in enumerate(_ATTEMPT_ACTIONS)}
        )
        events = (
            (
                await session.execute(
                    sa.text(
                        "SELECT action, payload_redacted, occurred_at FROM "
                        "authoritative_audit_events WHERE org_id = :org_id "
                        "AND project_id = :project_id AND target_type = 'job' "
                        f"AND target_id = :job_id AND action IN ({placeholders}) "
                        "ORDER BY occurred_at, id"
                    ),
                    parameters,
                )
            )
            .mappings()
            .all()
        )
        return self._attempts_from_events(events)

    def _attempts_from_events(
        self,
        events: Sequence[RowMapping],
    ) -> tuple[JobAttempt, ...]:
        attempts: dict[int, dict[str, Any]] = {}
        for event in events:
            payload = self._json_object(event["payload_redacted"]) or {}
            number = int(payload.get("attemptNumber", 0))
            if number <= 0:
                continue
            occurred_at = self._datetime(event["occurred_at"])
            attempt = attempts.setdefault(
                number,
                {
                    "status": "running",
                    "started_at": occurred_at,
                    "completed_at": None,
                    "error": None,
                },
            )
            if event["action"] == "job.attempt.started":
                attempt["started_at"] = occurred_at
                attempt["status"] = "running"
            else:
                attempt["status"] = str(payload.get("status", "failed"))
                attempt["completed_at"] = occurred_at
                attempt["error"] = self._error_from_object(payload.get("error"))
        return tuple(
            JobAttempt(
                number=number,
                status=str(values["status"]),
                started_at=values["started_at"],
                completed_at=values["completed_at"],
                error=values["error"],
            )
            for number, values in sorted(attempts.items())
        )

    async def _get_row(
        self,
        session: AsyncSession,
        org_id: UUID,
        project_id: UUID,
        job_id: UUID,
    ) -> RowMapping | None:
        return (
            (
                await session.execute(
                    sa.text(
                        "SELECT * FROM jobs WHERE id = :job_id AND org_id = :org_id "
                        "AND project_id = :project_id"
                    ),
                    {
                        "job_id": str(job_id),
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                    },
                )
            )
            .mappings()
            .first()
        )

    async def _insert_attempt_audit(
        self,
        session: AsyncSession,
        *,
        row: RowMapping,
        actor_id: UUID,
        action: str,
        status: str,
        occurred_at: datetime,
        error: SafeJobError | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "jobId": str(row["id"]),
            "attemptNumber": int(row["attempt_count"]),
            "status": status,
        }
        if error is not None:
            payload["error"] = asdict(error)
        await self._insert_audit(
            session,
            org_id=self._uuid(row["org_id"]),
            project_id=self._uuid(row["project_id"]),
            actor_id=actor_id,
            correlation_id=self._uuid(row["correlation_id"]),
            action=action,
            target_type="job",
            target_id=self._uuid(row["id"]),
            payload=payload,
            occurred_at=occurred_at,
        )

    async def _insert_audit(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        actor_id: UUID,
        correlation_id: UUID,
        action: str,
        target_type: str,
        target_id: UUID,
        payload: dict[str, Any],
        occurred_at: datetime,
    ) -> None:
        statement = sa.text(
            """
            INSERT INTO authoritative_audit_events (
                id, org_id, project_id, actor_id, action, target_type,
                target_id, payload_redacted, occurred_at, correlation_id
            ) VALUES (
                :id, :org_id, :project_id, :actor_id, :action, :target_type,
                :target_id, :payload, :occurred_at, :correlation_id
            )
            """
        ).bindparams(sa.bindparam("payload", type_=sa.JSON()))
        await session.execute(
            statement,
            {
                "id": str(uuid6.uuid7()),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "actor_id": str(actor_id),
                "action": action,
                "target_type": target_type,
                "target_id": str(target_id),
                "payload": payload,
                "occurred_at": occurred_at,
                "correlation_id": str(correlation_id),
            },
        )

    @staticmethod
    def _required_actor(row: RowMapping) -> UUID:
        if not row["actor_id"]:
            raise JobTransitionError("The job has no accountable actor.")
        return UUID(str(row["actor_id"]))

    @staticmethod
    def _uuid(value: Any) -> UUID:
        return value if isinstance(value, UUID) else UUID(str(value))

    @staticmethod
    def _datetime(value: Any) -> datetime:
        if isinstance(value, datetime):
            result = value
        else:
            result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if result.tzinfo is None:
            return result.replace(tzinfo=UTC)
        return result

    @staticmethod
    def _json_object(value: Any) -> dict[str, Any] | None:
        if value is None:
            return None
        try:
            parsed = json.loads(value) if isinstance(value, str) else value
        except (TypeError, json.JSONDecodeError):
            return None
        if not isinstance(parsed, dict):
            return None
        return dict(parsed)

    @staticmethod
    def _lease_expiry_sql(dialect_name: str) -> str:
        if dialect_name == "postgresql":
            return "clock_timestamp() + (:lease_seconds * INTERVAL '1 second')"
        if dialect_name == "sqlite":
            return "STRFTIME('%Y-%m-%d %H:%M:%f', 'now', '+' || :lease_seconds || ' seconds')"
        raise RuntimeError(f"Unsupported database dialect for job leases: {dialect_name}")

    @staticmethod
    def _serialize_error(error: SafeJobError) -> str:
        return json.dumps(asdict(error), sort_keys=True)

    @classmethod
    def _deserialize_error(cls, value: Any) -> SafeJobError | None:
        if value is None:
            return None
        try:
            parsed = json.loads(str(value))
        except (TypeError, json.JSONDecodeError):
            return SafeJobError(
                code="job_failed",
                message="The job failed.",
                retryable=False,
            )
        return cls._error_from_object(parsed)

    @staticmethod
    def _error_from_object(value: Any) -> SafeJobError | None:
        if not isinstance(value, dict):
            return None
        code = value.get("code")
        message = value.get("message")
        retryable = value.get("retryable")
        if not isinstance(code, str) or not isinstance(message, str):
            return None
        return SafeJobError(
            code=code,
            message=message,
            retryable=bool(retryable),
        )

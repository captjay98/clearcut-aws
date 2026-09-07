"""Durable dispatch reconciliation and expired lease recovery."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from clearcut.database import session_scope
from clearcut.operations.ports.job_dispatcher import (
    DispatchOutboxPort,
    DispatchReceipt,
    DispatchStatus,
    JobDispatchRequest,
    ReconciliationResult,
    TaskClientPort,
)
from clearcut.operations.ports.job_repository import JobRepositoryPort

logger = logging.getLogger(__name__)


class SqlDispatchOutbox(DispatchOutboxPort):
    def __init__(self, *, repository: JobRepositoryPort | None = None) -> None:
        self._repository = repository

    async def pending_dispatches(self, *, limit: int = 100) -> tuple[JobDispatchRequest, ...]:
        now = datetime.now(UTC)
        query = sa.text(
            """
            SELECT id, org_id, project_id, available_at, attempt_count
            FROM jobs
            WHERE status = 'queued' AND available_at <= :now AND lease_owner IS NULL
            ORDER BY available_at ASC, id ASC
            LIMIT :limit
            """
        )
        async with session_scope() as session:
            result = await session.execute(query, {"now": now, "limit": limit})
            rows = result.mappings().all()

        return tuple(
            JobDispatchRequest(
                org_id=UUID(str(row["org_id"])),
                project_id=UUID(str(row["project_id"])),
                job_id=UUID(str(row["id"])),
                available_at=row["available_at"]
                if isinstance(row["available_at"], datetime)
                else datetime.fromisoformat(str(row["available_at"])),
                attempt_count=int(row["attempt_count"]),
            )
            for row in rows
        )

    async def confirm_dispatch(self, command: JobDispatchRequest) -> DispatchReceipt:
        return DispatchReceipt(status=DispatchStatus.CONFIRMED)


class InMemoryDispatchOutbox(DispatchOutboxPort):
    def __init__(self, pending: list[JobDispatchRequest] | None = None) -> None:
        self._pending = list(pending or [])
        self.confirmed: list[JobDispatchRequest] = []

    async def pending_dispatches(self, *, limit: int = 100) -> tuple[JobDispatchRequest, ...]:
        return tuple(self._pending[:limit])

    async def confirm_dispatch(self, command: JobDispatchRequest) -> DispatchReceipt:
        self.confirmed.append(command)
        if command in self._pending:
            self._pending.remove(command)
        return DispatchReceipt(status=DispatchStatus.CONFIRMED)


class ReconcileJobsService:
    def __init__(
        self,
        *,
        outbox: DispatchOutboxPort,
        client: TaskClientPort,
        repository: JobRepositoryPort,
        batch_limit: int = 100,
    ) -> None:
        self._outbox = outbox
        self._client = client
        self._repository = repository
        self._batch_limit = batch_limit

    async def reconcile(self) -> ReconciliationResult:
        dispatched_count = 0
        failed_count = 0

        pending = await self._outbox.pending_dispatches(limit=self._batch_limit)
        for command in pending:
            try:
                receipt = await self._client.create_task(command)
                if receipt.status in {DispatchStatus.CONFIRMED, DispatchStatus.ALREADY_EXISTS}:
                    await self._outbox.confirm_dispatch(command)
                    dispatched_count += 1
            except Exception:
                logger.exception(
                    "Reconciliation failed to dispatch task for job_id=%s org_id=%s project_id=%s",
                    command.job_id,
                    command.org_id,
                    command.project_id,
                )
                failed_count += 1

        recovered = await self._repository.recover_interrupted_local_jobs()
        recovered_count = len(recovered)

        return ReconciliationResult(
            dispatched_count=dispatched_count,
            recovered_count=recovered_count,
            failed_count=failed_count,
        )

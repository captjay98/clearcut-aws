from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from clearcut.operations.domain.jobs import RunStatus
from clearcut.operations.ports.job_repository import (
    JobLeaseLostError,
    JobRecord,
    JobRepositoryPort,
    SafeJobError,
)


@dataclass(frozen=True)
class JobExecutionResult:
    summary: dict[str, Any]


class JobExecutionError(RuntimeError):
    def __init__(self, error: SafeJobError) -> None:
        super().__init__(error.message)
        self.error = error


JobProcessor = Callable[[JobRecord], Awaitable[JobExecutionResult]]


class RunJobService:
    def __init__(
        self,
        *,
        repository: JobRepositoryPort,
        processors: Mapping[str, JobProcessor],
        lease_owner: str,
        heartbeat_interval_seconds: float = 300.0,
    ) -> None:
        if heartbeat_interval_seconds <= 0:
            raise ValueError("Job heartbeat interval must be positive.")
        self._repository = repository
        self._processors = dict(processors)
        self._lease_owner = lease_owner
        self._heartbeat_interval_seconds = heartbeat_interval_seconds

    @property
    def configured_job_types(self) -> frozenset[str]:
        return frozenset(self._processors)

    async def run(
        self,
        job_id: UUID,
        org_id: UUID,
        project_id: UUID,
    ) -> JobRecord:
        claimed = await self._repository.claim(
            org_id=org_id,
            project_id=project_id,
            job_id=job_id,
            lease_owner=self._lease_owner,
        )
        if claimed is None:
            existing = await self._repository.get(
                org_id=org_id,
                project_id=project_id,
                job_id=job_id,
            )
            if existing is None:
                raise RuntimeError("Dispatched job was not found in its tenant scope.")
            return existing

        processor = self._processors.get(claimed.job_type)
        if processor is None:
            failed = await self._repository.fail(
                org_id=org_id,
                project_id=project_id,
                job_id=job_id,
                attempt_number=claimed.attempt_count,
                lease_owner=self._lease_owner,
                error=SafeJobError(
                    code="processor_unavailable",
                    message=(f"No processor is configured for job type '{claimed.job_type}'."),
                    retryable=False,
                ),
            )
            return self._terminal_result_or_raise(failed, expected=RunStatus.FAILED)

        try:
            result = await self._run_with_heartbeat(processor, claimed)
        except JobLeaseLostError:
            raise
        except JobExecutionError as failure:
            failed = await self._repository.fail(
                org_id=org_id,
                project_id=project_id,
                job_id=job_id,
                attempt_number=claimed.attempt_count,
                lease_owner=self._lease_owner,
                error=failure.error,
            )
            return self._terminal_result_or_raise(failed, expected=RunStatus.FAILED)
        except Exception:
            # The typed SafeJobError deliberately carries no internal detail, so
            # log the real traceback here or an unexpected failure is undiagnosable.
            logging.getLogger(__name__).exception(
                "Job execution raised an unhandled exception: job_id=%s job_type=%s "
                "org_id=%s project_id=%s",
                job_id,
                getattr(claimed, "job_type", None),
                org_id,
                project_id,
            )
            failed = await self._repository.fail(
                org_id=org_id,
                project_id=project_id,
                job_id=job_id,
                attempt_number=claimed.attempt_count,
                lease_owner=self._lease_owner,
                error=SafeJobError(
                    code="execution_failed",
                    message="Job execution failed unexpectedly.",
                    retryable=True,
                ),
            )
            return self._terminal_result_or_raise(failed, expected=RunStatus.FAILED)

        completed = await self._repository.succeed(
            org_id=org_id,
            project_id=project_id,
            job_id=job_id,
            attempt_number=claimed.attempt_count,
            lease_owner=self._lease_owner,
            summary=result.summary,
        )
        return self._terminal_result_or_raise(completed, expected=RunStatus.SUCCEEDED)

    async def _run_with_heartbeat(
        self,
        processor: JobProcessor,
        claimed: JobRecord,
    ) -> JobExecutionResult:
        processor_task = asyncio.create_task(
            self._invoke_processor(processor, claimed),
            name=f"job-processor:{claimed.job_id}:{claimed.attempt_count}",
        )
        heartbeat_task = asyncio.create_task(
            self._maintain_lease(claimed),
            name=f"job-heartbeat:{claimed.job_id}:{claimed.attempt_count}",
        )
        try:
            done, _pending = await asyncio.wait(
                {processor_task, heartbeat_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if heartbeat_task in done:
                heartbeat_task.result()
                raise JobLeaseLostError(
                    "Lease heartbeat stopped before the active leased attempt completed."
                )
            return await processor_task
        finally:
            for task in (heartbeat_task, processor_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(heartbeat_task, processor_task, return_exceptions=True)

    @staticmethod
    async def _invoke_processor(
        processor: JobProcessor,
        claimed: JobRecord,
    ) -> JobExecutionResult:
        return await processor(claimed)

    async def _maintain_lease(self, claimed: JobRecord) -> None:
        while True:
            await asyncio.sleep(self._heartbeat_interval_seconds)
            await self._repository.renew_lease(
                org_id=claimed.org_id,
                project_id=claimed.project_id,
                job_id=claimed.job_id,
                attempt_number=claimed.attempt_count,
                lease_owner=self._lease_owner,
            )

    @staticmethod
    def _terminal_result_or_raise(
        result: JobRecord,
        *,
        expected: RunStatus,
    ) -> JobRecord:
        if result.status is expected:
            return result
        if result.status is RunStatus.RUNNING:
            raise JobLeaseLostError("Terminal update does not match the active leased attempt.")
        return result

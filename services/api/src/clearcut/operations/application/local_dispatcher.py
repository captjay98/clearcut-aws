"""Non-durable single-process FastAPI background job dispatch."""

from __future__ import annotations

import logging
import os
from uuid import UUID

from clearcut.operations.application.run_job import RunJobService
from clearcut.operations.ports.job_repository import JobLeaseLostError, JobRecord
from fastapi import BackgroundTasks

logger = logging.getLogger(__name__)


class LocalDispatchConfigurationError(RuntimeError):
    pass


class LocalJobDispatcher:
    durable = False

    def __init__(
        self,
        *,
        runner: RunJobService,
        mode: str,
        worker_count: int | None,
    ) -> None:
        self.validate_configuration(mode=mode, worker_count=worker_count)
        self._runner = runner
        self.mode = mode

    @classmethod
    def from_environment(cls, *, runner: RunJobService) -> LocalJobDispatcher:
        mode = os.getenv("CLEARCUT_JOB_DISPATCH_MODE", "disabled").strip().lower()
        configured_workers: dict[str, int] = {}
        for variable in ("CLEARCUT_API_WORKERS", "WEB_CONCURRENCY"):
            value = os.getenv(variable)
            if value is None or not value.strip():
                continue
            try:
                configured_workers[variable] = int(value)
            except ValueError as error:
                raise LocalDispatchConfigurationError(f"{variable} must be an integer.") from error
        if len(set(configured_workers.values())) > 1:
            raise LocalDispatchConfigurationError(
                "CLEARCUT_API_WORKERS and WEB_CONCURRENCY must match when both are set."
            )
        worker_count = next(iter(configured_workers.values()), None)
        return cls(runner=runner, mode=mode, worker_count=worker_count)

    @staticmethod
    def validate_configuration(*, mode: str, worker_count: int | None) -> None:
        if mode not in {"disabled", "local"}:
            raise LocalDispatchConfigurationError(
                "CLEARCUT_JOB_DISPATCH_MODE must be 'disabled' or 'local'."
            )
        if mode == "local" and worker_count != 1:
            raise LocalDispatchConfigurationError(
                "Local job dispatch requires exactly one worker; set CLEARCUT_API_WORKERS=1."
            )

    def dispatch(self, background_tasks: BackgroundTasks, job: JobRecord) -> None:
        if self.mode != "local":
            return
        background_tasks.add_task(
            self._run_safely,
            job.job_id,
            job.org_id,
            job.project_id,
        )

    def dispatch_identifiers(
        self,
        background_tasks: BackgroundTasks,
        *,
        job_id: UUID,
        org_id: UUID,
        project_id: UUID,
    ) -> None:
        if self.mode != "local":
            return
        background_tasks.add_task(self._run_safely, job_id, org_id, project_id)

    async def _run_safely(
        self,
        job_id: UUID,
        org_id: UUID,
        project_id: UUID,
    ) -> None:
        try:
            await self._runner.run(job_id, org_id, project_id)
        except JobLeaseLostError:
            logger.info(
                "Local job attempt lost its lease after dispatch: job_id=%s org_id=%s "
                "project_id=%s",
                job_id,
                org_id,
                project_id,
            )

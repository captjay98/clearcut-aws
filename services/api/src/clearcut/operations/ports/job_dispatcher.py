"""Typed scheduling and Cloud Tasks delivery boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from clearcut.operations.ports.job_repository import JobRecord
from fastapi import BackgroundTasks


class DispatchStatus(StrEnum):
    SCHEDULED = "scheduled"
    DISABLED = "disabled"
    CONFIRMED = "confirmed"
    ALREADY_EXISTS = "already_exists"


@dataclass(frozen=True)
class DispatchReceipt:
    status: DispatchStatus
    task_name: str | None = None


@dataclass(frozen=True)
class JobDispatchRequest:
    org_id: UUID
    project_id: UUID
    job_id: UUID
    available_at: datetime
    attempt_count: int

    @classmethod
    def from_job(cls, job: JobRecord) -> JobDispatchRequest:
        return cls(job.org_id, job.project_id, job.job_id, job.available_at, job.attempt_count)


class JobDispatchError(RuntimeError):
    """Delivery was not confirmed; durable intent must remain pending."""


class JobDispatcherPort(Protocol):
    mode: str
    durable: bool

    def dispatch(self, background_tasks: BackgroundTasks, job: JobRecord) -> DispatchReceipt: ...


class TaskClientPort(Protocol):
    async def create_task(self, command: JobDispatchRequest) -> DispatchReceipt: ...


class DispatchOutboxPort(Protocol):
    async def pending_dispatches(self, *, limit: int = 100) -> tuple[JobDispatchRequest, ...]: ...

    async def confirm_dispatch(self, command: JobDispatchRequest) -> DispatchReceipt: ...


class AccessTokenPort(Protocol):
    async def authorization(self) -> str: ...


class TokenVerifierPort(Protocol):
    def verify_token(self, token: str, *, audience: str) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ReconciliationResult:
    dispatched_count: int
    recovered_count: int
    failed_count: int

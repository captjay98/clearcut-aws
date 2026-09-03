"""Typed persistence boundary for observable job lifecycles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from clearcut.operations.domain.jobs import RunStatus


@dataclass(frozen=True)
class SafeJobError:
    code: str
    message: str
    retryable: bool


@dataclass(frozen=True)
class JobAttempt:
    number: int
    status: str
    started_at: datetime
    completed_at: datetime | None
    error: SafeJobError | None


@dataclass(frozen=True)
class JobLifecycleEvent:
    action: str
    actor_id: UUID
    occurred_at: datetime


@dataclass(frozen=True)
class JobTarget:
    type: str
    id: UUID


_EXPECTED_TARGET_TYPE_BY_JOB_TYPE = {
    "detection": "script_version",
    "research": "clearance_item",
    "test": "project",
}
_SUPPORTED_JOB_PAYLOAD_SCHEMA_VERSION = 1


def validated_persisted_job_target(
    *,
    job_type: str,
    payload: dict[str, Any],
    fallback_id: UUID,
) -> JobTarget:
    """Project only fully validated, versioned job payloads into public targets."""
    legacy = JobTarget(type="legacy_unknown", id=fallback_id)
    expected_target_type = _EXPECTED_TARGET_TYPE_BY_JOB_TYPE.get(job_type)
    if expected_target_type is None or set(payload) != {"schemaVersion", "target"}:
        return legacy
    schema_version = payload["schemaVersion"]
    if type(schema_version) is not int or schema_version != _SUPPORTED_JOB_PAYLOAD_SCHEMA_VERSION:
        return legacy
    target = payload["target"]
    if not isinstance(target, dict) or set(target) != {"type", "id"}:
        return legacy
    if target["type"] != expected_target_type or not isinstance(target["id"], str):
        return legacy
    try:
        target_id = UUID(target["id"])
    except ValueError:
        return legacy
    return JobTarget(type=expected_target_type, id=target_id)


@dataclass(frozen=True)
class JobRecord:
    job_id: UUID
    org_id: UUID
    project_id: UUID
    actor_id: UUID | None
    correlation_id: UUID
    job_type: str
    target: JobTarget
    status: RunStatus
    idempotency_key: str
    payload: dict[str, Any]
    progress: float
    stage: str
    result_summary: dict[str, Any] | None
    error: SafeJobError | None
    attempt_count: int
    attempts: tuple[JobAttempt, ...]
    history: tuple[JobLifecycleEvent, ...]
    available_at: datetime
    created_at: datetime
    updated_at: datetime
    lease_owner: str | None
    lease_expires_at: datetime | None


@dataclass(frozen=True)
class JobPage:
    jobs: tuple[JobRecord, ...]
    next_cursor: UUID | None
    total_count: int


@dataclass(frozen=True)
class EnqueueJob:
    org_id: UUID
    project_id: UUID
    actor_id: UUID
    job_type: str
    idempotency_key: str
    payload: dict[str, Any]
    audit_action: str
    target_type: str
    target_id: UUID


@dataclass(frozen=True)
class EnqueueResult:
    job: JobRecord
    created: bool


class JobNotFoundError(RuntimeError):
    pass


class JobTransitionError(RuntimeError):
    pass


class JobLeaseLostError(JobTransitionError):
    """The caller no longer owns the active leased job attempt."""


class JobRepositoryPort(Protocol):
    async def enqueue(self, command: EnqueueJob) -> EnqueueResult: ...

    async def list(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        limit: int = 50,
        cursor: UUID | None = None,
    ) -> JobPage: ...

    async def get(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        job_id: UUID,
    ) -> JobRecord | None: ...

    async def claim(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        job_id: UUID,
        lease_owner: str,
    ) -> JobRecord | None: ...

    async def renew_lease(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        job_id: UUID,
        attempt_number: int,
        lease_owner: str,
    ) -> JobRecord: ...

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
    ) -> JobRecord: ...

    async def succeed(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        job_id: UUID,
        attempt_number: int,
        lease_owner: str,
        summary: dict[str, Any],
    ) -> JobRecord: ...

    async def fail(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        job_id: UUID,
        attempt_number: int,
        lease_owner: str,
        error: SafeJobError,
    ) -> JobRecord: ...

    async def retry(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        job_id: UUID,
        actor_id: UUID,
    ) -> JobRecord: ...

    async def cancel(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        job_id: UUID,
        actor_id: UUID,
    ) -> JobRecord: ...

    async def recover_interrupted_local_jobs(self) -> tuple[JobRecord, ...]: ...

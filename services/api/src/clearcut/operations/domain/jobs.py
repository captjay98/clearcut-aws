from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

import uuid6


class RunStatus(StrEnum):
    QUEUED = "queued"
    CLAIMED = "claimed"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    MANUAL_RETRY = "manual_retry"
    CANCELLED = "cancelled"


@dataclass
class Job:
    job_id: UUID
    org_id: UUID
    project_id: UUID
    job_type: str
    status: RunStatus
    idempotency_key: str
    payload: dict[str, Any]
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime = datetime.now(UTC)
    available_at: datetime = datetime.now(UTC)
    lease_expires_at: datetime | None = None

    @classmethod
    def create(
        cls,
        org_id: UUID,
        project_id: UUID,
        job_type: str,
        idempotency_key: str,
        payload: dict[str, Any],
    ) -> "Job":
        now = datetime.now(UTC)
        return cls(
            job_id=uuid6.uuid7(),
            org_id=org_id,
            project_id=project_id,
            job_type=job_type,
            status=RunStatus.QUEUED,
            idempotency_key=idempotency_key,
            payload=payload,
            result=None,
            error=None,
            created_at=now,
            available_at=now,
            lease_expires_at=None,
        )

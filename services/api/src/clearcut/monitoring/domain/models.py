from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

import uuid6


class WatchCadence(StrEnum):
    OFF = "off"
    MANUAL = "manual"
    DAILY = "daily"
    WEEKLY = "weekly"


class WatchKind(StrEnum):
    EXACT_SOURCE = "exact_source"
    NEW_EVENT_TOPIC = "new_event_topic"


class ProviderMonitorState(StrEnum):
    DISABLED = "disabled"
    PENDING = "pending"
    ACTIVE = "active"
    DEGRADED = "degraded"
    CANCELLED = "cancelled"


class MonitoringRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class WatchConfig:
    watch_id: UUID
    org_id: UUID
    project_id: UUID
    item_id: UUID
    cadence: WatchCadence
    watch_kind: WatchKind
    target_url: str | None = None
    query_text: str | None = None
    created_at: datetime = datetime.now(UTC)

    @classmethod
    def create(
        cls,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        cadence: WatchCadence = WatchCadence.DAILY,
        watch_kind: WatchKind = WatchKind.EXACT_SOURCE,
        target_url: str | None = None,
        query_text: str | None = None,
    ) -> "WatchConfig":
        return cls(
            watch_id=uuid6.uuid7(),
            org_id=org_id,
            project_id=project_id,
            item_id=item_id,
            cadence=cadence,
            watch_kind=watch_kind,
            target_url=target_url,
            query_text=query_text,
            created_at=datetime.now(UTC),
        )


@dataclass(frozen=True)
class MonitoringRun:
    run_id: UUID
    watch_id: UUID
    org_id: UUID
    project_id: UUID
    status: MonitoringRunStatus
    new_snapshot_id: UUID | None = None
    error_message: str | None = None
    created_at: datetime = datetime.now(UTC)

    @classmethod
    def create(
        cls,
        watch_id: UUID,
        org_id: UUID,
        project_id: UUID,
        status: MonitoringRunStatus = MonitoringRunStatus.PENDING,
        new_snapshot_id: UUID | None = None,
        error_message: str | None = None,
    ) -> "MonitoringRun":
        return cls(
            run_id=uuid6.uuid7(),
            watch_id=watch_id,
            org_id=org_id,
            project_id=project_id,
            status=status,
            new_snapshot_id=new_snapshot_id,
            error_message=error_message,
            created_at=datetime.now(UTC),
        )

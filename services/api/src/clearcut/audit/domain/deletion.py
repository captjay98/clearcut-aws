from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID

import uuid6


class DeletionState(StrEnum):
    ACTIVE = "active"
    GRACE_PERIOD = "grace_period"
    PURGED = "purged"


@dataclass(frozen=True)
class OrganizationDeletionSchedule:
    schedule_id: UUID
    org_id: UUID
    scheduled_by: UUID
    grace_ends_at: datetime
    state: DeletionState
    created_at: datetime = datetime.now(UTC)

    @classmethod
    def schedule(
        cls,
        org_id: UUID,
        scheduled_by: UUID,
    ) -> "OrganizationDeletionSchedule":
        return cls(
            schedule_id=uuid6.uuid7(),
            org_id=org_id,
            scheduled_by=scheduled_by,
            grace_ends_at=datetime.now(UTC) + timedelta(days=30),
            state=DeletionState.GRACE_PERIOD,
            created_at=datetime.now(UTC),
        )

    def restore(self) -> "OrganizationDeletionSchedule":
        return OrganizationDeletionSchedule(
            schedule_id=self.schedule_id,
            org_id=self.org_id,
            scheduled_by=self.scheduled_by,
            grace_ends_at=self.grace_ends_at,
            state=DeletionState.ACTIVE,
            created_at=self.created_at,
        )


@dataclass(frozen=True)
class DeletionTombstone:
    tombstone_id: UUID
    org_id: UUID
    state: DeletionState
    reproducibility_loss_recorded: bool
    purged_at: datetime = datetime.now(UTC)

    @classmethod
    def create(cls, org_id: UUID) -> "DeletionTombstone":
        return cls(
            tombstone_id=uuid6.uuid7(),
            org_id=org_id,
            state=DeletionState.PURGED,
            reproducibility_loss_recorded=True,
            purged_at=datetime.now(UTC),
        )

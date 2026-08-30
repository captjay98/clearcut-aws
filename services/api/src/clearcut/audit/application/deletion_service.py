from uuid import UUID

from clearcut.audit.domain.deletion import (
    DeletionTombstone,
    OrganizationDeletionSchedule,
)
from clearcut.organizations.domain.capabilities import Role, has_capability


class DeletionService:
    def __init__(self) -> None:
        self.schedules: dict[UUID, OrganizationDeletionSchedule] = {}
        self.tombstones: dict[UUID, DeletionTombstone] = {}

    async def schedule_org_deletion(
        self,
        org_id: UUID,
        actor_id: UUID,
        actor_role: Role,
    ) -> OrganizationDeletionSchedule:
        if not has_capability(actor_role, "org:delete"):
            raise PermissionError("Only organization Owners may schedule organization deletion.")

        schedule = OrganizationDeletionSchedule.schedule(org_id=org_id, scheduled_by=actor_id)
        self.schedules[org_id] = schedule
        return schedule

    async def restore_org_deletion(
        self,
        org_id: UUID,
        actor_id: UUID,
        actor_role: Role,
    ) -> OrganizationDeletionSchedule:
        if not has_capability(actor_role, "org:delete"):
            raise PermissionError("Only organization Owners may restore scheduled deletion.")

        schedule = self.schedules.get(org_id)
        if not schedule:
            raise ValueError(f"No deletion schedule found for organization {org_id}")

        restored = schedule.restore()
        self.schedules[org_id] = restored
        return restored

    async def purge_organization(self, org_id: UUID) -> DeletionTombstone:
        tombstone = DeletionTombstone.create(org_id=org_id)
        self.tombstones[org_id] = tombstone
        return tombstone

from uuid import UUID

from clearcut.organizations.domain.capabilities import Role, has_capability
from clearcut.organizations.domain.models import Membership, coerce_role_type
from clearcut.organizations.ports.organization_repository import (
    OrganizationRepositoryPort,
)


class MembershipService:
    def __init__(self, repository: OrganizationRepositoryPort) -> None:
        self.repository = repository

    async def change_membership_role(
        self,
        org_id: UUID,
        actor_id: UUID,
        target_membership_id: UUID,
        new_role: str,
    ) -> Membership:
        actor_membership = await self.repository.get_membership(org_id, actor_id)
        if not actor_membership or not has_capability(actor_membership.role, "member:manage"):
            raise PermissionError("Actor lacks member:manage capability")

        target_m = await self.repository.get_membership_by_id(target_membership_id)
        if not target_m or target_m.org_id != org_id:
            raise ValueError("Target membership not found in organization")

        # Final-Owner protection
        if target_m.role == Role.OWNER and new_role != Role.OWNER:
            active_owners = await self.repository.count_active_owners(org_id)
            if active_owners <= 1:
                raise ValueError("Cannot change role of the only active Owner")

        target_m.role = coerce_role_type(new_role)
        await self.repository.save_membership(target_m)
        return target_m

    async def deactivate_membership(
        self,
        org_id: UUID,
        actor_id: UUID,
        target_membership_id: UUID,
    ) -> Membership:
        actor_membership = await self.repository.get_membership(org_id, actor_id)
        if not actor_membership or not has_capability(actor_membership.role, "member:manage"):
            raise PermissionError("Actor lacks member:manage capability")

        target_m = await self.repository.get_membership_by_id(target_membership_id)
        if not target_m or target_m.org_id != org_id:
            raise ValueError("Target membership not found in organization")

        # Final-Owner protection
        if target_m.role == Role.OWNER:
            active_owners = await self.repository.count_active_owners(org_id)
            if active_owners <= 1:
                raise ValueError("Cannot deactivate the only active Owner")

        target_m.status = "deactivated"
        await self.repository.save_membership(target_m)
        return target_m

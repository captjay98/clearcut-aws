import pytest
import uuid6
from clearcut.organizations.adapters.in_memory import InMemoryOrganizationRepository
from clearcut.organizations.application.membership_service import MembershipService
from clearcut.organizations.domain.models import Membership


@pytest.mark.asyncio
async def test_final_owner_protection_prevents_deactivation():
    repo = InMemoryOrganizationRepository()
    service = MembershipService(repository=repo)

    org_id = uuid6.uuid7()
    owner_user = uuid6.uuid7()

    # Create single Owner membership
    owner_m = Membership.create_owner(org_id=org_id, user_id=owner_user)
    await repo.save_membership(owner_m)

    # Attempting to deactivate the only owner must fail
    with pytest.raises(ValueError, match="Cannot deactivate the only active Owner"):
        await service.deactivate_membership(
            org_id=org_id,
            actor_id=owner_user,
            target_membership_id=owner_m.membership_id,
        )


@pytest.mark.asyncio
async def test_final_owner_protection_prevents_demoting_last_owner():
    repo = InMemoryOrganizationRepository()
    service = MembershipService(repository=repo)

    org_id = uuid6.uuid7()
    owner_user = uuid6.uuid7()

    owner_m = Membership.create_owner(org_id=org_id, user_id=owner_user)
    await repo.save_membership(owner_m)

    # Attempting to change role to editor must fail
    with pytest.raises(ValueError, match="Cannot change role of the only active Owner"):
        await service.change_membership_role(
            org_id=org_id,
            actor_id=owner_user,
            target_membership_id=owner_m.membership_id,
            new_role="editor",
        )

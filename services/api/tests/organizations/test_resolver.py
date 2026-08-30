import pytest
import uuid6
from clearcut.organizations.adapters.in_memory import InMemoryOrganizationRepository
from clearcut.organizations.application.bootstrap import OrganizationBootstrapService


@pytest.mark.asyncio
async def test_resolve_entry_zero_memberships():
    repo = InMemoryOrganizationRepository()
    service = OrganizationBootstrapService(repository=repo)
    user_id = uuid6.uuid7()

    entry = await service.resolve_entry(user_id=user_id)
    assert entry.destination == "onboarding"
    assert len(entry.organizations) == 0


@pytest.mark.asyncio
async def test_resolve_entry_single_active_membership():
    repo = InMemoryOrganizationRepository()
    service = OrganizationBootstrapService(repository=repo)
    user_id = uuid6.uuid7()

    org, _ = await service.bootstrap_organization(
        user_id=user_id,
        name="Solo Film",
        slug="solo-film",
    )

    entry = await service.resolve_entry(user_id=user_id)
    assert entry.destination == "workspace"
    assert len(entry.organizations) == 1
    assert entry.active_org_id == org.org_id

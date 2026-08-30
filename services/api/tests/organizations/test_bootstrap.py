import pytest
import uuid6
from clearcut.organizations.adapters.in_memory import InMemoryOrganizationRepository
from clearcut.organizations.application.bootstrap import OrganizationBootstrapService


@pytest.mark.asyncio
async def test_atomic_organization_bootstrap():
    repo = InMemoryOrganizationRepository()
    service = OrganizationBootstrapService(repository=repo)
    user_id = uuid6.uuid7()

    org, membership = await service.bootstrap_organization(
        user_id=user_id,
        name="Paramount Indie",
        slug="paramount-indie",
    )

    assert org.name == "Paramount Indie"
    assert org.slug == "paramount-indie"
    assert membership.org_id == org.org_id
    assert membership.user_id == user_id
    assert membership.role == "owner"
    assert membership.status == "active"


@pytest.mark.asyncio
async def test_slug_uniqueness_enforced():
    repo = InMemoryOrganizationRepository()
    service = OrganizationBootstrapService(repository=repo)
    user_id = uuid6.uuid7()

    await service.bootstrap_organization(
        user_id=user_id,
        name="Test Studio",
        slug="test-studio",
    )

    with pytest.raises(ValueError, match="Slug already in use"):
        await service.bootstrap_organization(
            user_id=user_id,
            name="Test Studio 2",
            slug="test-studio",
        )

from dataclasses import dataclass
from uuid import UUID

from clearcut.organizations.domain.models import Membership, Organization, slugify
from clearcut.organizations.ports.organization_repository import (
    OrganizationRepositoryPort,
)


@dataclass
class OrganizationEntryDto:
    destination: str  # "onboarding" | "workspace"
    organizations: list[Organization]
    active_org_id: UUID | None = None


class OrganizationBootstrapService:
    def __init__(self, repository: OrganizationRepositoryPort) -> None:
        self.repository = repository

    async def bootstrap_organization(
        self,
        user_id: UUID,
        name: str,
        slug: str,
    ) -> tuple[Organization, Membership]:
        clean_slug = slugify(slug)
        existing = await self.repository.get_organization_by_slug(clean_slug)
        if existing:
            raise ValueError("Slug already in use")

        org = Organization.create(name=name, slug=clean_slug)
        await self.repository.create_organization(org)

        membership = Membership.create_owner(org_id=org.org_id, user_id=user_id)
        await self.repository.save_membership(membership)

        return org, membership

    async def resolve_entry(self, user_id: UUID) -> OrganizationEntryDto:
        memberships = await self.repository.get_memberships_for_user(user_id)
        active_memberships = [m for m in memberships if m.status == "active"]

        if not active_memberships:
            return OrganizationEntryDto(
                destination="onboarding",
                organizations=[],
                active_org_id=None,
            )

        orgs: list[Organization] = []
        for m in active_memberships:
            org = await self.repository.get_organization_by_id(m.org_id)
            if org:
                orgs.append(org)

        return OrganizationEntryDto(
            destination="workspace",
            organizations=orgs,
            active_org_id=orgs[0].org_id if orgs else None,
        )

    async def list_organizations_for_user(self, user_id: UUID) -> list[Organization]:
        memberships = await self.repository.get_memberships_for_user(user_id)
        orgs: list[Organization] = []
        for m in memberships:
            if m.status == "active":
                org = await self.repository.get_organization_by_id(m.org_id)
                if org:
                    orgs.append(org)
        return orgs

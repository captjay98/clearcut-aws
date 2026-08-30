from uuid import UUID

from clearcut.organizations.domain.models import Membership, Organization
from clearcut.organizations.ports.organization_repository import (
    OrganizationRepositoryPort,
)


class InMemoryOrganizationRepository(OrganizationRepositoryPort):
    def __init__(self) -> None:
        self.organizations: dict[UUID, Organization] = {}
        self.orgs_by_slug: dict[str, UUID] = {}
        self.memberships: dict[UUID, Membership] = {}
        self.user_memberships: dict[UUID, list[UUID]] = {}

    async def create_organization(self, org: Organization) -> Organization:
        self.organizations[org.org_id] = org
        self.orgs_by_slug[org.slug] = org.org_id
        return org

    async def get_organization_by_slug(self, slug: str) -> Organization | None:
        org_id = self.orgs_by_slug.get(slug)
        if org_id:
            return self.organizations.get(org_id)
        return None

    async def get_organization_by_id(self, org_id: UUID) -> Organization | None:
        return self.organizations.get(org_id)

    async def save_membership(self, membership: Membership) -> None:
        self.memberships[membership.membership_id] = membership
        if membership.user_id not in self.user_memberships:
            self.user_memberships[membership.user_id] = []
        if membership.membership_id not in self.user_memberships[membership.user_id]:
            self.user_memberships[membership.user_id].append(membership.membership_id)

    async def get_memberships_for_user(self, user_id: UUID) -> list[Membership]:
        membership_ids = self.user_memberships.get(user_id, [])
        return [self.memberships[m_id] for m_id in membership_ids]

    async def get_membership(self, org_id: UUID, user_id: UUID) -> Membership | None:
        for membership in self.memberships.values():
            if membership.org_id == org_id and membership.user_id == user_id:
                return membership
        return None

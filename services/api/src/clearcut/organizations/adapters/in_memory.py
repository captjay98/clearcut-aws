from uuid import UUID

from clearcut.organizations.domain.invitations import Invitation
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
        self.invitations: dict[UUID, Invitation] = {}
        self.invitations_by_token_hash: dict[str, UUID] = {}

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

    async def get_membership_by_id(self, membership_id: UUID) -> Membership | None:
        return self.memberships.get(membership_id)

    async def get_memberships_for_user(self, user_id: UUID) -> list[Membership]:
        membership_ids = self.user_memberships.get(user_id, [])
        return [self.memberships[m_id] for m_id in membership_ids]

    async def get_memberships_for_org(self, org_id: UUID) -> list[Membership]:
        return [m for m in self.memberships.values() if m.org_id == org_id]

    async def get_membership(self, org_id: UUID, user_id: UUID) -> Membership | None:
        for membership in self.memberships.values():
            if membership.org_id == org_id and membership.user_id == user_id:
                return membership
        return None

    async def count_active_owners(self, org_id: UUID) -> int:
        return sum(
            1
            for m in self.memberships.values()
            if m.org_id == org_id and m.role == "owner" and m.status == "active"
        )

    async def save_invitation(self, invitation: Invitation) -> None:
        self.invitations[invitation.invitation_id] = invitation
        self.invitations_by_token_hash[invitation.token_hash] = invitation.invitation_id

    async def get_invitation_by_id(self, invitation_id: UUID) -> Invitation | None:
        return self.invitations.get(invitation_id)

    async def get_invitation_by_token_hash(self, token_hash: str) -> Invitation | None:
        inv_id = self.invitations_by_token_hash.get(token_hash)
        if inv_id:
            return self.invitations.get(inv_id)
        return None

    async def list_invitations_for_org(self, org_id: UUID) -> list[Invitation]:
        return [inv for inv in self.invitations.values() if inv.org_id == org_id]

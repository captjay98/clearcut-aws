from abc import ABC, abstractmethod
from uuid import UUID

from clearcut.organizations.domain.invitations import Invitation
from clearcut.organizations.domain.models import Membership, Organization


class OrganizationRepositoryPort(ABC):
    @abstractmethod
    async def create_organization(self, org: Organization) -> Organization:
        pass

    @abstractmethod
    async def get_organization_by_slug(self, slug: str) -> Organization | None:
        pass

    @abstractmethod
    async def get_organization_by_id(self, org_id: UUID) -> Organization | None:
        pass

    @abstractmethod
    async def save_membership(self, membership: Membership) -> None:
        pass

    @abstractmethod
    async def get_membership_by_id(self, membership_id: UUID) -> Membership | None:
        pass

    @abstractmethod
    async def get_memberships_for_user(self, user_id: UUID) -> list[Membership]:
        pass

    @abstractmethod
    async def get_memberships_for_org(self, org_id: UUID) -> list[Membership]:
        pass

    @abstractmethod
    async def get_membership(self, org_id: UUID, user_id: UUID) -> Membership | None:
        pass

    @abstractmethod
    async def count_active_owners(self, org_id: UUID) -> int:
        pass

    @abstractmethod
    async def save_invitation(self, invitation: Invitation) -> None:
        pass

    @abstractmethod
    async def get_invitation_by_id(self, invitation_id: UUID) -> Invitation | None:
        pass

    @abstractmethod
    async def get_invitation_by_token_hash(self, token_hash: str) -> Invitation | None:
        pass

    @abstractmethod
    async def list_invitations_for_org(self, org_id: UUID) -> list[Invitation]:
        pass

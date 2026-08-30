from abc import ABC, abstractmethod
from uuid import UUID

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
    async def get_memberships_for_user(self, user_id: UUID) -> list[Membership]:
        pass

    @abstractmethod
    async def get_membership(self, org_id: UUID, user_id: UUID) -> Membership | None:
        pass

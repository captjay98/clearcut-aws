"""Organization bootstrap: creating an organization and resolving where a user lands.

Creating an organization is one indivisible act. Three rows must exist together or
none of them may: the organization, its owner membership, and the organization's
default protected configuration binding.

The binding is not decoration. Detection, research, and selective rescan all
refuse to run unless the organization holds exactly one ``active`` binding, so an
organization committed without one can never complete a detection pass — the
owner would see a workspace that cannot do the one thing it exists to do. Seeding
it in the same transaction is what makes a freshly created organization usable.

The seeded binding is accountable to the human who created the organization:
``activated_by`` and ``activated_at`` name that owner and that instant, which is
also what the database's accountability constraint on an active row requires. It
is a real, replaceable binding rather than a placeholder — an Owner supersedes it
through the governed draft/validate/activate sequence, which leaves the seeded row
intact as superseded history.
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID

from clearcut.evaluation.domain.configuration import ProtectedConfiguration
from clearcut.organizations.domain.models import Membership, Organization, slugify
from clearcut.organizations.ports.organization_repository import (
    OrganizationRepositoryPort,
)


@dataclass
class OrganizationEntryDto:
    destination: str  # "onboarding" | "workspace"
    organizations: list[Organization]
    active_org_id: UUID | None = None


@dataclass(frozen=True)
class GovernanceSeedUnavailable:
    """Explicit typed absence of a seeded governing binding.

    Returned only by a repository with no governance store at all — the in-memory
    repository used for unit tests, which is never a deployment target. It is a
    typed value rather than ``None`` so a caller cannot mistake "this repository
    cannot seed a binding" for "a binding was seeded", and so an organization
    reaching production without a governing binding is impossible to overlook.
    """

    reason: str


type GovernanceSeedState = ProtectedConfiguration | GovernanceSeedUnavailable


@dataclass(frozen=True)
class BootstrappedOrganization:
    """Everything one organization-creation act committed.

    All three parts were committed together or none of them were, so a caller that
    holds this value knows the organization is usable: it has an owner and it has
    exactly one governing policy and prompt binding.
    """

    organization: Organization
    owner: Membership
    governance: GovernanceSeedState


@runtime_checkable
class AtomicOrganizationBootstrapPort(Protocol):
    """A repository that can commit an organization, its owner, and its binding atomically.

    This capability is deliberately structural rather than a method on
    :class:`~clearcut.organizations.ports.organization_repository.OrganizationRepositoryPort`:
    the base port's methods each manage their own unit of work, so nothing
    expressed through them can be atomic. A repository that implements this
    protocol commits all three rows in one transaction.
    """

    async def create_organization_with_owner(
        self,
        *,
        organization: Organization,
        owner: Membership,
    ) -> ProtectedConfiguration:
        """Commit the organization, its owner membership, and its default binding.

        Returns the seeded binding. Raises rather than committing a partial
        organization: an organization without an owner or without a governing
        binding is not a usable organization.
        """
        ...


class OrganizationBootstrapService:
    def __init__(self, repository: OrganizationRepositoryPort) -> None:
        self.repository = repository

    async def bootstrap_organization(
        self,
        user_id: UUID,
        name: str,
        slug: str,
    ) -> tuple[Organization, Membership]:
        """Create an organization with its owner and its default governing binding.

        Returns the organization and owner membership. Callers that need the
        seeded binding use :meth:`bootstrap_organization_with_governance`, which
        this method delegates to.
        """
        result = await self.bootstrap_organization_with_governance(
            user_id=user_id,
            name=name,
            slug=slug,
        )
        return result.organization, result.owner

    async def bootstrap_organization_with_governance(
        self,
        *,
        user_id: UUID,
        name: str,
        slug: str,
    ) -> BootstrappedOrganization:
        """Create an organization, its owner membership, and its governing binding.

        A repository that can commit the three rows atomically does so, which is
        the only arrangement that guarantees an organization is never visible
        without the binding that governs it. A repository without a governance
        store reports typed absence instead of pretending a binding exists.
        """
        clean_slug = slugify(slug)
        existing = await self.repository.get_organization_by_slug(clean_slug)
        if existing:
            raise ValueError("Slug already in use")

        org = Organization.create(name=name, slug=clean_slug)
        membership = Membership.create_owner(org_id=org.org_id, user_id=user_id)

        if isinstance(self.repository, AtomicOrganizationBootstrapPort):
            configuration = await self.repository.create_organization_with_owner(
                organization=org,
                owner=membership,
            )
            return BootstrappedOrganization(
                organization=org,
                owner=membership,
                governance=configuration,
            )

        # A repository with no governance store: create what it can hold, and say
        # plainly that no binding was seeded rather than implying one was.
        await self.repository.create_organization(org)
        await self.repository.save_membership(membership)
        return BootstrappedOrganization(
            organization=org,
            owner=membership,
            governance=GovernanceSeedUnavailable(
                reason=(
                    "This repository has no protected configuration store, so no "
                    "governing policy and prompt binding was seeded."
                )
            ),
        )

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


__all__ = [
    "AtomicOrganizationBootstrapPort",
    "BootstrappedOrganization",
    "GovernanceSeedState",
    "GovernanceSeedUnavailable",
    "OrganizationBootstrapService",
    "OrganizationEntryDto",
]

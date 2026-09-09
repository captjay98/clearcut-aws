from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
import uuid6
from clearcut.database import session_scope
from clearcut.evaluation.adapters.sql_configuration_repository import (
    SqlProtectedConfigurationRepository,
)
from clearcut.evaluation.domain.configuration import (
    ProtectedConfiguration,
    default_active_configuration,
)
from clearcut.organizations.domain.invitations import Invitation
from clearcut.organizations.domain.models import Membership, Organization
from clearcut.organizations.ports.organization_repository import OrganizationRepositoryPort
from sqlalchemy.ext.asyncio import AsyncSession


class SqlOrganizationRepository(OrganizationRepositoryPort):
    def __init__(self, db_session: AsyncSession) -> None:
        self.db = db_session
        self._configurations = SqlProtectedConfigurationRepository()

    async def create_organization_with_owner(
        self,
        *,
        organization: Organization,
        owner: Membership,
    ) -> ProtectedConfiguration:
        """Create the organization, its owner membership, and its governing binding.

        All three writes go to this repository's single session, so they commit
        together or not at all. Detection, research, and rescan all refuse to run
        unless the organization holds exactly one active protected configuration
        binding, so an organization committed without one could never complete a
        detection pass. Seeding it here is what makes a newly created organization
        usable, and doing it in this transaction is what makes that guarantee hold
        under any failure.

        The seeded binding is accountable to the owner who created the
        organization and carries the organization's own creation instant, which is
        what the database's accountability constraint on an active row requires.
        """
        await self.create_organization(organization)
        await self.save_membership(owner)
        configuration = default_active_configuration(
            config_id=uuid6.uuid7(),
            org_id=organization.org_id,
            owner_user_id=owner.user_id,
            created_at=organization.created_at,
        )
        await self._configurations.seed_default_binding(self.db, configuration=configuration)
        await self.db.flush()
        return configuration

    async def create_organization(self, org: Organization) -> Organization:
        await self.db.execute(
            sa.text(
                "INSERT INTO organizations (id, name, slug, created_at) "
                "VALUES (:id, :name, :slug, :created_at)"
            ),
            {
                "id": str(org.org_id),
                "name": org.name,
                "slug": org.slug,
                "created_at": org.created_at,
            },
        )
        await self.db.flush()
        return org

    async def get_organization_by_slug(self, slug: str) -> Organization | None:
        res = await self.db.execute(
            sa.text("SELECT id, name, slug, created_at FROM organizations WHERE slug = :slug"),
            {"slug": slug},
        )
        row = res.mappings().first()
        if not row:
            return None
        return Organization(
            org_id=UUID(str(row["id"])),
            name=row["name"],
            slug=row["slug"],
            created_at=row["created_at"] if isinstance(row["created_at"], datetime) else datetime.fromisoformat(str(row["created_at"])),
        )

    async def get_organization_by_id(self, org_id: UUID) -> Organization | None:
        res = await self.db.execute(
            sa.text("SELECT id, name, slug, created_at FROM organizations WHERE id = :id"),
            {"id": str(org_id)},
        )
        row = res.mappings().first()
        if not row:
            return None
        return Organization(
            org_id=UUID(str(row["id"])),
            name=row["name"],
            slug=row["slug"],
            created_at=row["created_at"] if isinstance(row["created_at"], datetime) else datetime.fromisoformat(str(row["created_at"])),
        )

    async def save_membership(self, membership: Membership) -> None:
        res = await self.db.execute(
            sa.text("SELECT id FROM memberships WHERE id = :id"),
            {"id": str(membership.membership_id)},
        )
        if res.mappings().first():
            await self.db.execute(
                sa.text(
                    "UPDATE memberships SET role = :role, status = :status WHERE id = :id"
                ),
                {
                    "id": str(membership.membership_id),
                    "role": membership.role,
                    "status": membership.status,
                },
            )
        else:
            await self.db.execute(
                sa.text(
                    "INSERT INTO memberships (id, org_id, user_id, role, status, created_at) "
                    "VALUES (:id, :org_id, :user_id, :role, :status, :created_at)"
                ),
                {
                    "id": str(membership.membership_id),
                    "org_id": str(membership.org_id),
                    "user_id": str(membership.user_id),
                    "role": membership.role,
                    "status": membership.status,
                    "created_at": membership.created_at,
                },
            )
        await self.db.flush()

    async def get_membership_by_id(self, membership_id: UUID) -> Membership | None:
        res = await self.db.execute(
            sa.text(
                "SELECT id, org_id, user_id, role, status, created_at "
                "FROM memberships WHERE id = :id"
            ),
            {"id": str(membership_id)},
        )
        row = res.mappings().first()
        if not row:
            return None
        return Membership(
            membership_id=UUID(str(row["id"])),
            org_id=UUID(str(row["org_id"])),
            user_id=UUID(str(row["user_id"])),
            role=row["role"],
            status=row["status"],
            created_at=row["created_at"] if isinstance(row["created_at"], datetime) else datetime.fromisoformat(str(row["created_at"])),
        )

    async def get_memberships_for_user(self, user_id: UUID) -> list[Membership]:
        res = await self.db.execute(
            sa.text(
                "SELECT id, org_id, user_id, role, status, created_at "
                "FROM memberships WHERE user_id = :user_id"
            ),
            {"user_id": str(user_id)},
        )
        return [
            Membership(
                membership_id=UUID(str(row["id"])),
                org_id=UUID(str(row["org_id"])),
                user_id=UUID(str(row["user_id"])),
                role=row["role"],
                status=row["status"],
                created_at=row["created_at"] if isinstance(row["created_at"], datetime) else datetime.fromisoformat(str(row["created_at"])),
            )
            for row in res.mappings().all()
        ]

    async def get_memberships_for_org(self, org_id: UUID) -> list[Membership]:
        res = await self.db.execute(
            sa.text(
                "SELECT id, org_id, user_id, role, status, created_at "
                "FROM memberships WHERE org_id = :org_id"
            ),
            {"org_id": str(org_id)},
        )
        return [
            Membership(
                membership_id=UUID(str(row["id"])),
                org_id=UUID(str(row["org_id"])),
                user_id=UUID(str(row["user_id"])),
                role=row["role"],
                status=row["status"],
                created_at=row["created_at"] if isinstance(row["created_at"], datetime) else datetime.fromisoformat(str(row["created_at"])),
            )
            for row in res.mappings().all()
        ]

    async def get_membership(self, org_id: UUID, user_id: UUID) -> Membership | None:
        res = await self.db.execute(
            sa.text(
                "SELECT id, org_id, user_id, role, status, created_at "
                "FROM memberships WHERE org_id = :org_id AND user_id = :user_id"
            ),
            {"org_id": str(org_id), "user_id": str(user_id)},
        )
        row = res.mappings().first()
        if not row:
            return None
        return Membership(
            membership_id=UUID(str(row["id"])),
            org_id=UUID(str(row["org_id"])),
            user_id=UUID(str(row["user_id"])),
            role=row["role"],
            status=row["status"],
            created_at=row["created_at"] if isinstance(row["created_at"], datetime) else datetime.fromisoformat(str(row["created_at"])),
        )

    async def count_active_owners(self, org_id: UUID) -> int:
        res = await self.db.execute(
            sa.text(
                "SELECT count(*) FROM memberships "
                "WHERE org_id = :org_id AND role = 'owner' AND status = 'active'"
            ),
            {"org_id": str(org_id)},
        )
        return res.scalar() or 0

    async def save_invitation(self, invitation: Invitation) -> None:
        res = await self.db.execute(
            sa.text("SELECT id FROM invitations WHERE id = :id"),
            {"id": str(invitation.invitation_id)},
        )
        if res.mappings().first():
            await self.db.execute(
                sa.text(
                    "UPDATE invitations SET status = :status, accepted_at = :accepted_at, "
                    "revoked_at = :revoked_at, expires_at = :expires_at WHERE id = :id"
                ),
                {
                    "id": str(invitation.invitation_id),
                    "status": invitation.status,
                    "accepted_at": invitation.accepted_at,
                    "revoked_at": invitation.revoked_at,
                    "expires_at": invitation.expires_at,
                },
            )
        else:
            await self.db.execute(
                sa.text(
                    "INSERT INTO invitations (id, org_id, invited_by_user_id, email, role, token_hash, status, created_at, expires_at, accepted_at, revoked_at) "
                    "VALUES (:id, :org_id, :invited_by_user_id, :email, :role, :token_hash, :status, :created_at, :expires_at, :accepted_at, :revoked_at)"
                ),
                {
                    "id": str(invitation.invitation_id),
                    "org_id": str(invitation.org_id),
                    "invited_by_user_id": str(invitation.invited_by_user_id),
                    "email": invitation.email,
                    "role": invitation.role,
                    "token_hash": invitation.token_hash,
                    "status": invitation.status,
                    "created_at": invitation.created_at,
                    "expires_at": invitation.expires_at,
                    "accepted_at": invitation.accepted_at,
                    "revoked_at": invitation.revoked_at,
                },
            )
        await self.db.flush()

    async def get_invitation_by_id(self, invitation_id: UUID) -> Invitation | None:
        res = await self.db.execute(
            sa.text(
                "SELECT id, org_id, invited_by_user_id, email, role, token_hash, status, created_at, expires_at, accepted_at, revoked_at "
                "FROM invitations WHERE id = :id"
            ),
            {"id": str(invitation_id)},
        )
        row = res.mappings().first()
        if not row:
            return None
        return Invitation(
            invitation_id=UUID(str(row["id"])),
            org_id=UUID(str(row["org_id"])),
            invited_by_user_id=UUID(str(row["invited_by_user_id"])),
            email=row["email"],
            role=row["role"],
            token_hash=row["token_hash"],
            status=row["status"],
            created_at=row["created_at"] if isinstance(row["created_at"], datetime) else datetime.fromisoformat(str(row["created_at"])),
            expires_at=row["expires_at"] if isinstance(row["expires_at"], datetime) else datetime.fromisoformat(str(row["expires_at"])),
            accepted_at=row["accepted_at"] if (row["accepted_at"] is None or isinstance(row["accepted_at"], datetime)) else datetime.fromisoformat(str(row["accepted_at"])),
            revoked_at=row["revoked_at"] if (row["revoked_at"] is None or isinstance(row["revoked_at"], datetime)) else datetime.fromisoformat(str(row["revoked_at"])),
        )

    async def get_invitation_by_token_hash(self, token_hash: str) -> Invitation | None:
        res = await self.db.execute(
            sa.text(
                "SELECT id, org_id, invited_by_user_id, email, role, token_hash, status, created_at, expires_at, accepted_at, revoked_at "
                "FROM invitations WHERE token_hash = :token_hash"
            ),
            {"token_hash": token_hash},
        )
        row = res.mappings().first()
        if not row:
            return None
        return Invitation(
            invitation_id=UUID(str(row["id"])),
            org_id=UUID(str(row["org_id"])),
            invited_by_user_id=UUID(str(row["invited_by_user_id"])),
            email=row["email"],
            role=row["role"],
            token_hash=row["token_hash"],
            status=row["status"],
            created_at=row["created_at"] if isinstance(row["created_at"], datetime) else datetime.fromisoformat(str(row["created_at"])),
            expires_at=row["expires_at"] if isinstance(row["expires_at"], datetime) else datetime.fromisoformat(str(row["expires_at"])),
            accepted_at=row["accepted_at"] if (row["accepted_at"] is None or isinstance(row["accepted_at"], datetime)) else datetime.fromisoformat(str(row["accepted_at"])),
            revoked_at=row["revoked_at"] if (row["revoked_at"] is None or isinstance(row["revoked_at"], datetime)) else datetime.fromisoformat(str(row["revoked_at"])),
        )

    async def list_invitations_for_org(self, org_id: UUID) -> list[Invitation]:
        res = await self.db.execute(
            sa.text(
                "SELECT id, org_id, invited_by_user_id, email, role, token_hash, status, created_at, expires_at, accepted_at, revoked_at "
                "FROM invitations WHERE org_id = :org_id"
            ),
            {"org_id": str(org_id)},
        )
        return [
            Invitation(
                invitation_id=UUID(str(row["id"])),
                org_id=UUID(str(row["org_id"])),
                invited_by_user_id=UUID(str(row["invited_by_user_id"])),
                email=row["email"],
                role=row["role"],
                token_hash=row["token_hash"],
                status=row["status"],
                created_at=row["created_at"] if isinstance(row["created_at"], datetime) else datetime.fromisoformat(str(row["created_at"])),
                expires_at=row["expires_at"] if isinstance(row["expires_at"], datetime) else datetime.fromisoformat(str(row["expires_at"])),
                accepted_at=row["accepted_at"] if (row["accepted_at"] is None or isinstance(row["accepted_at"], datetime)) else datetime.fromisoformat(str(row["accepted_at"])),
                revoked_at=row["revoked_at"] if (row["revoked_at"] is None or isinstance(row["revoked_at"], datetime)) else datetime.fromisoformat(str(row["revoked_at"])),
            )
            for row in res.mappings().all()
        ]


class DatabaseOrganizationRepository(OrganizationRepositoryPort):
    async def create_organization_with_owner(
        self,
        *,
        organization: Organization,
        owner: Membership,
    ) -> ProtectedConfiguration:
        """Commit the organization, its owner, and its governing binding atomically.

        This is the single unit of work the whole creation act runs in. Every other
        method on this class opens its own session, which is why organization
        creation cannot be composed from them: a failure between two of those calls
        would leave an organization with no owner, or an owner with no governing
        policy binding — an organization that exists but can never run a detection
        pass.
        """
        async with session_scope() as db:
            repo = SqlOrganizationRepository(db)
            return await repo.create_organization_with_owner(
                organization=organization,
                owner=owner,
            )

    async def create_organization(self, org: Organization) -> Organization:
        async with session_scope() as db:
            repo = SqlOrganizationRepository(db)
            return await repo.create_organization(org)

    async def get_organization_by_slug(self, slug: str) -> Organization | None:
        async with session_scope() as db:
            repo = SqlOrganizationRepository(db)
            return await repo.get_organization_by_slug(slug)

    async def get_organization_by_id(self, org_id: UUID) -> Organization | None:
        async with session_scope() as db:
            repo = SqlOrganizationRepository(db)
            return await repo.get_organization_by_id(org_id)

    async def save_membership(self, membership: Membership) -> None:
        async with session_scope() as db:
            repo = SqlOrganizationRepository(db)
            await repo.save_membership(membership)

    async def get_membership_by_id(self, membership_id: UUID) -> Membership | None:
        async with session_scope() as db:
            repo = SqlOrganizationRepository(db)
            return await repo.get_membership_by_id(membership_id)

    async def get_memberships_for_user(self, user_id: UUID) -> list[Membership]:
        async with session_scope() as db:
            repo = SqlOrganizationRepository(db)
            return await repo.get_memberships_for_user(user_id)

    async def get_memberships_for_org(self, org_id: UUID) -> list[Membership]:
        async with session_scope() as db:
            repo = SqlOrganizationRepository(db)
            return await repo.get_memberships_for_org(org_id)

    async def get_membership(self, org_id: UUID, user_id: UUID) -> Membership | None:
        async with session_scope() as db:
            repo = SqlOrganizationRepository(db)
            return await repo.get_membership(org_id, user_id)

    async def count_active_owners(self, org_id: UUID) -> int:
        async with session_scope() as db:
            repo = SqlOrganizationRepository(db)
            return await repo.count_active_owners(org_id)

    async def save_invitation(self, invitation: Invitation) -> None:
        async with session_scope() as db:
            repo = SqlOrganizationRepository(db)
            await repo.save_invitation(invitation)

    async def get_invitation_by_id(self, invitation_id: UUID) -> Invitation | None:
        async with session_scope() as db:
            repo = SqlOrganizationRepository(db)
            return await repo.get_invitation_by_id(invitation_id)

    async def get_invitation_by_token_hash(self, token_hash: str) -> Invitation | None:
        async with session_scope() as db:
            repo = SqlOrganizationRepository(db)
            return await repo.get_invitation_by_token_hash(token_hash)

    async def list_invitations_for_org(self, org_id: UUID) -> list[Invitation]:
        async with session_scope() as db:
            repo = SqlOrganizationRepository(db)
            return await repo.list_invitations_for_org(org_id)

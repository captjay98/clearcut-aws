import hashlib
import secrets
from uuid import UUID

from clearcut.organizations.domain.capabilities import has_capability
from clearcut.organizations.domain.invitations import (
    Invitation,
)
from clearcut.organizations.domain.models import Membership, coerce_role_type
from clearcut.organizations.ports.email_delivery import EmailDeliveryPort
from clearcut.organizations.ports.organization_repository import (
    OrganizationRepositoryPort,
)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class InvitationService:
    def __init__(
        self,
        repository: OrganizationRepositoryPort,
        email_delivery: EmailDeliveryPort | None = None,
    ) -> None:
        self.repository = repository
        self.email_delivery = email_delivery

    async def create_invitation(
        self,
        org_id: UUID,
        actor_id: UUID,
        email: str,
        role: str,
    ) -> tuple[Invitation, str]:
        actor_m = await self.repository.get_membership(org_id, actor_id)
        if not actor_m or not has_capability(actor_m.role, "member:invite"):
            raise PermissionError("Actor lacks member:invite capability")

        raw_token = secrets.token_urlsafe(32)
        token_hash = hash_token(raw_token)

        invitation = Invitation.create(
            org_id=org_id,
            invited_by_user_id=actor_id,
            email=email,
            role=role,
            token_hash=token_hash,
        )
        await self.repository.save_invitation(invitation)

        if self.email_delivery:
            org = await self.repository.get_organization_by_id(org_id)
            org_name = org.name if org else "ClearCut Workspace"
            await self.email_delivery.send_invitation_email(
                recipient_email=email,
                org_name=org_name,
                inviter_name="Team Admin",
                raw_token=raw_token,
            )

        return invitation, raw_token

    async def accept_invitation(
        self,
        raw_token: str,
        user_id: UUID,
        user_email: str,
    ) -> Membership:
        token_hash = hash_token(raw_token)
        invitation = await self.repository.get_invitation_by_token_hash(token_hash)
        if not invitation:
            raise ValueError("Invitation not found or invalid token")

        invitation.accept(actor_email=user_email)
        await self.repository.save_invitation(invitation)

        membership = Membership(
            membership_id=invitation.invitation_id,
            org_id=invitation.org_id,
            user_id=user_id,
            role=coerce_role_type(invitation.role),
            status="active",
            created_at=invitation.created_at,
        )
        await self.repository.save_membership(membership)
        return membership

    async def decline_invitation(self, raw_token: str) -> None:
        token_hash = hash_token(raw_token)
        invitation = await self.repository.get_invitation_by_token_hash(token_hash)
        if not invitation:
            raise ValueError("Invitation not found or invalid token")

        invitation.decline()
        await self.repository.save_invitation(invitation)

    async def revoke_invitation(self, org_id: UUID, actor_id: UUID, invitation_id: UUID) -> None:
        actor_m = await self.repository.get_membership(org_id, actor_id)
        if not actor_m or not has_capability(actor_m.role, "member:invite"):
            raise PermissionError("Actor lacks member:invite capability")

        invitation = await self.repository.get_invitation_by_id(invitation_id)
        if not invitation or invitation.org_id != org_id:
            raise ValueError("Invitation not found")

        invitation.revoke()
        await self.repository.save_invitation(invitation)

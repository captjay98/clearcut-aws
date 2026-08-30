from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID

import uuid6


def normalize_email(email: str) -> str:
    return email.strip().lower()


class InvitationStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"
    REVOKED = "revoked"


@dataclass
class Invitation:
    invitation_id: UUID
    org_id: UUID
    invited_by_user_id: UUID
    email: str
    role: str
    token_hash: str
    status: InvitationStatus
    created_at: datetime
    expires_at: datetime
    accepted_at: datetime | None = None
    revoked_at: datetime | None = None

    @classmethod
    def create(
        cls,
        org_id: UUID,
        invited_by_user_id: UUID,
        email: str,
        role: str,
        token_hash: str,
        ttl_hours: int = 168,  # 7 days
    ) -> "Invitation":
        now = datetime.now(UTC)
        return cls(
            invitation_id=uuid6.uuid7(),
            org_id=org_id,
            invited_by_user_id=invited_by_user_id,
            email=normalize_email(email),
            role=role,
            token_hash=token_hash,
            status=InvitationStatus.PENDING,
            created_at=now,
            expires_at=now + timedelta(hours=ttl_hours),
        )

    def is_active(self) -> bool:
        now = datetime.now(UTC)
        return self.status == InvitationStatus.PENDING and self.expires_at > now

    def accept(self, actor_email: str) -> None:
        if normalize_email(actor_email) != self.email:
            raise ValueError("Invitation email does not match actor account")
        if not self.is_active():
            raise ValueError(f"Cannot accept invitation in state {self.status}")
        self.status = InvitationStatus.ACCEPTED
        self.accepted_at = datetime.now(UTC)

    def decline(self) -> None:
        if not self.is_active():
            raise ValueError(f"Cannot decline invitation in state {self.status}")
        self.status = InvitationStatus.DECLINED

    def revoke(self) -> None:
        self.status = InvitationStatus.REVOKED
        self.revoked_at = datetime.now(UTC)

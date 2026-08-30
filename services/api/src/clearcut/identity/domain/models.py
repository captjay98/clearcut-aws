from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import uuid6


def normalize_email(email: str) -> str:
    return email.strip().lower()


@dataclass(frozen=True)
class User:
    user_id: UUID
    email: str
    created_at: datetime

    @classmethod
    def create(cls, email: str) -> "User":
        return cls(
            user_id=uuid6.uuid7(),
            email=normalize_email(email),
            created_at=datetime.now(UTC),
        )


@dataclass(frozen=True)
class LocalCredential:
    user_id: UUID
    password_hash: str
    updated_at: datetime


@dataclass
class Session:
    session_id: UUID
    user_id: UUID
    token_hash: str
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None

    @classmethod
    def create(cls, user_id: UUID, token_hash: str, ttl_hours: int = 24 * 7) -> "Session":
        now = datetime.now(UTC)
        return cls(
            session_id=uuid6.uuid7(),
            user_id=user_id,
            token_hash=token_hash,
            created_at=now,
            expires_at=now + timedelta(hours=ttl_hours),
            revoked_at=None,
        )

    def is_active(self) -> bool:
        now = datetime.now(UTC)
        return self.revoked_at is None and self.expires_at > now

    def revoke(self) -> None:
        self.revoked_at = datetime.now(UTC)


@dataclass(frozen=True)
class SecurityEvent:
    event_id: UUID
    user_id: UUID | None
    event_type: str
    ip_address: str | None
    user_agent: str | None
    occurred_at: datetime

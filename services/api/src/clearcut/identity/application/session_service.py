import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import uuid6
from clearcut.identity.domain.models import SecurityEvent, Session
from clearcut.identity.ports.identity_provider import (
    IdentityProviderPort,
    IdentityRepositoryPort,
)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass
class SessionContextDto:
    authenticated: bool
    user_id: UUID | None = None
    email: str | None = None
    active_org_id: UUID | None = None
    role: str | None = None


class SessionService:
    def __init__(
        self,
        repository: IdentityRepositoryPort,
        identity_provider: IdentityProviderPort,
    ) -> None:
        self.repository = repository
        self.identity_provider = identity_provider

    async def create_session(
        self,
        email: str,
        password: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[Session, str]:
        user = await self.repository.get_user_by_email(email)
        if not user:
            # Timing mitigation: dummy verify
            self.identity_provider.verify_password(
                "$argon2id$v=19$m=65536,t=3,p=4$dummy$dummy", "dummy"
            )
            await self.repository.record_security_event(
                SecurityEvent(
                    event_id=uuid6.uuid7(),
                    user_id=None,
                    event_type="auth.login.failed",
                    ip_address=ip_address,
                    user_agent=user_agent,
                    occurred_at=datetime.now(UTC),
                )
            )
            raise ValueError("Invalid credentials")

        pw_hash = await self.repository.get_credential(user.user_id)
        if not pw_hash or not self.identity_provider.verify_password(pw_hash, password):
            await self.repository.record_security_event(
                SecurityEvent(
                    event_id=uuid6.uuid7(),
                    user_id=user.user_id,
                    event_type="auth.login.failed",
                    ip_address=ip_address,
                    user_agent=user_agent,
                    occurred_at=datetime.now(UTC),
                )
            )
            raise ValueError("Invalid credentials")

        # Generate cryptographically secure token
        raw_token = secrets.token_urlsafe(32)
        token_hash = hash_token(raw_token)

        session = Session.create(user_id=user.user_id, token_hash=token_hash)
        await self.repository.save_session(session)

        await self.repository.record_security_event(
            SecurityEvent(
                event_id=uuid6.uuid7(),
                user_id=user.user_id,
                event_type="auth.login.success",
                ip_address=ip_address,
                user_agent=user_agent,
                occurred_at=datetime.now(UTC),
            )
        )

        return session, raw_token

    async def get_session_context(self, token: str) -> SessionContextDto | None:
        if not token:
            return SessionContextDto(authenticated=False)

        token_hash = hash_token(token)
        session = await self.repository.get_session_by_token_hash(token_hash)
        if not session or not session.is_active():
            return SessionContextDto(authenticated=False)

        user = await self.repository.get_user_by_id(session.user_id)
        if not user:
            return SessionContextDto(authenticated=False)

        return SessionContextDto(
            authenticated=True,
            user_id=user.user_id,
            email=user.email,
        )

    async def revoke_current_session(self, token: str) -> bool:
        if not token:
            return False
        token_hash = hash_token(token)
        session = await self.repository.get_session_by_token_hash(token_hash)
        if session and session.is_active():
            await self.repository.revoke_session(session.session_id)
            return True
        return False

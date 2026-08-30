from uuid import UUID

from clearcut.identity.domain.models import SecurityEvent, Session, User, normalize_email
from clearcut.identity.ports.identity_provider import IdentityRepositoryPort


class InMemoryIdentityRepository(IdentityRepositoryPort):
    def __init__(self) -> None:
        self.users: dict[UUID, User] = {}
        self.users_by_email: dict[str, UUID] = {}
        self.credentials: dict[UUID, str] = {}
        self.sessions_by_hash: dict[str, Session] = {}
        self.security_events: list[SecurityEvent] = []

    async def create_user_with_password(self, email: str, password_hash: str) -> User:
        user = User.create(email=email)
        self.users[user.user_id] = user
        self.users_by_email[user.email] = user.user_id
        self.credentials[user.user_id] = password_hash
        return user

    async def get_user_by_email(self, email: str) -> User | None:
        normalized = normalize_email(email)
        user_id = self.users_by_email.get(normalized)
        if user_id:
            return self.users.get(user_id)
        return None

    async def get_user_by_id(self, user_id: UUID) -> User | None:
        return self.users.get(user_id)

    async def get_credential(self, user_id: UUID) -> str | None:
        return self.credentials.get(user_id)

    async def save_session(self, session: Session) -> None:
        self.sessions_by_hash[session.token_hash] = session

    async def get_session_by_token_hash(self, token_hash: str) -> Session | None:
        return self.sessions_by_hash.get(token_hash)

    async def revoke_session(self, session_id: UUID) -> None:
        for session in self.sessions_by_hash.values():
            if session.session_id == session_id:
                session.revoke()

    async def record_security_event(self, event: SecurityEvent) -> None:
        self.security_events.append(event)

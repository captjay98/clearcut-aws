from abc import ABC, abstractmethod
from uuid import UUID

from clearcut.identity.domain.models import SecurityEvent, Session, User


class IdentityProviderPort(ABC):
    @abstractmethod
    def hash_password(self, password: str) -> str:
        pass

    @abstractmethod
    def verify_password(self, password_hash: str, password: str) -> bool:
        pass


class IdentityRepositoryPort(ABC):
    @abstractmethod
    async def get_user_by_email(self, email: str) -> User | None:
        pass

    @abstractmethod
    async def get_user_by_id(self, user_id: UUID) -> User | None:
        pass

    @abstractmethod
    async def get_credential(self, user_id: UUID) -> str | None:
        pass

    @abstractmethod
    async def save_session(self, session: Session) -> None:
        pass

    @abstractmethod
    async def get_session_by_token_hash(self, token_hash: str) -> Session | None:
        pass

    @abstractmethod
    async def revoke_session(self, session_id: UUID) -> None:
        pass

    @abstractmethod
    async def record_security_event(self, event: SecurityEvent) -> None:
        pass

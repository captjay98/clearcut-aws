from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from clearcut.database import session_scope
from clearcut.identity.domain.models import SecurityEvent, Session, User, normalize_email
from clearcut.identity.ports.identity_provider import IdentityRepositoryPort
from sqlalchemy.ext.asyncio import AsyncSession


class SqlIdentityRepository(IdentityRepositoryPort):
    def __init__(self, db_session: AsyncSession) -> None:
        self.db = db_session

    async def create_user_with_password(self, email: str, password_hash: str) -> User:
        user = User.create(email=email)
        now = datetime.now(UTC)

        await self.db.execute(
            sa.text(
                "INSERT INTO users (id, email, created_at) VALUES (:id, :email, :created_at)"
            ),
            {"id": str(user.user_id), "email": user.email, "created_at": user.created_at},
        )
        await self.db.execute(
            sa.text(
                "INSERT INTO local_credentials (user_id, password_hash, updated_at) "
                "VALUES (:user_id, :password_hash, :updated_at)"
            ),
            {"user_id": str(user.user_id), "password_hash": password_hash, "updated_at": now},
        )
        await self.db.flush()
        return user

    async def get_user_by_email(self, email: str) -> User | None:
        normalized = normalize_email(email)
        res = await self.db.execute(
            sa.text("SELECT id, email, created_at FROM users WHERE email = :email"),
            {"email": normalized},
        )
        row = res.mappings().first()
        if not row:
            return None
        return User(
            user_id=UUID(str(row["id"])),
            email=row["email"],
            created_at=row["created_at"] if isinstance(row["created_at"], datetime) else datetime.fromisoformat(str(row["created_at"])),
        )

    async def get_user_by_id(self, user_id: UUID) -> User | None:
        res = await self.db.execute(
            sa.text("SELECT id, email, created_at FROM users WHERE id = :id"),
            {"id": str(user_id)},
        )
        row = res.mappings().first()
        if not row:
            return None
        return User(
            user_id=UUID(str(row["id"])),
            email=row["email"],
            created_at=row["created_at"] if isinstance(row["created_at"], datetime) else datetime.fromisoformat(str(row["created_at"])),
        )

    async def get_credential(self, user_id: UUID) -> str | None:
        res = await self.db.execute(
            sa.text("SELECT password_hash FROM local_credentials WHERE user_id = :user_id"),
            {"user_id": str(user_id)},
        )
        row = res.mappings().first()
        return row["password_hash"] if row else None

    async def save_session(self, session: Session) -> None:
        res = await self.db.execute(
            sa.text("SELECT id FROM sessions WHERE id = :id"),
            {"id": str(session.session_id)},
        )
        if res.mappings().first():
            await self.db.execute(
                sa.text(
                    "UPDATE sessions SET revoked_at = :revoked_at, expires_at = :expires_at "
                    "WHERE id = :id"
                ),
                {
                    "id": str(session.session_id),
                    "revoked_at": session.revoked_at,
                    "expires_at": session.expires_at,
                },
            )
        else:
            await self.db.execute(
                sa.text(
                    "INSERT INTO sessions (id, user_id, token_hash, created_at, expires_at, revoked_at) "
                    "VALUES (:id, :user_id, :token_hash, :created_at, :expires_at, :revoked_at)"
                ),
                {
                    "id": str(session.session_id),
                    "user_id": str(session.user_id),
                    "token_hash": session.token_hash,
                    "created_at": session.created_at,
                    "expires_at": session.expires_at,
                    "revoked_at": session.revoked_at,
                },
            )
        await self.db.flush()

    async def get_session_by_token_hash(self, token_hash: str) -> Session | None:
        res = await self.db.execute(
            sa.text(
                "SELECT id, user_id, token_hash, created_at, expires_at, revoked_at "
                "FROM sessions WHERE token_hash = :token_hash"
            ),
            {"token_hash": token_hash},
        )
        row = res.mappings().first()
        if not row:
            return None
        return Session(
            session_id=UUID(str(row["id"])),
            user_id=UUID(str(row["user_id"])),
            token_hash=row["token_hash"],
            created_at=row["created_at"] if isinstance(row["created_at"], datetime) else datetime.fromisoformat(str(row["created_at"])),
            expires_at=row["expires_at"] if isinstance(row["expires_at"], datetime) else datetime.fromisoformat(str(row["expires_at"])),
            revoked_at=row["revoked_at"] if (row["revoked_at"] is None or isinstance(row["revoked_at"], datetime)) else datetime.fromisoformat(str(row["revoked_at"])),
        )

    async def revoke_session(self, session_id: UUID) -> None:
        now = datetime.now(UTC)
        await self.db.execute(
            sa.text("UPDATE sessions SET revoked_at = :revoked_at WHERE id = :id"),
            {"id": str(session_id), "revoked_at": now},
        )
        await self.db.flush()

    async def record_security_event(self, event: SecurityEvent) -> None:
        await self.db.execute(
            sa.text(
                "INSERT INTO security_events (id, user_id, event_type, ip_address, user_agent, occurred_at) "
                "VALUES (:id, :user_id, :event_type, :ip_address, :user_agent, :occurred_at)"
            ),
            {
                "id": str(event.event_id),
                "user_id": str(event.user_id) if event.user_id else None,
                "event_type": event.event_type,
                "ip_address": event.ip_address,
                "user_agent": event.user_agent,
                "occurred_at": event.occurred_at,
            },
        )
        await self.db.flush()


class DatabaseIdentityRepository(IdentityRepositoryPort):
    """Database-backed repository executing with session_scope()."""

    async def create_user_with_password(self, email: str, password_hash: str) -> User:
        async with session_scope() as db:
            repo = SqlIdentityRepository(db)
            return await repo.create_user_with_password(email, password_hash)

    async def get_user_by_email(self, email: str) -> User | None:
        async with session_scope() as db:
            repo = SqlIdentityRepository(db)
            return await repo.get_user_by_email(email)

    async def get_user_by_id(self, user_id: UUID) -> User | None:
        async with session_scope() as db:
            repo = SqlIdentityRepository(db)
            return await repo.get_user_by_id(user_id)

    async def get_credential(self, user_id: UUID) -> str | None:
        async with session_scope() as db:
            repo = SqlIdentityRepository(db)
            return await repo.get_credential(user_id)

    async def save_session(self, session: Session) -> None:
        async with session_scope() as db:
            repo = SqlIdentityRepository(db)
            await repo.save_session(session)

    async def get_session_by_token_hash(self, token_hash: str) -> Session | None:
        async with session_scope() as db:
            repo = SqlIdentityRepository(db)
            return await repo.get_session_by_token_hash(token_hash)

    async def revoke_session(self, session_id: UUID) -> None:
        async with session_scope() as db:
            repo = SqlIdentityRepository(db)
            await repo.revoke_session(session_id)

    async def record_security_event(self, event: SecurityEvent) -> None:
        async with session_scope() as db:
            repo = SqlIdentityRepository(db)
            await repo.record_security_event(event)

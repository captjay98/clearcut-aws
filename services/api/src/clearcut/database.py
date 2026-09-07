"""SQLAlchemy async database engine and session management."""
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from clearcut.bootstrap.settings import (
    LOCAL_SQLITE_URL,
    DeploymentProfile,
    validate_hosted_database_url,
)

deployment_profile_value = os.getenv(
    "CLEARCUT_DEPLOYMENT_PROFILE",
    DeploymentProfile.LOCAL.value,
)
try:
    deployment_profile = DeploymentProfile(deployment_profile_value.strip().lower())
except ValueError as error:
    raise RuntimeError(
        f"Unsupported CLEARCUT_DEPLOYMENT_PROFILE: {deployment_profile_value!r}."
    ) from error

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    if deployment_profile is not DeploymentProfile.LOCAL:
        raise RuntimeError("DATABASE_URL is required for hosted deployment profiles.")
    DATABASE_URL = LOCAL_SQLITE_URL

if deployment_profile in {DeploymentProfile.PORTABLE, DeploymentProfile.GCP}:
    try:
        validate_hosted_database_url(DATABASE_URL)
    except ValueError as error:
        raise RuntimeError(str(error)) from error

is_sqlite = DATABASE_URL.startswith("sqlite")


def database_wall_clock_sql(dialect_name: str) -> str:
    """Return a trusted SQL fragment for statement-evaluated database wall time."""
    if dialect_name == "postgresql":
        return "clock_timestamp()"
    if dialect_name == "sqlite":
        return "STRFTIME('%Y-%m-%d %H:%M:%f', 'now')"
    raise RuntimeError(f"Unsupported database dialect: {dialect_name}")


engine_kwargs: dict[str, Any] = {"echo": False}
if not is_sqlite:
    engine_kwargs.update({
        "pool_size": 10,
        "max_overflow": 20,
        "pool_pre_ping": True,
    })

engine: AsyncEngine = create_async_engine(DATABASE_URL, **engine_kwargs)

if is_sqlite:
    @event.listens_for(engine.sync_engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency generator yielding an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for database sessions outside HTTP request handlers."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

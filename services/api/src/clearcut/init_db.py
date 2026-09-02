"""Alembic-backed database initialization and optional canonical seeding."""
import asyncio
import importlib
import logging
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import cast

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from clearcut.database import DATABASE_URL, engine

logger = logging.getLogger(__name__)
API_ROOT = Path(__file__).resolve().parents[2]


class UnversionedLegacySchemaError(RuntimeError):
    """Raised before Alembic can collide with the retired runtime-DDL schema."""


def _alembic_config() -> Config:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))
    return config


def _validate_database_bootstrap(connection: sa.Connection) -> None:
    """Accept an empty or valid Alembic database and preserve legacy data unchanged."""
    table_names = set(sa.inspect(connection).get_table_names())
    application_tables = sorted(
        table_name
        for table_name in table_names
        if table_name != "alembic_version" and not table_name.startswith("sqlite_")
    )
    if not application_tables:
        return

    if "alembic_version" not in table_names:
        revisions: set[str] = set()
    else:
        revisions = set(
            connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalars()
        )

    known_revisions = {
        script.revision for script in ScriptDirectory.from_config(_alembic_config()).walk_revisions()
    }
    if not revisions or not revisions <= known_revisions:
        joined = ", ".join(application_tables)
        revision_detail = ", ".join(sorted(revisions)) if revisions else "none"
        raise UnversionedLegacySchemaError(
            "Detected an unversioned or unknown-revision ClearCut schema; startup "
            "stopped before modifying it. Back up/export the database and migrate it "
            f"explicitly before restarting. Revision(s): {revision_detail}. "
            f"Managed tables found: {joined}."
        )


def _upgrade_database_to_head() -> None:
    """Run the canonical Alembic migration chain from a synchronous worker thread."""
    command.upgrade(_alembic_config(), "head")


SeedFunction = Callable[[], Awaitable[bool]]


def _load_seed() -> SeedFunction:
    if str(API_ROOT) not in sys.path:
        sys.path.insert(0, str(API_ROOT))
    module = importlib.import_module("scripts.seed_db")
    return cast(SeedFunction, module.seed)


async def init_and_seed_db(*, seed_if_empty: bool = True) -> None:
    """Upgrade to Alembic head and optionally seed an empty organization catalog."""
    async with engine.connect() as connection:
        await connection.run_sync(_validate_database_bootstrap)

    await asyncio.to_thread(_upgrade_database_to_head)

    if not seed_if_empty:
        return

    async with engine.connect() as connection:
        result = await connection.execute(sa.text("SELECT count(*) FROM organizations"))
        organization_count = result.scalar_one()

    if organization_count != 0:
        return

    logger.info("Database is empty. Evaluating optional canonical demo seed...")
    seed = _load_seed()
    seeded = await seed()
    if seeded:
        logger.info("Initial canonical demo seed completed.")
    else:
        logger.info("Canonical demo seed was disabled or already present.")

import contextlib
import os
import re
from datetime import datetime

import alembic.command
import clearcut.main
import pytest_asyncio
import sqlalchemy as sa
from clearcut.database import (
    DATABASE_URL as CONFIGURED_DATABASE_URL,
)
from clearcut.database import (
    LOCAL_SQLITE_URL,
    engine,
)
from clearcut.init_db import init_and_seed_db
from pydantic import SecretStr


# In tests, isolated Alembic schema migration tests (e.g. test_migrated_runtime_schema.py)
# construct their own Config instances pointing to temporary SQLite databases.
# However, alembic/env.py line 12 unconditionally overrides config's sqlalchemy.url
# with os.getenv("DATABASE_URL") if present in the environment.
# When running pytest against a real database (e.g. PostgreSQL), this causes Alembic
# to direct migrations/downgrades at the PostgreSQL test database rather than the test's
# SQLite database, corrupting the test suite.
# We wrap alembic.command functions so that during migration execution, os.environ["DATABASE_URL"]
# is aligned with the Config's explicit sqlalchemy.url, and restored immediately after.
def _wrap_alembic_command(fn):
    def wrapper(config, *args, **kwargs):
        target_url = config.get_main_option("sqlalchemy.url")
        old_env = os.environ.get("DATABASE_URL")
        try:
            if target_url:
                os.environ["DATABASE_URL"] = target_url
            return fn(config, *args, **kwargs)
        finally:
            if old_env is not None:
                os.environ["DATABASE_URL"] = old_env
            else:
                os.environ.pop("DATABASE_URL", None)

    return wrapper


for _cmd in ("upgrade", "downgrade", "stamp"):
    if hasattr(alembic.command, _cmd):
        setattr(alembic.command, _cmd, _wrap_alembic_command(getattr(alembic.command, _cmd)))

if CONFIGURED_DATABASE_URL != LOCAL_SQLITE_URL:
    _orig_create_app = clearcut.main.create_app

    def _test_create_app(settings, *args, **kwargs):
        if settings.database.url != SecretStr(CONFIGURED_DATABASE_URL):
            settings = settings.model_copy(
                update={
                    "database": settings.database.model_copy(
                        update={"url": SecretStr(CONFIGURED_DATABASE_URL)}
                    )
                }
            )
        return _orig_create_app(settings, *args, **kwargs)

    clearcut.main.create_app = _test_create_app

if engine.dialect.name == "postgresql":
    @sa.event.listens_for(engine.sync_engine, "connect")
    def _pg_connect(dbapi_conn, _record):
        async def _setup_codecs(connection):
            for type_name in ("uuid", "json", "jsonb"):
                await connection.set_type_codec(
                    type_name,
                    encoder=str,
                    decoder=str,
                    schema="pg_catalog",
                    format="text",
                )

        dbapi_conn.run_async(_setup_codecs)

    @sa.event.listens_for(engine.sync_engine, "before_cursor_execute", retval=True)
    def _pg_before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        if "payload_redacted LIKE" in statement:
            statement = statement.replace("payload_redacted LIKE", "CAST(payload_redacted AS text) LIKE")
        if "'CrossRunGate', 0," in statement:
            statement = statement.replace("'CrossRunGate', 0,", "'CrossRunGate', false,")
        if "STRFTIME" in statement:
            statement = re.sub(
                r"STRFTIME\('%Y-%m-%d %H:%M:%f',\s*'now',\s*'([^']+)'\)",
                lambda m: f"(clock_timestamp() + interval '{m.group(1).strip()}')",
                statement,
                flags=re.IGNORECASE,
            )
        if "SET created_at =" in statement or "SET lease_expires_at =" in statement:
            if isinstance(parameters, tuple):
                new_params = list(parameters)
                for idx, val in enumerate(new_params):
                    if isinstance(val, str) and (val.endswith("+00:00") or val.endswith("Z") or "2000-01-01" in val):
                        with contextlib.suppress(ValueError, TypeError):
                            new_params[idx] = datetime.fromisoformat(val)
                parameters = tuple(new_params)
            elif isinstance(parameters, dict):
                new_params = dict(parameters)
                for k, val in new_params.items():
                    if isinstance(val, str) and (val.endswith("+00:00") or val.endswith("Z") or "2000-01-01" in val):
                        with contextlib.suppress(ValueError, TypeError):
                            new_params[k] = datetime.fromisoformat(val)
                parameters = new_params
        return statement, parameters


def _tables_in_delete_order(connection: sa.Connection) -> list[str]:
    inspector = sa.inspect(connection)
    dependency_order = inspector.get_sorted_table_and_fkc_names()
    return [
        table_name
        for table_name, _foreign_keys in reversed(dependency_order)
        if table_name is not None and table_name != "alembic_version"
    ]


@pytest_asyncio.fixture(autouse=True)
async def clean_database():
    """Migrate with Alembic and clear all runtime data before each test."""
    await init_and_seed_db(seed_if_empty=False)
    # Self-referential RESTRICT foreign keys (e.g. script_versions.predecessor_version_id)
    # make a single bulk ``DELETE FROM`` fail under SQLite's per-row enforcement even
    # when tables are wiped in dependency order. Suspend enforcement for the wipe so the
    # whole runtime dataset can be cleared regardless of intra-table lineage links.
    dialect_name = engine.dialect.name
    if dialect_name == "sqlite":
        async with engine.connect() as conn:
            await conn.execute(sa.text("PRAGMA foreign_keys=OFF"))
            table_names = await conn.run_sync(_tables_in_delete_order)
            for table_name in table_names:
                await conn.execute(sa.text(f'DELETE FROM "{table_name}"'))
            await conn.commit()
            await conn.execute(sa.text("PRAGMA foreign_keys=ON"))
    else:
        async with engine.begin() as conn:
            table_names = await conn.run_sync(_tables_in_delete_order)
            if table_names:
                tables_str = ", ".join(f'"{t}"' for t in table_names)
                await conn.execute(sa.text(f"TRUNCATE TABLE {tables_str} CASCADE"))
    try:
        yield
    finally:
        await engine.dispose()

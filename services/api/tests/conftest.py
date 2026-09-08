import pytest_asyncio
import sqlalchemy as sa
from clearcut.database import engine
from clearcut.init_db import init_and_seed_db


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
            await conn.execute(sa.text("SET CONSTRAINTS ALL DEFERRED"))
            for table_name in table_names:
                await conn.execute(sa.text(f'DELETE FROM "{table_name}"'))
    yield

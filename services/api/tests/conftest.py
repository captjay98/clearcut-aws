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
    async with engine.begin() as conn:
        table_names = await conn.run_sync(_tables_in_delete_order)
        for table_name in table_names:
            await conn.execute(sa.text(f'DELETE FROM "{table_name}"'))
    yield

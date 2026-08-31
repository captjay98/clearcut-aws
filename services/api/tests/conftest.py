import pytest
import pytest_asyncio
import sqlalchemy as sa
from clearcut.database import engine, is_sqlite
from clearcut.init_db import init_and_seed_db


@pytest_asyncio.fixture(autouse=True)
async def clean_database():
    """Ensure database schema is initialized and tables are clean before each test."""
    await init_and_seed_db()
    async with engine.begin() as conn:
        tables = [
            "audit_events",
            "evidence_decisions",
            "evidence_claims",
            "source_snapshots",
            "research_runs",
            "clearance_items",
            "element_spans",
            "script_elements",
            "script_versions",
            "scripts",
            "project_grants",
            "invitations",
            "projects",
            "memberships",
            "organizations",
            "sessions",
            "local_credentials",
            "users",
        ]
        for t in tables:
            try:
                await conn.execute(sa.text(f"DELETE FROM {t}"))
            except Exception:
                pass
    yield

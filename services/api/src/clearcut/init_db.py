"""Database schema initialization and seed runner."""
import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from clearcut.database import engine, is_sqlite

logger = logging.getLogger(__name__)

CREATE_TABLES_SQL = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id UUID PRIMARY KEY,
        email VARCHAR(255) NOT NULL UNIQUE,
        created_at TIMESTAMPTZ NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS organizations (
        id UUID PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        slug VARCHAR(100) NOT NULL UNIQUE,
        created_at TIMESTAMPTZ NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS memberships (
        id UUID PRIMARY KEY,
        org_id UUID NOT NULL,
        user_id UUID NOT NULL,
        role VARCHAR(50) NOT NULL,
        status VARCHAR(50) NOT NULL,
        created_at TIMESTAMPTZ NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS projects (
        id UUID PRIMARY KEY,
        org_id UUID NOT NULL,
        title VARCHAR(255) NOT NULL,
        description TEXT,
        created_at TIMESTAMPTZ NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS scripts (
        id UUID PRIMARY KEY,
        org_id UUID NOT NULL,
        project_id UUID NOT NULL,
        title VARCHAR(255) NOT NULL,
        created_at TIMESTAMPTZ NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS script_versions (
        id UUID PRIMARY KEY,
        script_id UUID NOT NULL,
        org_id UUID NOT NULL,
        project_id UUID NOT NULL,
        ordinal INTEGER NOT NULL,
        source_hash VARCHAR(64) NOT NULL,
        parser_version VARCHAR(32) NOT NULL,
        created_at TIMESTAMPTZ NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS script_elements (
        id UUID PRIMARY KEY,
        version_id UUID NOT NULL,
        ordinal INTEGER NOT NULL,
        element_type VARCHAR(50) NOT NULL,
        text TEXT NOT NULL,
        scene_number INTEGER,
        page_number INTEGER
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS element_spans (
        id UUID PRIMARY KEY,
        element_id UUID NOT NULL,
        start_char INTEGER NOT NULL,
        end_char INTEGER NOT NULL,
        text TEXT NOT NULL,
        tag VARCHAR(100)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS clearance_items (
        id UUID PRIMARY KEY,
        org_id UUID NOT NULL,
        project_id UUID NOT NULL,
        script_id UUID NOT NULL,
        version_id UUID NOT NULL,
        element_id UUID,
        category VARCHAR(100) NOT NULL,
        text TEXT NOT NULL,
        status VARCHAR(100) NOT NULL,
        research_status VARCHAR(50) NOT NULL,
        workflow_status VARCHAR(50) NOT NULL,
        disposition_status VARCHAR(50) NOT NULL DEFAULT 'undisposed',
        assigned_to_user_id UUID,
        created_at TIMESTAMPTZ NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS research_runs (
        id UUID PRIMARY KEY,
        org_id UUID NOT NULL,
        project_id UUID NOT NULL,
        item_id UUID NOT NULL,
        status VARCHAR(50) NOT NULL,
        created_at TIMESTAMPTZ NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS source_snapshots (
        id UUID PRIMARY KEY,
        org_id UUID NOT NULL,
        project_id UUID NOT NULL,
        item_id UUID NOT NULL,
        run_id UUID NOT NULL,
        url TEXT NOT NULL,
        title TEXT NOT NULL,
        publisher VARCHAR(255),
        excerpt TEXT,
        origin VARCHAR(50) NOT NULL,
        sha256_hash VARCHAR(64) NOT NULL,
        retrieved_at TIMESTAMPTZ NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS evidence_claims (
        id UUID PRIMARY KEY,
        org_id UUID NOT NULL,
        project_id UUID NOT NULL,
        item_id UUID NOT NULL,
        snapshot_id UUID NOT NULL,
        stance VARCHAR(50) NOT NULL,
        authority_tier VARCHAR(100) NOT NULL,
        claim_text TEXT NOT NULL,
        provenance_excerpt TEXT,
        created_at TIMESTAMPTZ NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS evidence_decisions (
        id UUID PRIMARY KEY,
        org_id UUID NOT NULL,
        project_id UUID NOT NULL,
        item_id UUID NOT NULL,
        actor_id UUID NOT NULL,
        decision_type VARCHAR(50) NOT NULL,
        rationale TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS audit_events (
        id UUID PRIMARY KEY,
        org_id UUID NOT NULL,
        project_id UUID,
        action VARCHAR(100) NOT NULL,
        actor_id UUID NOT NULL,
        target_id UUID NOT NULL,
        target_type VARCHAR(100) NOT NULL,
        details JSON,
        created_at TIMESTAMPTZ NOT NULL
    );
    """
]

async def init_and_seed_db() -> None:
    """Ensure all required tables exist and populate initial canonical dataset if empty."""
    try:
        async with engine.begin() as conn:
            for ddl in CREATE_TABLES_SQL:
                if is_sqlite:
                    ddl_sql = (
                        ddl.replace("UUID", "TEXT")
                        .replace("TIMESTAMPTZ", "DATETIME")
                        .replace("JSON", "TEXT")
                    )
                else:
                    ddl_sql = ddl
                await conn.execute(sa.text(ddl_sql))

        # Check if organization table has data
        async with engine.connect() as conn:
            res = await conn.execute(sa.text("SELECT count(*) FROM organizations"))
            count = res.scalar() or 0

        if count == 0:
            logger.info("Database is empty. Running initial canonical seed...")
            from scripts.seed_db import seed
            await seed()
            logger.info("Initial canonical seed completed.")
    except Exception as e:
        logger.warning(f"Database auto-init note: {e}")

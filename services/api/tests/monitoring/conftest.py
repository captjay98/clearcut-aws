"""Shared seeding for monitoring persistence tests.

The tests directory has no package ``__init__``, so a seeded org/project/item
scope is shared through a fixture rather than a cross-module import. The full
chain (organization, project, script, version, element, clearance item) is
seeded because ``monitoring_source_deltas.item_id`` and the clearance item's own
scope foreign keys require it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest_asyncio
import sqlalchemy as sa
import uuid6
from clearcut.database import session_scope


async def seed_monitoring_scope() -> tuple[UUID, UUID, UUID, UUID]:
    """Seed org, project, script, version, element, a clearance item, and a user.

    Returns ``(org_id, project_id, item_id, actor_id)``. A real user row is
    seeded because the authoritative audit ledger's ``actor_id`` foreign-keys to
    ``users``.
    """
    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    script_id = uuid6.uuid7()
    version_id = uuid6.uuid7()
    element_id = uuid6.uuid7()
    item_id = uuid6.uuid7()
    actor_id = uuid6.uuid7()
    now = datetime.now(UTC)

    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO users (id, email, created_at) "
                "VALUES (:id, :email, :created_at)"
            ),
            {
                "id": str(actor_id),
                "email": f"reviewer-{str(actor_id)[:8]}@example.com",
                "created_at": now,
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO organizations (id, name, slug, created_at) "
                "VALUES (:id, :name, :slug, :created_at)"
            ),
            {
                "id": str(org_id),
                "name": f"Org {org_id}",
                "slug": f"org-{str(org_id)[:8]}",
                "created_at": now,
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO projects (id, org_id, title, created_at) "
                "VALUES (:id, :org_id, 'Monitoring project', :created_at)"
            ),
            {"id": str(project_id), "org_id": str(org_id), "created_at": now},
        )
        await session.execute(
            sa.text(
                "INSERT INTO scripts (id, org_id, project_id, title, created_at, current_slot) "
                "VALUES (:id, :org_id, :project_id, 'Script', :created_at, 'current')"
            ),
            {
                "id": str(script_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "created_at": now,
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO script_versions "
                "(id, script_id, org_id, project_id, ordinal, source_hash, parser_version, "
                "created_at) VALUES "
                "(:id, :script_id, :org_id, :project_id, 1, :source_hash, 'v1', :created_at)"
            ),
            {
                "id": str(version_id),
                "script_id": str(script_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "source_hash": f"{1:064d}",
                "created_at": now,
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO script_elements (id, version_id, ordinal, element_type, text) "
                "VALUES (:id, :version_id, 1, 'action', 'Coca-Cola')"
            ),
            {"id": str(element_id), "version_id": str(version_id)},
        )
        await session.execute(
            sa.text(
                "INSERT INTO clearance_items "
                "(id, org_id, project_id, script_id, version_id, element_id, category, text, "
                "status, created_at, version) VALUES "
                "(:id, :org_id, :project_id, :script_id, :version_id, :element_id, "
                "'products_and_trademarks', 'Coca-Cola', 'researched', :created_at, 1)"
            ),
            {
                "id": str(item_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "script_id": str(script_id),
                "version_id": str(version_id),
                "element_id": str(element_id),
                "created_at": now,
            },
        )

    return org_id, project_id, item_id, actor_id


@pytest_asyncio.fixture
async def seeded_monitoring_scope() -> tuple[UUID, UUID, UUID, UUID]:
    """Fixture wrapper around :func:`seed_monitoring_scope`."""
    return await seed_monitoring_scope()

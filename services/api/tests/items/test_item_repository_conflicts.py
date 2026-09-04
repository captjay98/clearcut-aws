"""Adapter-level conflict-branch tests for the governed item-assignment slice.

The end-to-end behavioral tests (``test_item_assignment_commands.py``) drive the
mounted ``:assign`` route sequentially, so they exercise the shared kernel's
``classify_command`` stale/replay decision but never the *adapter's* own
concurrency branches. In the sequential flow a stale ``expected_version`` is
caught by ``classify_command`` in the application layer *before*
``commit_assignment`` is ever called, and an absent/foreign item fails at
``load_scoped_item`` *before* the compare-and-swap. So the adapter's own CAS-miss
branches — the version-guarded UPDATE that affects zero rows because the row
moved between load and update — are not genuinely covered by the route tests.

Those branches only fire under real interleaving: a concurrent writer advancing
the item version (or deleting the row) in the window after this transaction
classified the command as a fresh write at a version it had already observed.
These tests drive those adapter branches directly and deterministically against
the real migrated schema:

* A CAS miss where the scoped item still exists must surface a typed
  :class:`StaleVersionConflictError` (HTTP 409), never a not-found (HTTP 404):
  the resource is present but its version moved. This is proven two ways —
  with a stale ``expected_version`` and with a genuine concurrent version bump
  performed in a separate session between load and commit.
* A CAS miss where the row was deleted from the scope between load and commit
  must stay a typed :class:`CommandNotFoundError` (HTTP 404), preserving safe
  not-found parity even though the item was visible when it was first loaded.

They are explicit, documented unit tests of the adapter's conflict handling so
the conflict branches are genuinely covered rather than only ``classify_command``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
import uuid6
from clearcut.commanding.errors import (
    CommandNotFoundError,
    StaleVersionConflictError,
)
from clearcut.database import session_scope
from clearcut.init_db import init_and_seed_db
from clearcut.items.adapters.sql_command_repository import SqlItemCommandRepository
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _seed_scoped_item(session: AsyncSession) -> tuple[UUID, UUID, UUID, UUID]:
    """Seed the minimal scope chain and one clearance item at version 1.

    Returns ``(org_id, project_id, actor_id, item_id)`` so tests can address the
    adapter with the exact tenant-and-project scope tuple.
    """
    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    actor_id = uuid6.uuid7()
    script_id = uuid6.uuid7()
    version_id = uuid6.uuid7()
    element_id = uuid6.uuid7()
    item_id = uuid6.uuid7()
    now = datetime.now(UTC)

    await session.execute(
        sa.text("INSERT INTO users (id, email, created_at) VALUES (:id, :email, :created_at)"),
        {"id": str(actor_id), "email": f"actor-{uuid4().hex}@example.com", "created_at": now},
    )
    await session.execute(
        sa.text(
            "INSERT INTO organizations (id, name, slug, created_at) "
            "VALUES (:id, :name, :slug, :created_at)"
        ),
        {
            "id": str(org_id),
            "name": "Adapter Studio",
            "slug": f"adapter-{uuid4().hex[:8]}",
            "created_at": now,
        },
    )
    await session.execute(
        sa.text(
            "INSERT INTO projects (id, org_id, title, created_at) "
            "VALUES (:id, :org_id, :title, :created_at)"
        ),
        {"id": str(project_id), "org_id": str(org_id), "title": "Adapter", "created_at": now},
    )
    await session.execute(
        sa.text(
            "INSERT INTO scripts (id, org_id, project_id, title, created_at) "
            "VALUES (:id, :org_id, :project_id, :title, :created_at)"
        ),
        {
            "id": str(script_id),
            "org_id": str(org_id),
            "project_id": str(project_id),
            "title": "Draft",
            "created_at": now,
        },
    )
    await session.execute(
        sa.text(
            "INSERT INTO script_versions "
            "(id, script_id, org_id, project_id, ordinal, source_hash, parser_version, created_at) "
            "VALUES (:id, :script_id, :org_id, :project_id, 1, :source_hash, 'v1', :created_at)"
        ),
        {
            "id": str(version_id),
            "script_id": str(script_id),
            "org_id": str(org_id),
            "project_id": str(project_id),
            "source_hash": "f" * 64,
            "created_at": now,
        },
    )
    await session.execute(
        sa.text(
            "INSERT INTO script_elements (id, version_id, ordinal, element_type, text) "
            "VALUES (:id, :version_id, 1, 'action', 'Acme Corporation')"
        ),
        {"id": str(element_id), "version_id": str(version_id)},
    )
    await session.execute(
        sa.text(
            "INSERT INTO clearance_items "
            "(id, org_id, project_id, script_id, version_id, element_id, category, text, "
            "status, research_status, workflow_status, disposition_status, created_at, version) "
            "VALUES (:id, :org_id, :project_id, :script_id, :version_id, :element_id, "
            "'products_and_trademarks', 'Acme Corporation', 'unresolved', 'completed', "
            "'detected', 'undisposed', :created_at, 1)"
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
    return org_id, project_id, actor_id, item_id


# --------------------------------------------------------------------------- #
# CAS miss on a present item is a stale-version conflict (409), not a 404.
# --------------------------------------------------------------------------- #


async def test_commit_cas_miss_on_present_item_raises_stale_version_conflict() -> None:
    """Directly drive the adapter's version-guarded CAS miss.

    The item exists in scope at version 1, but the caller commits against a
    stale ``expected_version`` (simulating a concurrent writer that advanced the
    row after this transaction loaded it). The UPDATE affects zero rows, and the
    adapter must classify a *present* item's CAS miss as a typed stale-version
    conflict, never a not-found: the resource is visible, only its version moved.
    """
    await init_and_seed_db(seed_if_empty=False)
    repository = SqlItemCommandRepository()
    async with session_scope() as session:
        org_id, project_id, _actor_id, item_id = await _seed_scoped_item(session)
        with pytest.raises(StaleVersionConflictError):
            await repository.commit_assignment(
                session,
                org_id=org_id,
                project_id=project_id,
                item_id=item_id,
                assigned_to_user_id=None,
                # The row is at version 1; guard on a version that no longer
                # matches so the CAS misses while the item still exists.
                expected_version=99,
                resulting_version=100,
            )


async def test_commit_cas_miss_after_concurrent_version_bump_is_stale_conflict() -> None:
    """Drive the CAS miss through a genuine concurrent version bump.

    The adapter loads the item at version 1, then a *separate* committed session
    advances the item's version (the interleaving the sequential route flow can
    never produce). When the first caller then commits its compare-and-swap
    against the version it observed (1), the UPDATE affects zero rows because the
    row moved under it, and the adapter must raise a typed stale-version conflict
    for the still-present item.
    """
    await init_and_seed_db(seed_if_empty=False)
    repository = SqlItemCommandRepository()
    async with session_scope() as session:
        org_id, project_id, _actor_id, item_id = await _seed_scoped_item(session)

    async with session_scope() as session:
        # This transaction loads the item at its current version (1).
        loaded = await repository.load_scoped_item(
            session,
            org_id=org_id,
            project_id=project_id,
            item_id=item_id,
        )
        assert loaded.version == 1

        # A concurrent writer advances the version in a separate committed
        # transaction, in the window after the load above.
        async with session_scope() as concurrent:
            await concurrent.execute(
                sa.text(
                    "UPDATE clearance_items SET version = version + 1 "
                    "WHERE id = :id AND org_id = :org_id AND project_id = :project_id"
                ),
                {"id": str(item_id), "org_id": str(org_id), "project_id": str(project_id)},
            )

        # Committing against the version we loaded (1) now misses: the row moved,
        # but it is still present, so this is a stale-version conflict, not a 404.
        with pytest.raises(StaleVersionConflictError):
            await repository.commit_assignment(
                session,
                org_id=org_id,
                project_id=project_id,
                item_id=item_id,
                assigned_to_user_id=None,
                expected_version=loaded.version,
                resulting_version=loaded.version + 1,
            )


# --------------------------------------------------------------------------- #
# CAS miss on a row deleted from scope stays a neutral not-found (404).
# --------------------------------------------------------------------------- #


async def test_commit_cas_miss_after_row_deletion_is_not_found() -> None:
    """Drive the CAS miss through a concurrent row deletion.

    The adapter loads the item, then a *separate* committed session deletes the
    row from the scope (the interleaving the sequential route flow cannot
    produce: it fails at ``load_scoped_item`` instead). When the first caller
    then commits its compare-and-swap, the UPDATE affects zero rows because the
    row is gone, and the scoped-existence probe finds nothing — so the miss must
    stay a neutral not-found, never be mislabelled as a stale-version conflict.
    """
    await init_and_seed_db(seed_if_empty=False)
    repository = SqlItemCommandRepository()
    async with session_scope() as session:
        org_id, project_id, _actor_id, item_id = await _seed_scoped_item(session)

    async with session_scope() as session:
        loaded = await repository.load_scoped_item(
            session,
            org_id=org_id,
            project_id=project_id,
            item_id=item_id,
        )
        assert loaded.version == 1

        # A concurrent writer deletes the row in a separate committed
        # transaction, in the window after the load above.
        async with session_scope() as concurrent:
            await concurrent.execute(
                sa.text(
                    "DELETE FROM clearance_items "
                    "WHERE id = :id AND org_id = :org_id AND project_id = :project_id"
                ),
                {"id": str(item_id), "org_id": str(org_id), "project_id": str(project_id)},
            )

        # The compare-and-swap misses and the scoped-existence probe finds
        # nothing: a genuinely absent item keeps neutral not-found parity.
        with pytest.raises(CommandNotFoundError):
            await repository.commit_assignment(
                session,
                org_id=org_id,
                project_id=project_id,
                item_id=item_id,
                assigned_to_user_id=None,
                expected_version=loaded.version,
                resulting_version=loaded.version + 1,
            )

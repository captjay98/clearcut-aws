"""Adapter-level conflict-branch tests for the governed evidence-decision slice.

The end-to-end behavioral tests (``test_governed_evidence_decision.py``) drive
the mounted route sequentially, so they exercise the shared kernel's
``classify_command`` stale/replay decision but never the *adapter's* own
concurrency branches: the version-guarded compare-and-swap that misses because
the row moved between load and update, and the idempotency-receipt insert that
loses a unique-constraint race. Those branches only fire under genuine
interleaving (a concurrent writer advancing the version or committing a receipt
in the window after this transaction classified the command as a fresh write).

These tests drive those adapter branches directly and deterministically against
the real migrated schema by simulating the concurrent mutation the sequential
route flow cannot produce:

* A CAS miss where the scoped item still exists must surface a typed
  :class:`StaleVersionConflictError` (HTTP 409), never a not-found (HTTP 404):
  the resource is present but its version moved.
* A duplicate idempotency receipt for the same scope/intent must be reconciled
  into the prior receipt's idempotent replay, never a raw ``IntegrityError``
  bubbling out as a 500.

They are explicit, documented unit tests of the adapter's conflict handling so
the conflict branches are genuinely covered rather than only ``classify_command``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
import uuid6
from clearcut.commanding.domain import CommandEnvelope
from clearcut.commanding.errors import (
    CommandNotFoundError,
    StaleVersionConflictError,
)
from clearcut.commanding.sql import insert_command_receipt, lookup_command_receipt
from clearcut.database import session_scope
from clearcut.decisions.adapters.sql_repository import SqlDecisionRepository
from clearcut.init_db import init_and_seed_db
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio

_VALID_INTENT_HASH = "a" * 64
_OPERATION = "decision.evidence.record"


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


def _envelope(*, org_id: UUID, project_id: UUID, actor_id: UUID) -> CommandEnvelope:
    return CommandEnvelope(
        org_id=org_id,
        project_id=project_id,
        actor_id=actor_id,
        operation=_OPERATION,
        idempotency_key=f"idem-adapter-{uuid4().hex}",
        intent_hash=_VALID_INTENT_HASH,
        expected_version=1,
    )


# --------------------------------------------------------------------------- #
# Finding 1: CAS miss on a present item is a stale-version conflict (409), not
# a not-found (404).
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
    repository = SqlDecisionRepository()
    async with session_scope() as session:
        org_id, project_id, actor_id, item_id = await _seed_scoped_item(session)
        with pytest.raises(StaleVersionConflictError):
            await repository.commit_decision(
                session,
                decision_id=uuid6.uuid7(),
                org_id=org_id,
                project_id=project_id,
                item_id=item_id,
                actor_id=actor_id,
                decision_value="further_review_required",
                rationale="Concurrent writer advanced the version.",
                # The row is at version 1; guard on a version that no longer
                # matches so the CAS misses while the item still exists.
                expected_version=99,
                resulting_version=100,
                next_status="in_review",
                occurred_at=datetime.now(UTC),
            )


async def test_cas_miss_classification_when_item_absent_from_scope_is_not_found() -> None:
    """A CAS miss for an item that is genuinely absent from the scope stays a
    typed not-found, preserving safe not-found parity.

    The adapter's scoped-existence probe classifies the CAS miss: a foreign or
    deleted item (nothing visible in this ``(org, project)`` scope) is a
    not-found, never mislabelled as a stale-version conflict. This drives the
    classification probe directly, because a genuinely absent item can never
    reach the compare-and-swap through ``commit_decision`` — the decision
    record's ``(item_id, org_id, project_id)`` foreign key already blocks the
    insert — so the not-found branch is only reachable via the probe itself.
    """
    await init_and_seed_db(seed_if_empty=False)
    repository = SqlDecisionRepository()
    async with session_scope() as session:
        org_id, project_id, actor_id, _item_id = await _seed_scoped_item(session)
        # An item id that does not exist within this (org, project) scope: the
        # scoped-existence probe finds nothing, so the CAS miss is a not-found.
        absent_item_id = uuid6.uuid7()
        with pytest.raises(CommandNotFoundError):
            await repository.classify_cas_miss(
                session,
                org_id=org_id,
                project_id=project_id,
                item_id=absent_item_id,
            )


async def test_cas_miss_classification_when_item_present_is_stale_version() -> None:
    """The scoped-existence probe classifies a present item's CAS miss as a
    typed stale-version conflict, mirroring the branch ``commit_decision`` takes
    when its version-guarded UPDATE affects zero rows for a still-present item.
    """
    await init_and_seed_db(seed_if_empty=False)
    repository = SqlDecisionRepository()
    async with session_scope() as session:
        org_id, project_id, actor_id, item_id = await _seed_scoped_item(session)
        with pytest.raises(StaleVersionConflictError):
            await repository.classify_cas_miss(
                session,
                org_id=org_id,
                project_id=project_id,
                item_id=item_id,
            )


# --------------------------------------------------------------------------- #
# Finding 2: a duplicate idempotency receipt for the same scope/intent is
# reconciled into the prior receipt (replay), never a raw IntegrityError.
# --------------------------------------------------------------------------- #


async def test_persist_receipt_reconciles_duplicate_scope_into_prior_receipt() -> None:
    """Drive the receipt-unique race directly.

    A concurrent transaction is simulated by pre-inserting a receipt for the
    exact ``(org, project, actor, operation, idempotency_key)`` scope. When the
    adapter then tries to persist its own receipt for the same scope, the unique
    constraint is violated; instead of letting the ``IntegrityError`` escape as
    a 500, the adapter must roll the failed insert back to a savepoint, re-read
    the prior receipt, and return it so the caller can replay the original
    idempotent result.
    """
    await init_and_seed_db(seed_if_empty=False)
    repository = SqlDecisionRepository()
    prior_result_id = uuid6.uuid7()
    async with session_scope() as session:
        org_id, project_id, actor_id, item_id = await _seed_scoped_item(session)
        envelope = _envelope(org_id=org_id, project_id=project_id, actor_id=actor_id)
        # A concurrent writer already committed the receipt for this exact scope.
        await insert_command_receipt(
            session,
            envelope,
            item_id=item_id,
            resulting_version=2,
            result_id=prior_result_id,
            occurred_at=datetime.now(UTC),
        )

        # The adapter's own receipt insert for the same scope loses the race and
        # must reconcile to the prior receipt rather than raise.
        prior = await repository.persist_receipt_idempotent(
            session,
            envelope,
            item_id=item_id,
            resulting_version=3,
            result_id=uuid6.uuid7(),
            occurred_at=datetime.now(UTC),
        )

    assert prior is not None
    assert prior.result_id == prior_result_id
    assert prior.resulting_version == 2


async def test_persist_receipt_inserts_when_no_prior_exists() -> None:
    """When there is no conflicting receipt, the adapter persists its own and
    returns ``None`` (no replay), so the caller proceeds with the fresh result.
    """
    await init_and_seed_db(seed_if_empty=False)
    repository = SqlDecisionRepository()
    fresh_result_id = uuid6.uuid7()
    async with session_scope() as session:
        org_id, project_id, actor_id, item_id = await _seed_scoped_item(session)
        envelope = _envelope(org_id=org_id, project_id=project_id, actor_id=actor_id)
        prior = await repository.persist_receipt_idempotent(
            session,
            envelope,
            item_id=item_id,
            resulting_version=2,
            result_id=fresh_result_id,
            occurred_at=datetime.now(UTC),
        )
        assert prior is None
        # The fresh receipt is durably present in the same transaction.
        roundtrip = await lookup_command_receipt(session, envelope)
    assert roundtrip is not None
    assert roundtrip.result_id == fresh_result_id

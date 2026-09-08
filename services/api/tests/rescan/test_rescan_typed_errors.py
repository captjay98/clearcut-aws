"""Regression coverage for two durable-selective-rescan production defects.

Both tests are provider-free and touch no Parallel/Gemini/network/cloud
dependency. They pin the two confirmed defects that block the durable
``selective_rescan`` job for a realistic revision:

* Defect 1 (correctness): the item-lineage coordinator must carry forward
  evidence only for carryable elements that actually have a predecessor
  clearance item, and simply SKIP carryable elements that have none (an
  unchanged NARRATIVE line legitimately has no item because detection only
  creates items on brand/entity lines). It must NOT raise
  ``predecessor_item_not_found`` for an item-less carryable element.
* Defect 2 (error masking): ``RescanSafeError`` must survive propagation through
  an ``async with session_scope()`` block. A frozen-dataclass exception cannot
  have ``__traceback__`` assigned, so the context manager's ``__aexit__`` raises
  ``FrozenInstanceError`` and the typed error is lost, surfacing as an opaque
  ``execution_failed`` instead of the intended typed :class:`SafeJobError`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
import sqlalchemy as sa
import uuid6
from clearcut.database import session_scope
from clearcut.detection.adapters.sql_rescan_lineage import SqlItemLineageAdapter
from clearcut.main import _SelectiveRescanItemLineageCoordinator
from clearcut.operations.application.run_job import RunJobService
from clearcut.operations.domain.jobs import RunStatus
from clearcut.operations.ports.job_repository import EnqueueJob
from clearcut.rescan.application.models import (
    CarriedItemMapping,
    CarryableElement,
    RescanSafeError,
)
from clearcut.rescan.application.run_rescan_job import RunSelectiveRescanJobService

pytestmark = pytest.mark.asyncio


# --------------------------------------------------------------------------- #
# Defect 2 — typed error survives context-manager propagation
# --------------------------------------------------------------------------- #


async def test_rescan_safe_error_survives_session_scope_propagation() -> None:
    """A RescanSafeError raised inside session_scope must propagate intact.

    Python assigns ``__traceback__`` on the exception as it unwinds through the
    ``async with session_scope()`` ``__aexit__``. A frozen-dataclass exception
    rejects that assignment with ``FrozenInstanceError``, replacing the typed
    error. After the fix the original typed error propagates unchanged.
    """
    original = RescanSafeError(
        code="predecessor_item_not_found",
        message="A carryable element has no predecessor clearance item in scope.",
        retryable=False,
    )

    with pytest.raises(RescanSafeError) as caught:
        async with session_scope():
            raise original

    assert caught.value is original
    assert caught.value.code == "predecessor_item_not_found"
    assert caught.value.retryable is False


class _RaisingItemLineage:
    """A typed item-lineage double that raises a genuine RescanSafeError."""

    async def materialize(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        script_id: UUID,
        before_version_id: UUID,
        after_version_id: UUID,
        carryable_elements: tuple[CarryableElement, ...],
    ) -> tuple[CarriedItemMapping, ...]:
        del (
            org_id,
            project_id,
            script_id,
            before_version_id,
            after_version_id,
            carryable_elements,
        )
        # Raise inside a real session scope so the traceback-assignment path is
        # exercised exactly as production does.
        async with session_scope():
            raise RescanSafeError(
                code="predecessor_item_not_found",
                message="A carryable element has no predecessor clearance item in scope.",
                retryable=False,
            )


class _UnusedPort:
    """A stand-in for rescan ports that must never be reached on failure."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"unexpected call to {name} after a typed lineage failure")


async def _enqueue_selective_rescan_job(
    repository: Any, *, org_id: UUID, project_id: UUID, actor_id: UUID, after_version_id: UUID
) -> UUID:
    result = await repository.enqueue(
        EnqueueJob(
            org_id=org_id,
            project_id=project_id,
            actor_id=actor_id,
            job_type="selective_rescan",
            idempotency_key=f"selective_rescan:{after_version_id}",
            payload={
                "schemaVersion": 1,
                "target": {"type": "script_version", "id": str(after_version_id)},
            },
            audit_action="selective_rescan.started",
            target_type="script_version",
            target_id=after_version_id,
        )
    )
    return result.job.job_id


async def test_typed_rescan_failure_maps_to_typed_safe_job_error_not_execution_failed() -> None:
    """A genuine typed RescanSafeError must surface as its typed SafeJobError.

    Driven through the real ``RunJobService`` so the whole failure path
    (processor -> JobExecutionError -> repository.fail) runs. A frozen
    RescanSafeError would be masked into ``execution_failed`` by the kernel's
    bare ``except Exception`` after ``FrozenInstanceError`` replaces it.
    """
    from clearcut.operations.adapters.sql_job_repository import SqlJobRepository
    from clearcut.rescan.adapters.sql_repository import SqlSelectiveRescanRepository

    job_repository = SqlJobRepository()
    checkpoints = SqlSelectiveRescanRepository()

    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    actor_id = uuid6.uuid7()
    after_version_id = uuid6.uuid7()

    await _seed_org_project(org_id=org_id, project_id=project_id)
    await _seed_actor(actor_id=actor_id)

    # A revision-plan double so lineage materialization is the first real stage.
    class _RevisionPlan:
        async def load_revision_plan(
            self, *, org_id: UUID, project_id: UUID, after_version_id: UUID
        ):
            from clearcut.rescan.application.models import CarryableElementPair, RevisionPlan

            return RevisionPlan(
                org_id=org_id,
                project_id=project_id,
                script_id=uuid6.uuid7(),
                before_version_id=uuid6.uuid7(),
                after_version_id=after_version_id,
                algorithm_version="element-lineage-v1",
                carryable_elements=(
                    CarryableElementPair(
                        before_element_id=uuid6.uuid7(),
                        after_element_id=uuid6.uuid7(),
                        before_text="Unchanged",
                        after_text="Unchanged",
                    ),
                ),
                affected_element_ids=frozenset(),
                removed_element_ids=frozenset(),
            )

    processor = RunSelectiveRescanJobService(
        revision_plan=_RevisionPlan(),
        materialize_items=_RaisingItemLineage(),
        carry_evidence=_UnusedPort(),
        child_work=_UnusedPort(),
        repository=checkpoints,
        job_repository=job_repository,
    )

    job_id = await _enqueue_selective_rescan_job(
        job_repository,
        org_id=org_id,
        project_id=project_id,
        actor_id=actor_id,
        after_version_id=after_version_id,
    )

    service = RunJobService(
        repository=job_repository,
        processors={"selective_rescan": processor},
        lease_owner="test-worker",
        heartbeat_interval_seconds=3600.0,
    )
    record = await service.run(job_id, org_id, project_id)

    assert record.status is RunStatus.FAILED
    assert record.error is not None
    assert record.error.code == "predecessor_item_not_found"
    assert record.error.code != "execution_failed"


# --------------------------------------------------------------------------- #
# Defect 1 — item-less carryable elements are skipped, not fatal
# --------------------------------------------------------------------------- #


class _CapturingItemLineageAdapter:
    """Wraps the real adapter to capture what materialize_carried_items receives."""

    def __init__(self) -> None:
        self._inner = SqlItemLineageAdapter()
        self.received: tuple[CarryableElement, ...] = ()

    async def materialize_carried_items(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        script_id: UUID,
        before_version_id: UUID,
        after_version_id: UUID,
        carryable_elements: tuple[CarryableElement, ...],
    ) -> tuple[CarriedItemMapping, ...]:
        self.received = carryable_elements
        return await self._inner.materialize_carried_items(
            org_id=org_id,
            project_id=project_id,
            script_id=script_id,
            before_version_id=before_version_id,
            after_version_id=after_version_id,
            carryable_elements=carryable_elements,
        )


async def _seed_actor(*, actor_id: UUID) -> None:
    async with session_scope() as session:
        await session.execute(
            sa.text("INSERT INTO users (id, email, created_at) VALUES (:id, :email, :created)"),
            {
                "id": str(actor_id),
                "email": f"actor-{actor_id}@example.com",
                "created": datetime.now(UTC),
            },
        )


async def _seed_org_project(*, org_id: UUID, project_id: UUID) -> None:
    now = datetime.now(UTC)
    async with session_scope() as session:
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
                "VALUES (:id, :org_id, :title, :created_at)"
            ),
            {
                "id": str(project_id),
                "org_id": str(org_id),
                "title": "Item-less carryable project",
                "created_at": now,
            },
        )


async def _seed_version(
    *,
    org_id: UUID,
    project_id: UUID,
    script_id: UUID,
    version_id: UUID,
    ordinal: int,
    predecessor_version_id: UUID | None,
    predecessor_ordinal: int | None,
    create_script: bool,
) -> None:
    now = datetime.now(UTC)
    async with session_scope() as session:
        if create_script:
            await session.execute(
                sa.text(
                    "INSERT INTO scripts (id, org_id, project_id, title, created_at, "
                    "current_slot) VALUES (:id, :org_id, :project_id, 'Item-less Carryable', "
                    ":created_at, 'current')"
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
                "created_at, predecessor_version_id, predecessor_ordinal) VALUES "
                "(:id, :script_id, :org_id, :project_id, :ordinal, :source_hash, 'v1', "
                ":created_at, :predecessor_version_id, :predecessor_ordinal)"
            ),
            {
                "id": str(version_id),
                "script_id": str(script_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "ordinal": ordinal,
                "source_hash": f"{ordinal:064d}",
                "created_at": now,
                "predecessor_version_id": (
                    str(predecessor_version_id) if predecessor_version_id else None
                ),
                "predecessor_ordinal": predecessor_ordinal,
            },
        )


async def _seed_element(*, version_id: UUID, element_id: UUID, ordinal: int, text: str) -> None:
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO script_elements (id, version_id, ordinal, element_type, text) "
                "VALUES (:id, :version_id, :ordinal, 'action', :text)"
            ),
            {
                "id": str(element_id),
                "version_id": str(version_id),
                "ordinal": ordinal,
                "text": text,
            },
        )


async def _seed_item(
    *,
    org_id: UUID,
    project_id: UUID,
    script_id: UUID,
    version_id: UUID,
    element_id: UUID,
    item_id: UUID,
    category: str,
    text: str,
) -> None:
    now = datetime.now(UTC)
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO clearance_items "
                "(id, org_id, project_id, script_id, version_id, element_id, category, text, "
                "status, research_status, workflow_status, disposition_status, created_at, "
                "version) VALUES "
                "(:id, :org_id, :project_id, :script_id, :version_id, :element_id, :category, "
                ":text, 'unresolved', 'completed', 'open', 'undisposed', :created_at, 1)"
            ),
            {
                "id": str(item_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "script_id": str(script_id),
                "version_id": str(version_id),
                "element_id": str(element_id),
                "category": category,
                "text": text,
                "created_at": now,
            },
        )


async def test_item_less_carryable_element_is_skipped_not_fatal() -> None:
    """A carryable set with one item-bearing and one item-less unchanged element.

    A realistic revision has unchanged NARRATIVE lines that never held a
    clearance item (detection only creates items on brand/entity lines). The
    coordinator must carry forward ONLY the item-bearing element and SKIP the
    item-less one, never raising ``predecessor_item_not_found``.
    """
    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    script_id = uuid6.uuid7()
    before_version_id = uuid6.uuid7()
    after_version_id = uuid6.uuid7()

    # One carryable element WITH a predecessor brand item; one WITHOUT (an
    # unchanged narrative line that never held an item).
    item_bearing_before = uuid6.uuid7()
    item_bearing_after = uuid6.uuid7()
    item_less_before = uuid6.uuid7()
    item_less_after = uuid6.uuid7()
    predecessor_item_id = uuid6.uuid7()

    await _seed_org_project(org_id=org_id, project_id=project_id)
    await _seed_version(
        org_id=org_id,
        project_id=project_id,
        script_id=script_id,
        version_id=before_version_id,
        ordinal=1,
        predecessor_version_id=None,
        predecessor_ordinal=None,
        create_script=True,
    )
    await _seed_version(
        org_id=org_id,
        project_id=project_id,
        script_id=script_id,
        version_id=after_version_id,
        ordinal=2,
        predecessor_version_id=before_version_id,
        predecessor_ordinal=1,
        create_script=False,
    )

    await _seed_element(
        version_id=before_version_id,
        element_id=item_bearing_before,
        ordinal=1,
        text="Vera studies the file, a Rolex glinting on her wrist.",
    )
    await _seed_element(
        version_id=before_version_id,
        element_id=item_less_before,
        ordinal=2,
        text="Every case leaves a mark. This one left a scar.",
    )
    await _seed_element(
        version_id=after_version_id,
        element_id=item_bearing_after,
        ordinal=1,
        text="Vera studies the file, a Rolex glinting on her wrist.",
    )
    await _seed_element(
        version_id=after_version_id,
        element_id=item_less_after,
        ordinal=2,
        text="Every case leaves a mark. This one left a scar.",
    )

    await _seed_item(
        org_id=org_id,
        project_id=project_id,
        script_id=script_id,
        version_id=before_version_id,
        element_id=item_bearing_before,
        item_id=predecessor_item_id,
        category="products_and_trademarks",
        text="Rolex",
    )

    adapter = _CapturingItemLineageAdapter()
    coordinator = _SelectiveRescanItemLineageCoordinator(adapter)  # type: ignore[arg-type]

    carryable = (
        CarryableElement(
            before_element_id=item_bearing_before,
            after_element_id=item_bearing_after,
            predecessor_item_id=item_bearing_before,
            category="",
            text="Vera studies the file, a Rolex glinting on her wrist.",
        ),
        CarryableElement(
            before_element_id=item_less_before,
            after_element_id=item_less_after,
            predecessor_item_id=item_less_before,
            category="",
            text="Every case leaves a mark. This one left a scar.",
        ),
    )

    mappings = await coordinator.materialize(
        org_id=org_id,
        project_id=project_id,
        script_id=script_id,
        before_version_id=before_version_id,
        after_version_id=after_version_id,
        carryable_elements=carryable,
    )

    # Only the item-bearing carryable element is materialized and passed down.
    assert len(adapter.received) == 1
    assert adapter.received[0].before_element_id == item_bearing_before
    assert adapter.received[0].predecessor_item_id == predecessor_item_id
    assert len(mappings) == 1
    assert mappings[0].predecessor_item_id == predecessor_item_id
    assert mappings[0].after_element_id == item_bearing_after

    # The item-less carryable element persists no successor row.
    async with session_scope() as session:
        successor_count = (
            await session.execute(
                sa.text(
                    "SELECT COUNT(*) FROM clearance_items "
                    "WHERE version_id = :after AND element_id = :element"
                ),
                {"after": str(after_version_id), "element": str(item_less_after)},
            )
        ).scalar_one()
    assert int(successor_count) == 0

"""Typed ports for durable selective-rescan checkpoint persistence and work.

The durable rescan processor advances through the seven approved
:class:`~clearcut.rescan.application.models.RescanStage` values and persists a
checkpoint per stage *before* the next stage runs, so a reload through a fresh
process replays only the stages that have not yet succeeded. All values crossing
these boundaries are immutable dataclasses or typed errors — no booleans,
``None`` sentinels, or raw dictionaries encode an outcome.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from clearcut.rescan.application.models import (
    CarriedItemMapping,
    CarryableElement,
    ElementId,
    ItemId,
    OrgId,
    ProjectId,
    RescanStage,
    VersionId,
)


@dataclass(frozen=True)
class RescanChildWorkTicket:
    """A durable, idempotent handle to child rescan work for one item.

    ``idempotency_key`` is stable across retries so a reload never enqueues a
    duplicate child detection/research job or provider call for the same item.
    """

    item_id: ItemId
    idempotency_key: str


@dataclass(frozen=True)
class RescanStageCheckpoint:
    """A persisted stage checkpoint loaded on replay.

    ``status`` is one of ``pending``/``running``/``succeeded``/``failed`` exactly
    as the ``selective_rescan_checkpoints`` state check constraint allows.
    """

    stage: RescanStage
    status: str


class SelectiveRescanRepositoryPort(Protocol):
    """Persists and reads scoped, per-stage selective-rescan checkpoints."""

    async def load_stage_history(
        self,
        *,
        org_id: OrgId,
        project_id: ProjectId,
        job_id: ItemId,
    ) -> list[tuple[RescanStage, str]]:
        """Return the persisted ``(stage, status)`` history for a rescan job.

        Scope is enforced before any access; only checkpoints owned by the
        requested organization/project/job are returned, ordered by stage
        progression.
        """
        ...

    async def completed_stages(
        self,
        *,
        org_id: OrgId,
        project_id: ProjectId,
        job_id: ItemId,
    ) -> frozenset[RescanStage]:
        """Return the set of stages already recorded as ``succeeded``."""
        ...

    async def record_stage_success(
        self,
        *,
        org_id: OrgId,
        project_id: ProjectId,
        job_id: ItemId,
        stage: RescanStage,
        attempt_number: int,
        result: dict[str, object],
    ) -> None:
        """Persist a succeeded stage checkpoint before the next stage runs.

        Idempotent on the migration-0035 partial-unique stage key, so a replay
        writes no duplicate row for a stage already recorded.
        """
        ...

    async def record_stage_failure(
        self,
        *,
        org_id: OrgId,
        project_id: ProjectId,
        job_id: ItemId,
        stage: RescanStage,
        attempt_number: int,
        error_code: str,
        error_message: str,
        retryable: bool,
    ) -> None:
        """Persist a failed stage checkpoint; no later stage is recorded after."""
        ...


class RescanItemLineageWorkPort(Protocol):
    """Materializes carried successor items for carryable elements."""

    async def materialize(
        self,
        *,
        org_id: OrgId,
        project_id: ProjectId,
        script_id: ItemId,
        before_version_id: VersionId,
        after_version_id: VersionId,
        carryable_elements: tuple[CarryableElement, ...],
    ) -> tuple[CarriedItemMapping, ...]:
        """Create carried successor items and return the predecessor mapping."""
        ...


class RescanEvidenceWorkPort(Protocol):
    """Carries evidence lineage forward from a predecessor item."""

    async def carry_forward(
        self,
        *,
        org_id: OrgId,
        project_id: ProjectId,
        new_item_id: ItemId,
        source_item_id: ItemId,
    ) -> tuple[object, ...]:
        """Carry every source claim of ``source_item_id`` to ``new_item_id``."""
        ...


class RescanChildWorkPort(Protocol):
    """Lists affected items and requests idempotent child rescan work."""

    async def list_affected_items(
        self,
        *,
        org_id: OrgId,
        project_id: ProjectId,
        before_version_id: VersionId,
        affected_element_ids: tuple[ElementId, ...],
    ) -> tuple[ItemId, ...]:
        """List predecessor items whose elements were modified/removed."""
        ...

    async def request_detection(
        self,
        *,
        org_id: OrgId,
        project_id: ProjectId,
        after_version_id: VersionId,
        affected_item_ids: tuple[ItemId, ...],
        actor_id: ItemId,
    ) -> tuple[RescanChildWorkTicket, ...]:
        """Request fresh detection for affected items with stable keys."""
        ...

    async def request_research(
        self,
        *,
        org_id: OrgId,
        project_id: ProjectId,
        after_version_id: VersionId,
        affected_item_ids: tuple[ItemId, ...],
        actor_id: ItemId,
    ) -> tuple[RescanChildWorkTicket, ...]:
        """Request fresh research for affected items with stable keys."""
        ...


__all__ = [
    "RescanChildWorkTicket",
    "RescanStageCheckpoint",
    "SelectiveRescanRepositoryPort",
    "RescanItemLineageWorkPort",
    "RescanEvidenceWorkPort",
    "RescanChildWorkPort",
]

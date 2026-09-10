"""Session-bound SQL adapter for the monitoring change-signal review port.

Every statement runs on the caller-provided
:class:`~sqlalchemy.ext.asyncio.AsyncSession` and never opens, commits, or rolls
back its own transaction, so the review-decision flip and the authoritative
audit event share one atomic unit of work. All reads and writes are constrained
by the full ``(org_id, project_id)`` scope tuple, so a change signal is never
listed or mutated outside the authenticated organization-and-project scope.

The review flip is a status-guarded compare-and-swap: the ``UPDATE`` only
matches a row still in ``status = 'pending'`` within the exact scope. A zero
rowcount means the delta is absent, belongs to another tenant, or was already
reviewed; all three collapse to a neutral
:class:`~clearcut.commanding.errors.CommandNotFoundError`, so a caller can
neither double-review a signal nor probe for a foreign tenant's signals.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast
from uuid import UUID

import sqlalchemy as sa
from clearcut.commanding.errors import CommandNotFoundError
from clearcut.monitoring.domain.materiality import (
    ChangeMateriality,
    MonitoringReviewDecision,
    SourceDelta,
)
from clearcut.monitoring.ports.review_repository import PendingChangeSignal
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

_INSERT_DELTA = sa.text(
    """
    INSERT INTO monitoring_source_deltas (
        id, org_id, project_id, item_id, watch_id,
        prior_snapshot_id, new_snapshot_id, prior_excerpt, current_excerpt,
        signal_type, change_kind, change_summary, status, detected_at, created_at
    ) VALUES (
        :id, :org_id, :project_id, :item_id, :watch_id,
        :prior_snapshot_id, :new_snapshot_id, :prior_excerpt, :current_excerpt,
        :signal_type, :change_kind, :change_summary, 'pending', :detected_at, :created_at
    )
    """
)

_LIST_PENDING = sa.text(
    """
    SELECT id, org_id, project_id, item_id, watch_id,
           signal_type, change_kind, change_summary,
           prior_excerpt, current_excerpt, detected_at
    FROM monitoring_source_deltas
    WHERE org_id = :org_id AND project_id = :project_id AND status = 'pending'
    ORDER BY detected_at DESC
    """
)

_RECORD_REVIEW = sa.text(
    """
    UPDATE monitoring_source_deltas
    SET status = 'reviewed',
        review_id = :review_id,
        reviewed_by = :reviewed_by,
        review_action = :review_action,
        review_rationale = :review_rationale,
        reviewed_at = :reviewed_at
    WHERE id = :delta_id AND org_id = :org_id AND project_id = :project_id
      AND status = 'pending'
    """
)


class SqlMonitoringReviewRepository:
    """SQL implementation of :class:`MonitoringReviewRepositoryPort`."""

    async def write_delta(
        self,
        session: AsyncSession,
        *,
        delta: SourceDelta,
        watch_id: UUID | None,
        change_kind: str,
        prior_excerpt: str | None,
        current_excerpt: str | None,
    ) -> None:
        await session.execute(
            _INSERT_DELTA,
            {
                "id": str(delta.delta_id),
                "org_id": str(delta.org_id),
                "project_id": str(delta.project_id),
                "item_id": str(delta.item_id),
                "watch_id": str(watch_id) if watch_id is not None else None,
                "prior_snapshot_id": str(delta.prior_snapshot_id),
                "new_snapshot_id": str(delta.new_snapshot_id),
                "prior_excerpt": prior_excerpt,
                "current_excerpt": current_excerpt,
                "signal_type": delta.materiality.value,
                "change_kind": change_kind,
                "change_summary": delta.rationale,
                "detected_at": delta.created_at,
                "created_at": delta.created_at,
            },
        )

    async def list_pending(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
    ) -> list[PendingChangeSignal]:
        rows = (
            (
                await session.execute(
                    _LIST_PENDING,
                    {"org_id": str(org_id), "project_id": str(project_id)},
                )
            )
            .mappings()
            .all()
        )
        return [
            PendingChangeSignal(
                delta_id=_as_uuid(row["id"]),
                org_id=_as_uuid(row["org_id"]),
                project_id=_as_uuid(row["project_id"]),
                item_id=_as_uuid(row["item_id"]),
                watch_id=_as_optional_uuid(row["watch_id"]),
                signal_type=ChangeMateriality(str(row["signal_type"])),
                change_kind=str(row["change_kind"]),
                change_summary=str(row["change_summary"]),
                prior_excerpt=(
                    str(row["prior_excerpt"]) if row["prior_excerpt"] is not None else None
                ),
                current_excerpt=(
                    str(row["current_excerpt"]) if row["current_excerpt"] is not None else None
                ),
                detected_at=row["detected_at"],
            )
            for row in rows
        ]

    async def record_review_decision(
        self,
        session: AsyncSession,
        *,
        delta_id: UUID,
        org_id: UUID,
        project_id: UUID,
        decision: MonitoringReviewDecision,
        reviewed_at: datetime,
    ) -> None:
        result = await session.execute(
            _RECORD_REVIEW,
            {
                "delta_id": str(delta_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "review_id": str(decision.review_id),
                "reviewed_by": str(decision.actor_id),
                "review_action": decision.action.value,
                "review_rationale": decision.rationale,
                "reviewed_at": reviewed_at,
            },
        )
        # The status-guarded compare-and-swap must match exactly one pending row.
        # A zero rowcount means the delta is absent, foreign, or already
        # reviewed: keep neutral not-found parity so a caller cannot double-review
        # a signal or distinguish a foreign one.
        if cast(CursorResult[Any], result).rowcount != 1:
            raise CommandNotFoundError()


def _as_uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _as_optional_uuid(value: Any) -> UUID | None:
    if value is None:
        return None
    return _as_uuid(value)


__all__ = ["SqlMonitoringReviewRepository"]

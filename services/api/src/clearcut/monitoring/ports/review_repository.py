"""Typed persistence port for the monitoring change-signal review loop.

The port is the single boundary the monitoring review application service uses
to (1) persist a :class:`SourceDelta` when a recheck detects a change, (2) list
the pending change signals for an exact organization-and-project scope so a
human can triage them, and (3) record a :class:`MonitoringReviewDecision`
together with its authoritative audit event in one transaction, flipping the
delta from ``pending`` to ``reviewed``.

Every value crossing the boundary is a typed dataclass or a typed
governed-command error; no booleans, ``None`` sentinels, or raw rows encode
outcomes. A delta that is not visible in the authenticated scope, or one that
was already reviewed, surfaces as a typed
:class:`~clearcut.commanding.errors.CommandNotFoundError` — never a raw ``None``
— so a caller can neither probe for a foreign tenant's signals nor double-review
one.

Implementations run every statement inside the caller's unit of work so the
review decision and the authoritative audit event commit or roll back
atomically.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from clearcut.monitoring.domain.materiality import (
    ChangeMateriality,
    MonitoringReviewDecision,
    SourceDelta,
)
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class PendingChangeSignal:
    """A persisted, not-yet-reviewed monitoring change signal.

    This is the read projection the delivery layer maps onto the canonical
    ``MonitoringChange`` response. ``review_id`` is always ``None`` here (a
    pending signal has no decision yet); the delivery layer surfaces the delta's
    own id as the ``reviewId`` the client posts back to review it, so the signal
    is addressable before any decision exists.
    """

    delta_id: UUID
    org_id: UUID
    project_id: UUID
    item_id: UUID
    watch_id: UUID | None
    signal_type: ChangeMateriality
    change_kind: str
    change_summary: str
    prior_excerpt: str | None
    current_excerpt: str | None
    detected_at: datetime


class MonitoringReviewRepositoryPort(Protocol):
    """Session-bound persistence operations for the monitoring review loop."""

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
        """Persist a detected change signal as a pending review target.

        Runs inside the caller's transaction. The delta's own
        ``org_id``/``project_id``/``item_id`` scope the row; the excerpts are
        denormalized so the signal stays reviewable independently of the
        snapshots it was derived from.
        """
        ...

    async def list_pending(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
    ) -> list[PendingChangeSignal]:
        """Return the pending change signals for the exact scope, newest first.

        Only ``status = 'pending'`` rows in the authenticated
        organization-and-project scope are returned; a reviewed delta is never
        listed and a foreign tenant's signals are never visible.
        """
        ...

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
        """Flip a pending delta to reviewed, stamping the accountable decision.

        A version-guarded update on ``status = 'pending'`` within the exact scope
        writes ``review_id``, ``reviewed_by``, ``review_action``,
        ``review_rationale``, ``reviewed_at`` and sets ``status = 'reviewed'``.
        When the update affects zero rows the delta is absent, foreign, or
        already reviewed: the implementation raises a typed
        :class:`~clearcut.commanding.errors.CommandNotFoundError` so a caller
        cannot double-review or probe a foreign signal. Runs inside the caller's
        transaction so the flip commits atomically with the authoritative audit
        event.
        """
        ...


__all__ = [
    "PendingChangeSignal",
    "MonitoringReviewRepositoryPort",
]

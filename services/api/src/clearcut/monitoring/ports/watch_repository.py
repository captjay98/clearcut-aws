"""Typed persistence port for monitored-source registration and recheck state.

The monitoring review loop (see :mod:`clearcut.monitoring.ports.review_repository`)
persists and triages *detected changes*. This port sits one step earlier: it owns
the durable state a recheck compares against.

It lets the delivery layer (1) register a monitored source — insert a
``monitoring_watches`` row and record an initial baseline
:class:`SourceSnapshot` so a later recheck has a real prior to compare against —
(2) load a project's registered watches, (3) load the most recent persisted
snapshot for a watch's item to use as the recheck's prior, and (4) persist the
fresh snapshot and its :class:`MonitoringRun` produced by a recheck.

Registration is an *operational* write (it records what to watch), not a
governed clearance decision, so it carries no audit event. Every value crossing
the boundary is a typed dataclass; no booleans, ``None`` sentinels, or raw rows
encode outcomes, and every read and write is constrained by the full
``(org_id, project_id)`` scope tuple so a watch or snapshot is never visible or
mutable outside the authenticated organization-and-project scope.

Implementations run every statement inside the caller's unit of work so a
registration (watch row + baseline snapshot) is atomic, and a recheck's snapshot
and run persist together with any detected-change write.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from clearcut.monitoring.domain.models import MonitoringRun, WatchConfig
from clearcut.research.domain.snapshots import SourceSnapshot
from sqlalchemy.ext.asyncio import AsyncSession


class MonitoringWatchRepositoryPort(Protocol):
    """Session-bound persistence for monitored sources and their snapshots."""

    async def register_watch(
        self,
        session: AsyncSession,
        *,
        watch: WatchConfig,
        baseline_snapshot: SourceSnapshot,
    ) -> None:
        """Persist a monitored source and its initial baseline snapshot.

        Runs inside the caller's transaction. Inserts the ``monitoring_watches``
        row described by ``watch`` and stores ``baseline_snapshot`` as the prior
        a later recheck compares against, so the very first recheck has a real
        persisted snapshot to diff rather than nothing. The watch's own
        ``org_id``/``project_id`` scope the row.
        """
        ...

    async def list_watches(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
    ) -> list[WatchConfig]:
        """Return the registered watches for the exact scope, newest first.

        Only rows in the authenticated organization-and-project scope are
        returned; a foreign tenant's watches are never visible.
        """
        ...

    async def latest_snapshot_for_watch(
        self,
        session: AsyncSession,
        *,
        watch: WatchConfig,
    ) -> SourceSnapshot | None:
        """Return the most recent persisted snapshot for the watch's item.

        This is the prior a recheck compares against. ``None`` means the watch
        has no stored snapshot yet (nothing to compare), which is distinct from a
        detected change; the caller must not fabricate a delta in that case.
        """
        ...

    async def persist_recheck(
        self,
        session: AsyncSession,
        *,
        run: MonitoringRun,
        snapshot: SourceSnapshot,
    ) -> None:
        """Persist a recheck's fresh snapshot and its completed run.

        Runs inside the caller's transaction so the snapshot, the run, and any
        detected-change write recorded by the review repository in the same unit
        of work commit or roll back together.
        """
        ...


__all__ = ["MonitoringWatchRepositoryPort"]

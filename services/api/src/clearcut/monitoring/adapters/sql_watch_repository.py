"""Session-bound SQL adapter for the monitored-source watch port.

Every statement runs on the caller-provided
:class:`~sqlalchemy.ext.asyncio.AsyncSession` and never opens, commits, or rolls
back its own transaction, so a registration (watch row + baseline snapshot) is
one atomic unit of work, and a recheck's snapshot, run, and any change-signal
write share one transaction with the review repository. All reads and writes are
constrained by the full ``(org_id, project_id)`` scope tuple, so a watch or
snapshot is never listed, compared, or mutated outside the authenticated
organization-and-project scope.

A persisted :class:`SourceSnapshot` requires a parent ``research_runs`` row
(``source_snapshots.run_id`` is a non-null foreign key). A monitoring snapshot is
not produced by a research run, so this adapter provisions a minimal
item-scoped ``research_runs`` row for each snapshot it stores and points the
snapshot at it. The snapshot's research-provenance columns stay ``NULL`` (which
the schema's provenance check constraint permits for a non-research snapshot),
so no research provenance is fabricated.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from clearcut.monitoring.domain.models import (
    MonitoringRun,
    WatchCadence,
    WatchConfig,
    WatchKind,
)
from clearcut.research.domain.snapshots import SourceSnapshot
from sqlalchemy.ext.asyncio import AsyncSession

_INSERT_WATCH = sa.text(
    """
    INSERT INTO monitoring_watches (
        id, org_id, project_id, item_id, cadence, watch_kind,
        target_url, query_text, created_at
    ) VALUES (
        :id, :org_id, :project_id, :item_id, :cadence, :watch_kind,
        :target_url, :query_text, :created_at
    )
    """
)

_LIST_WATCHES = sa.text(
    """
    SELECT id, org_id, project_id, item_id, cadence, watch_kind,
           target_url, query_text, created_at
    FROM monitoring_watches
    WHERE org_id = :org_id AND project_id = :project_id
    ORDER BY created_at DESC
    """
)

# The prior a recheck compares against: the newest snapshot recorded for the
# watch's item within the exact scope. ``retrieved_at`` orders the timeline; the
# UUIDv7 id breaks ties deterministically for snapshots stamped in the same
# instant.
_LATEST_SNAPSHOT = sa.text(
    """
    SELECT id, org_id, project_id, item_id, run_id, url, title, publisher,
           excerpt, origin, sha256_hash, published_date, retrieved_at
    FROM source_snapshots
    WHERE org_id = :org_id AND project_id = :project_id AND item_id = :item_id
    ORDER BY retrieved_at DESC, id DESC
    LIMIT 1
    """
)

_INSERT_RESEARCH_RUN = sa.text(
    """
    INSERT INTO research_runs (id, org_id, project_id, item_id, status, created_at)
    VALUES (:id, :org_id, :project_id, :item_id, :status, :created_at)
    """
)

_INSERT_SNAPSHOT = sa.text(
    """
    INSERT INTO source_snapshots (
        id, org_id, project_id, item_id, run_id, url, title, publisher,
        excerpt, origin, sha256_hash, published_date, retrieved_at
    ) VALUES (
        :id, :org_id, :project_id, :item_id, :run_id, :url, :title, :publisher,
        :excerpt, :origin, :sha256_hash, :published_date, :retrieved_at
    )
    """
)

_INSERT_MONITORING_RUN = sa.text(
    """
    INSERT INTO monitoring_runs (
        id, watch_id, org_id, project_id, status, new_snapshot_id,
        error_message, created_at
    ) VALUES (
        :id, :watch_id, :org_id, :project_id, :status, :new_snapshot_id,
        :error_message, :created_at
    )
    """
)


class SqlMonitoringWatchRepository:
    """SQL implementation of :class:`MonitoringWatchRepositoryPort`."""

    async def register_watch(
        self,
        session: AsyncSession,
        *,
        watch: WatchConfig,
        baseline_snapshot: SourceSnapshot,
    ) -> None:
        await session.execute(
            _INSERT_WATCH,
            {
                "id": str(watch.watch_id),
                "org_id": str(watch.org_id),
                "project_id": str(watch.project_id),
                "item_id": str(watch.item_id),
                "cadence": watch.cadence.value,
                "watch_kind": watch.watch_kind.value,
                "target_url": watch.target_url,
                "query_text": watch.query_text,
                "created_at": watch.created_at,
            },
        )
        await self._persist_snapshot(session, baseline_snapshot)

    async def list_watches(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
    ) -> list[WatchConfig]:
        rows = (
            (
                await session.execute(
                    _LIST_WATCHES,
                    {"org_id": str(org_id), "project_id": str(project_id)},
                )
            )
            .mappings()
            .all()
        )
        return [
            WatchConfig(
                watch_id=_as_uuid(row["id"]),
                org_id=_as_uuid(row["org_id"]),
                project_id=_as_uuid(row["project_id"]),
                item_id=_as_uuid(row["item_id"]),
                cadence=WatchCadence(str(row["cadence"])),
                watch_kind=WatchKind(str(row["watch_kind"])),
                target_url=(
                    str(row["target_url"]) if row["target_url"] is not None else None
                ),
                query_text=(
                    str(row["query_text"]) if row["query_text"] is not None else None
                ),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    async def latest_snapshot_for_watch(
        self,
        session: AsyncSession,
        *,
        watch: WatchConfig,
    ) -> SourceSnapshot | None:
        row = (
            (
                await session.execute(
                    _LATEST_SNAPSHOT,
                    {
                        "org_id": str(watch.org_id),
                        "project_id": str(watch.project_id),
                        "item_id": str(watch.item_id),
                    },
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        return SourceSnapshot(
            snapshot_id=_as_uuid(row["id"]),
            org_id=_as_uuid(row["org_id"]),
            project_id=_as_uuid(row["project_id"]),
            item_id=_as_uuid(row["item_id"]),
            run_id=_as_uuid(row["run_id"]),
            url=str(row["url"]),
            title=str(row["title"]),
            publisher=str(row["publisher"]),
            excerpt=str(row["excerpt"]),
            origin=str(row["origin"]),
            sha256_hash=str(row["sha256_hash"]),
            retrieved_at=row["retrieved_at"],
            published_date=(
                str(row["published_date"]) if row["published_date"] is not None else None
            ),
        )

    async def persist_recheck(
        self,
        session: AsyncSession,
        *,
        run: MonitoringRun,
        snapshot: SourceSnapshot | None,
    ) -> None:
        if snapshot is not None:
            await self._persist_snapshot(session, snapshot)
        await session.execute(
            _INSERT_MONITORING_RUN,
            {
                "id": str(run.run_id),
                "watch_id": str(run.watch_id),
                "org_id": str(run.org_id),
                "project_id": str(run.project_id),
                "status": run.status.value,
                "new_snapshot_id": (
                    str(run.new_snapshot_id) if run.new_snapshot_id is not None else None
                ),
                "error_message": run.error_message,
                "created_at": run.created_at,
            },
        )

    async def _persist_snapshot(
        self, session: AsyncSession, snapshot: SourceSnapshot
    ) -> None:
        """Store a snapshot, provisioning its required item-scoped research run.

        ``source_snapshots.run_id`` is a non-null foreign key to
        ``research_runs``; a monitoring snapshot has no research run, so a minimal
        completed run scoped to the same item is created to anchor it. The
        snapshot's research-provenance columns are left ``NULL`` so no research
        provenance is invented.
        """
        await session.execute(
            _INSERT_RESEARCH_RUN,
            {
                "id": str(snapshot.run_id),
                "org_id": str(snapshot.org_id),
                "project_id": str(snapshot.project_id),
                "item_id": str(snapshot.item_id),
                "status": "completed",
                "created_at": datetime.now(UTC),
            },
        )
        await session.execute(
            _INSERT_SNAPSHOT,
            {
                "id": str(snapshot.snapshot_id),
                "org_id": str(snapshot.org_id),
                "project_id": str(snapshot.project_id),
                "item_id": str(snapshot.item_id),
                "run_id": str(snapshot.run_id),
                "url": snapshot.url,
                "title": snapshot.title,
                "publisher": snapshot.publisher,
                "excerpt": snapshot.excerpt,
                "origin": snapshot.origin,
                "sha256_hash": snapshot.sha256_hash,
                "published_date": snapshot.published_date,
                "retrieved_at": snapshot.retrieved_at,
            },
        )


def _as_uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


__all__ = ["SqlMonitoringWatchRepository"]

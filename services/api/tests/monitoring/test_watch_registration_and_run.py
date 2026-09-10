"""End-to-end persistence coverage for the monitoring watch loop.

These tests exercise the real SQL watch repository, the scheduled recheck
service, the review repository, and the delivery projection against a migrated
database. They mirror exactly what ``POST /monitoring:runCheck`` does — load the
registered watches, load each watch's most recent persisted snapshot as the
prior, run the recheck, persist the fresh snapshot + run, and persist only a
MATERIAL delta as a pending signal — without standing up the HTTP/session stack.

The change signal is never fabricated: it flows through
``execute_watch_recheck`` and the real ``compare_snapshots`` on genuinely
persisted snapshots. A baseline recorded with a different excerpt is what makes
the first recheck legitimately material; an identical baseline stays
non-material and persists no signal.
"""

from __future__ import annotations

from uuid import UUID

import pytest
import uuid6
from clearcut.database import session_scope
from clearcut.monitoring.adapters.sql_review_repository import SqlMonitoringReviewRepository
from clearcut.monitoring.adapters.sql_watch_repository import SqlMonitoringWatchRepository
from clearcut.monitoring.application.run_scheduled_watch import ScheduledWatchService
from clearcut.monitoring.delivery.http import _change_payload
from clearcut.monitoring.domain.materiality import ChangeMateriality
from clearcut.monitoring.domain.models import WatchCadence, WatchConfig, WatchKind
from clearcut.research.adapters.hermetic_extract import HermeticExtractAdapter
from clearcut.research.adapters.hermetic_search import HermeticSearchAdapter
from clearcut.research.domain.snapshots import SourceSnapshot

_TARGET_URL = "https://uspto.gov/trademarks/coca-cola"
# The excerpt the hermetic recheck deterministically re-derives (see
# ScheduledWatchService.execute_watch_recheck).
_RECHECK_EXCERPT = "Active registered record"


def _watch(org_id: UUID, project_id: UUID, item_id: UUID) -> WatchConfig:
    return WatchConfig.create(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        cadence=WatchCadence.WEEKLY,
        watch_kind=WatchKind.EXACT_SOURCE,
        target_url=_TARGET_URL,
    )


def _baseline(
    org_id: UUID, project_id: UUID, item_id: UUID, excerpt: str
) -> SourceSnapshot:
    return SourceSnapshot.create(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        run_id=uuid6.uuid7(),
        url=_TARGET_URL,
        title=f"Baseline for {item_id}",
        publisher="uspto.gov",
        excerpt=excerpt,
        origin="extract",
    )


async def _run_check(
    watch_repository: SqlMonitoringWatchRepository,
    review_repository: SqlMonitoringReviewRepository,
    org_id: UUID,
    project_id: UUID,
) -> int:
    """Replicate the runCheck handler's transaction and return signalsDetected."""
    service = ScheduledWatchService(
        extract_port=HermeticExtractAdapter(),
        search_port=HermeticSearchAdapter(),
    )
    signals = 0
    async with session_scope() as session:
        watches = await watch_repository.list_watches(
            session, org_id=org_id, project_id=project_id
        )
        for watch in watches:
            prior = await watch_repository.latest_snapshot_for_watch(session, watch=watch)
            run, snapshot, delta = await service.execute_watch_recheck(
                watch, prior_snapshot=prior
            )
            await watch_repository.persist_recheck(session, run=run, snapshot=snapshot)
            if delta is not None and delta.materiality is ChangeMateriality.MATERIAL:
                await review_repository.write_delta(
                    session,
                    delta=delta,
                    watch_id=watch.watch_id,
                    change_kind="content_changed",
                    prior_excerpt=prior.excerpt if prior is not None else None,
                    current_excerpt=snapshot.excerpt,
                )
                signals += 1
    return signals


@pytest.mark.asyncio
async def test_register_writes_watch_and_baseline_snapshot(
    seeded_monitoring_scope,
) -> None:
    org_id, project_id, item_id, _actor_id = seeded_monitoring_scope
    repository = SqlMonitoringWatchRepository()
    watch = _watch(org_id, project_id, item_id)
    baseline = _baseline(org_id, project_id, item_id, "Registered and active")

    async with session_scope() as session:
        await repository.register_watch(
            session, watch=watch, baseline_snapshot=baseline
        )

    async with session_scope() as session:
        watches = await repository.list_watches(
            session, org_id=org_id, project_id=project_id
        )
        stored_prior = await repository.latest_snapshot_for_watch(session, watch=watch)

    assert len(watches) == 1
    assert watches[0].watch_id == watch.watch_id
    assert watches[0].item_id == item_id
    assert watches[0].target_url == _TARGET_URL
    assert watches[0].cadence == WatchCadence.WEEKLY
    # The baseline snapshot is persisted as the real prior a recheck compares to.
    assert stored_prior is not None
    assert stored_prior.snapshot_id == baseline.snapshot_id
    assert stored_prior.excerpt == "Registered and active"


@pytest.mark.asyncio
async def test_run_check_with_material_difference_persists_pending_signal(
    seeded_monitoring_scope,
) -> None:
    org_id, project_id, item_id, _actor_id = seeded_monitoring_scope
    watch_repository = SqlMonitoringWatchRepository()
    review_repository = SqlMonitoringReviewRepository()
    watch = _watch(org_id, project_id, item_id)
    # Baseline excerpt differs from the recheck's deterministic excerpt, so the
    # real comparison legitimately yields a MATERIAL change.
    baseline = _baseline(org_id, project_id, item_id, "Registered and active")

    async with session_scope() as session:
        await watch_repository.register_watch(
            session, watch=watch, baseline_snapshot=baseline
        )

    signals = await _run_check(watch_repository, review_repository, org_id, project_id)
    assert signals == 1

    # The persisted signal is visible to listMonitoringChanges (list_pending).
    async with session_scope() as session:
        pending = await review_repository.list_pending(
            session, org_id=org_id, project_id=project_id
        )
    assert len(pending) == 1
    assert pending[0].item_id == item_id
    assert pending[0].watch_id == watch.watch_id
    assert pending[0].signal_type == ChangeMateriality.MATERIAL
    assert pending[0].prior_excerpt == "Registered and active"
    assert pending[0].current_excerpt == _RECHECK_EXCERPT

    payload = _change_payload(pending[0])
    assert payload["reviewId"] == str(pending[0].delta_id)
    assert payload["signalType"] == "material"


@pytest.mark.asyncio
async def test_run_check_with_no_watches_detects_zero_signals(
    seeded_monitoring_scope,
) -> None:
    org_id, project_id, _item_id, _actor_id = seeded_monitoring_scope
    watch_repository = SqlMonitoringWatchRepository()
    review_repository = SqlMonitoringReviewRepository()

    signals = await _run_check(watch_repository, review_repository, org_id, project_id)
    assert signals == 0

    async with session_scope() as session:
        pending = await review_repository.list_pending(
            session, org_id=org_id, project_id=project_id
        )
    assert pending == []


@pytest.mark.asyncio
async def test_run_check_with_identical_content_persists_no_signal(
    seeded_monitoring_scope,
) -> None:
    org_id, project_id, item_id, _actor_id = seeded_monitoring_scope
    watch_repository = SqlMonitoringWatchRepository()
    review_repository = SqlMonitoringReviewRepository()
    watch = _watch(org_id, project_id, item_id)
    # Baseline excerpt equals the recheck's excerpt, so the comparison is
    # NON_MATERIAL and no change signal is fabricated.
    baseline = _baseline(org_id, project_id, item_id, _RECHECK_EXCERPT)

    async with session_scope() as session:
        await watch_repository.register_watch(
            session, watch=watch, baseline_snapshot=baseline
        )

    signals = await _run_check(watch_repository, review_repository, org_id, project_id)
    assert signals == 0

    async with session_scope() as session:
        pending = await review_repository.list_pending(
            session, org_id=org_id, project_id=project_id
        )
    assert pending == []

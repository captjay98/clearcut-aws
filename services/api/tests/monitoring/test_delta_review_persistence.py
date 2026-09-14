"""Persistence coverage for the monitoring change-signal review loop.

These tests exercise the real SQL adapter, the governed review service, and the
delivery projection against a migrated database:

* a recheck that detects a change persists a :class:`SourceDelta` as a pending
  signal;
* ``listMonitoringChanges`` returns that pending signal carrying a ``reviewId``
  (the delta's own id);
* ``reviewMonitoringChange`` records the decision and its authoritative audit
  event atomically and removes the signal from the pending list;
* the review capability is enforced from the server-derived role.
"""

from __future__ import annotations

from uuid import UUID

import pytest
import sqlalchemy as sa
import uuid6
from clearcut.commanding.errors import CommandForbiddenError, CommandNotFoundError
from clearcut.database import session_scope
from clearcut.monitoring.adapters.sql_review_repository import SqlMonitoringReviewRepository
from clearcut.monitoring.application.review_change import MonitoringReviewService
from clearcut.monitoring.application.run_scheduled_watch import ScheduledWatchService
from clearcut.monitoring.delivery.http import _change_payload
from clearcut.monitoring.domain.materiality import ChangeMateriality, MonitoringReviewAction
from clearcut.monitoring.domain.models import WatchCadence, WatchConfig, WatchKind
from clearcut.organizations.domain.capabilities import Role
from clearcut.research.adapters.hermetic_extract import HermeticExtractAdapter
from clearcut.research.adapters.hermetic_search import HermeticSearchAdapter
from clearcut.research.domain.snapshots import SourceSnapshot


def _watch(org_id: UUID, project_id: UUID, item_id: UUID) -> WatchConfig:
    return WatchConfig.create(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        cadence=WatchCadence.DAILY,
        watch_kind=WatchKind.EXACT_SOURCE,
        target_url="https://uspto.gov/trademarks/coca-cola",
    )


def _prior_snapshot(org_id: UUID, project_id: UUID, item_id: UUID) -> SourceSnapshot:
    return SourceSnapshot.create(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        run_id=uuid6.uuid7(),
        url="https://uspto.gov/trademarks/coca-cola",
        title="Prior source",
        publisher="uspto.gov",
        excerpt="Registered and active",
        origin="extract",
    )


@pytest.mark.asyncio
async def test_recheck_detects_and_persists_a_pending_delta(seeded_monitoring_scope) -> None:
    org_id, project_id, item_id, _actor_id = seeded_monitoring_scope
    service = ScheduledWatchService(
        extract_port=HermeticExtractAdapter(),
        search_port=HermeticSearchAdapter(),
    )
    watch = _watch(org_id, project_id, item_id)
    prior = _prior_snapshot(org_id, project_id, item_id)

    # The hermetic adapter's derived excerpt differs from the prior excerpt,
    # so a MATERIAL change signal is produced from real comparison.
    run, snapshot, delta = await service.execute_watch_recheck(watch, prior_snapshot=prior)
    assert delta is not None
    assert delta.materiality == ChangeMateriality.MATERIAL

    repository = SqlMonitoringReviewRepository()
    async with session_scope() as session:
        await repository.write_delta(
            session,
            delta=delta,
            watch_id=None,
            change_kind="content_changed",
            prior_excerpt=prior.excerpt,
            current_excerpt=snapshot.excerpt,
        )

    async with session_scope() as session:
        pending = await repository.list_pending(session, org_id=org_id, project_id=project_id)

    assert len(pending) == 1
    assert pending[0].delta_id == delta.delta_id
    assert pending[0].item_id == item_id
    assert pending[0].current_excerpt == snapshot.excerpt


@pytest.mark.asyncio
async def test_list_monitoring_changes_projection_carries_review_id(
    seeded_monitoring_scope,
) -> None:
    org_id, project_id, item_id, _actor_id = seeded_monitoring_scope
    repository = SqlMonitoringReviewRepository()
    delta = _material_delta(org_id, project_id, item_id)

    async with session_scope() as session:
        await repository.write_delta(
            session,
            delta=delta,
            watch_id=None,
            change_kind="content_changed",
            prior_excerpt="Registered and active",
            current_excerpt="Cancelled",
        )
        pending = await repository.list_pending(session, org_id=org_id, project_id=project_id)

    payload = _change_payload(pending[0])
    # The reviewId the client posts back is the delta's own id.
    assert payload["reviewId"] == str(delta.delta_id)
    assert payload["deltaId"] == str(delta.delta_id)
    assert payload["itemId"] == str(item_id)
    assert payload["signalType"] == "material"


@pytest.mark.asyncio
async def test_review_persists_decision_and_audit_and_removes_from_pending(
    seeded_monitoring_scope,
) -> None:
    org_id, project_id, item_id, actor_id = seeded_monitoring_scope
    repository = SqlMonitoringReviewRepository()
    review_service = MonitoringReviewService(repository=repository)
    delta = _material_delta(org_id, project_id, item_id)

    async with session_scope() as session:
        await repository.write_delta(
            session,
            delta=delta,
            watch_id=None,
            change_kind="content_changed",
            prior_excerpt="Registered and active",
            current_excerpt="Cancelled",
        )

    # Record the decision and audit in one transaction.
    async with session_scope() as session:
        decision = await review_service.review_monitoring_delta(
            session,
            org_id=org_id,
            project_id=project_id,
            item_id=item_id,
            delta_id=delta.delta_id,
            actor_id=actor_id,
            actor_role=Role.REVIEWER.value,
            action=MonitoringReviewAction.REOPEN,
            rationale="Trademark cancelled; reopening for review.",
        )

    assert decision.action == MonitoringReviewAction.REOPEN

    async with session_scope() as session:
        # The signal is gone from pending.
        pending = await repository.list_pending(session, org_id=org_id, project_id=project_id)
        assert pending == []

        # The delta row is now reviewed and stamped with the accountable identity.
        row = (
            (
                await session.execute(
                    sa.text(
                        "SELECT status, review_id, reviewed_by, review_action "
                        "FROM monitoring_source_deltas WHERE id = :id"
                    ),
                    {"id": str(delta.delta_id)},
                )
            )
            .mappings()
            .first()
        )
        assert row is not None
        assert row["status"] == "reviewed"
        assert UUID(str(row["review_id"])) == decision.review_id
        assert UUID(str(row["reviewed_by"])) == actor_id
        assert row["review_action"] == MonitoringReviewAction.REOPEN.value

        # The authoritative audit event committed in the same transaction.
        audit_count = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM authoritative_audit_events "
                    "WHERE target_id = :review_id AND action = 'monitoring_review_decided'"
                ),
                {"review_id": str(decision.review_id)},
            )
        ).scalar_one()
        assert audit_count == 1


@pytest.mark.asyncio
async def test_review_without_capability_is_forbidden_and_leaves_signal_pending(
    seeded_monitoring_scope,
) -> None:
    org_id, project_id, item_id, actor_id = seeded_monitoring_scope
    repository = SqlMonitoringReviewRepository()
    review_service = MonitoringReviewService(repository=repository)
    delta = _material_delta(org_id, project_id, item_id)

    async with session_scope() as session:
        await repository.write_delta(
            session,
            delta=delta,
            watch_id=None,
            change_kind="content_changed",
            prior_excerpt="Registered and active",
            current_excerpt="Cancelled",
        )

    # Editor lacks item:decide, so the review is forbidden.
    with pytest.raises(CommandForbiddenError):
        async with session_scope() as session:
            await review_service.review_monitoring_delta(
                session,
                org_id=org_id,
                project_id=project_id,
                item_id=item_id,
                delta_id=delta.delta_id,
                actor_id=actor_id,
                actor_role=Role.EDITOR.value,
                action=MonitoringReviewAction.KEEP_WITH_FOLLOW_UP,
                rationale="Should not be allowed.",
            )

    # The forbidden attempt left the signal pending, not silently consumed.
    async with session_scope() as session:
        pending = await repository.list_pending(session, org_id=org_id, project_id=project_id)
    assert len(pending) == 1
    assert pending[0].delta_id == delta.delta_id


@pytest.mark.asyncio
async def test_reviewing_an_unknown_delta_is_a_neutral_not_found(seeded_monitoring_scope) -> None:
    org_id, project_id, item_id, actor_id = seeded_monitoring_scope
    repository = SqlMonitoringReviewRepository()
    review_service = MonitoringReviewService(repository=repository)

    with pytest.raises(CommandNotFoundError):
        async with session_scope() as session:
            await review_service.review_monitoring_delta(
                session,
                org_id=org_id,
                project_id=project_id,
                item_id=item_id,
                delta_id=uuid6.uuid7(),
                actor_id=actor_id,
                actor_role=Role.REVIEWER.value,
                action=MonitoringReviewAction.REFER,
                rationale="No such signal.",
            )


def _material_delta(org_id: UUID, project_id: UUID, item_id: UUID):
    from clearcut.monitoring.domain.materiality import SourceDelta

    return SourceDelta.create(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        prior_snapshot_id=uuid6.uuid7(),
        new_snapshot_id=uuid6.uuid7(),
        materiality=ChangeMateriality.MATERIAL,
        rationale="Source content changed materially.",
    )

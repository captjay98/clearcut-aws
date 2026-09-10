import pytest
import sqlalchemy as sa
import uuid6
from clearcut.database import session_scope
from clearcut.monitoring.adapters.sql_review_repository import SqlMonitoringReviewRepository
from clearcut.monitoring.application.review_change import MonitoringReviewService
from clearcut.monitoring.domain.materiality import (
    ChangeMateriality,
    MonitoringReviewAction,
    SourceDelta,
)
from clearcut.organizations.domain.capabilities import Role


@pytest.mark.asyncio
async def test_reopen_review_commits_decision_and_audit(seeded_monitoring_scope):
    """A reopen decision persists the accountable decision and its authoritative
    audit event in one transaction, moving the loop off the old in-memory dict.
    """
    org_id, project_id, item_id, actor_id = seeded_monitoring_scope
    repository = SqlMonitoringReviewRepository()
    service = MonitoringReviewService(repository=repository)

    delta = SourceDelta.create(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        prior_snapshot_id=uuid6.uuid7(),
        new_snapshot_id=uuid6.uuid7(),
        materiality=ChangeMateriality.MATERIAL,
        rationale="Source content changed",
    )

    async with session_scope() as session:
        await repository.write_delta(
            session,
            delta=delta,
            watch_id=None,
            change_kind="content_changed",
            prior_excerpt="Registered and active",
            current_excerpt="Cancelled",
        )

    async with session_scope() as session:
        decision = await service.review_monitoring_delta(
            session,
            org_id=org_id,
            project_id=project_id,
            item_id=item_id,
            delta_id=delta.delta_id,
            actor_id=actor_id,
            actor_role=Role.REVIEWER.value,
            action=MonitoringReviewAction.REOPEN,
            rationale="Reopening clearance review due to trademark status change",
        )

    assert decision.action == MonitoringReviewAction.REOPEN
    assert decision.actor_id == actor_id

    async with session_scope() as session:
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

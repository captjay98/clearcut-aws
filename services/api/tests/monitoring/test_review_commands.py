import pytest
import uuid6
from clearcut.monitoring.application.review_change import MonitoringReviewService
from clearcut.monitoring.domain.materiality import (
    ChangeMateriality,
    MonitoringReviewAction,
    SourceDelta,
)
from clearcut.organizations.domain.capabilities import Role


@pytest.mark.asyncio
async def test_reopen_review_commits_decision_and_audit():
    service = MonitoringReviewService()
    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    item_id = uuid6.uuid7()
    actor_id = uuid6.uuid7()

    delta = SourceDelta.create(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        prior_snapshot_id=uuid6.uuid7(),
        new_snapshot_id=uuid6.uuid7(),
        materiality=ChangeMateriality.MATERIAL,
        rationale="Source content changed",
    )

    decision, audit = await service.review_monitoring_delta(
        org_id=org_id,
        project_id=project_id,
        delta=delta,
        actor_id=actor_id,
        actor_role=Role.REVIEWER,
        action=MonitoringReviewAction.REOPEN,
        rationale="Reopening clearance review due to trademark status change",
    )

    assert decision.action == MonitoringReviewAction.REOPEN
    assert audit.action == "monitoring_review_decided"
    assert audit.actor_id == actor_id

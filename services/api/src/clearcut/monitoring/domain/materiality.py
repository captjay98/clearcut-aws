from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

import uuid6


class ChangeMateriality(StrEnum):
    NON_MATERIAL = "non_material"
    MATERIAL = "material"
    UNAVAILABLE = "unavailable"


class MonitoringReviewAction(StrEnum):
    KEEP_WITH_FOLLOW_UP = "keep_with_follow_up"
    REOPEN = "reopen"
    REFER = "refer"


@dataclass(frozen=True)
class SourceDelta:
    delta_id: UUID
    org_id: UUID
    project_id: UUID
    item_id: UUID
    prior_snapshot_id: UUID
    new_snapshot_id: UUID
    materiality: ChangeMateriality
    rationale: str
    created_at: datetime = datetime.now(UTC)

    @classmethod
    def create(
        cls,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        prior_snapshot_id: UUID,
        new_snapshot_id: UUID,
        materiality: ChangeMateriality,
        rationale: str,
    ) -> "SourceDelta":
        return cls(
            delta_id=uuid6.uuid7(),
            org_id=org_id,
            project_id=project_id,
            item_id=item_id,
            prior_snapshot_id=prior_snapshot_id,
            new_snapshot_id=new_snapshot_id,
            materiality=materiality,
            rationale=rationale.strip(),
            created_at=datetime.now(UTC),
        )


@dataclass(frozen=True)
class MonitoringReviewDecision:
    review_id: UUID
    org_id: UUID
    project_id: UUID
    item_id: UUID
    delta_id: UUID
    actor_id: UUID
    action: MonitoringReviewAction
    rationale: str
    created_at: datetime = datetime.now(UTC)

    @classmethod
    def create(
        cls,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        delta_id: UUID,
        actor_id: UUID,
        action: MonitoringReviewAction,
        rationale: str,
    ) -> "MonitoringReviewDecision":
        return cls(
            review_id=uuid6.uuid7(),
            org_id=org_id,
            project_id=project_id,
            item_id=item_id,
            delta_id=delta_id,
            actor_id=actor_id,
            action=action,
            rationale=rationale.strip(),
            created_at=datetime.now(UTC),
        )

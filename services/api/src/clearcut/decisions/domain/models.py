from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

import uuid6


class EvidenceDecisionType(StrEnum):
    ACCEPT_AS_IS = "accept_as_is"
    REQUEST_REWRITE = "request_rewrite"
    SEEK_LICENSE = "seek_license"
    FLAG_BLOCKER = "flag_blocker"


@dataclass(frozen=True)
class EvidenceDecision:
    decision_id: UUID
    org_id: UUID
    project_id: UUID
    item_id: UUID
    actor_id: UUID
    decision_type: EvidenceDecisionType
    rationale: str
    created_at: datetime = datetime.now(UTC)

    @classmethod
    def create(
        cls,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        actor_id: UUID,
        decision_type: EvidenceDecisionType,
        rationale: str,
    ) -> "EvidenceDecision":
        return cls(
            decision_id=uuid6.uuid7(),
            org_id=org_id,
            project_id=project_id,
            item_id=item_id,
            actor_id=actor_id,
            decision_type=decision_type,
            rationale=rationale.strip(),
            created_at=datetime.now(UTC),
        )


@dataclass(frozen=True)
class AuditEvent:
    event_id: UUID
    org_id: UUID
    project_id: UUID
    action: str
    actor_id: UUID
    target_id: UUID
    target_type: str
    details: dict[str, Any]
    created_at: datetime = datetime.now(UTC)

    @classmethod
    def create(
        cls,
        org_id: UUID,
        project_id: UUID,
        action: str,
        actor_id: UUID,
        target_id: UUID,
        target_type: str,
        details: dict[str, Any],
    ) -> "AuditEvent":
        return cls(
            event_id=uuid6.uuid7(),
            org_id=org_id,
            project_id=project_id,
            action=action,
            actor_id=actor_id,
            target_id=target_id,
            target_type=target_type,
            details=details,
            created_at=datetime.now(UTC),
        )

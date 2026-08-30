from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import uuid6


@dataclass(frozen=True)
class AuthoritativeAuditEvent:
    event_id: UUID
    org_id: UUID
    project_id: UUID | None
    actor_id: UUID
    action: str
    target_type: str
    target_id: UUID
    payload_redacted: dict[str, Any] = field(default_factory=dict)
    occurred_at: datetime = datetime.now(UTC)

    @classmethod
    def create(
        cls,
        org_id: UUID,
        project_id: UUID | None,
        actor_id: UUID,
        action: str,
        target_type: str,
        target_id: UUID,
        payload_redacted: dict[str, Any] | None = None,
    ) -> "AuthoritativeAuditEvent":
        return cls(
            event_id=uuid6.uuid7(),
            org_id=org_id,
            project_id=project_id,
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            payload_redacted=payload_redacted or {},
            occurred_at=datetime.now(UTC),
        )


@dataclass(frozen=True)
class DecisionReceipt:
    receipt_id: UUID
    decision_id: UUID
    decision_type: str
    actor_id: UUID
    rationale: str
    created_at: datetime = datetime.now(UTC)

    @classmethod
    def create(
        cls,
        decision_id: UUID,
        decision_type: str,
        actor_id: UUID,
        rationale: str,
    ) -> "DecisionReceipt":
        return cls(
            receipt_id=uuid6.uuid7(),
            decision_id=decision_id,
            decision_type=decision_type,
            actor_id=actor_id,
            rationale=rationale,
            created_at=datetime.now(UTC),
        )

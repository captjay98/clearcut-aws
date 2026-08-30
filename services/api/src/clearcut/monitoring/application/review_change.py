from uuid import UUID

from clearcut.decisions.domain.models import AuditEvent
from clearcut.monitoring.domain.materiality import (
    MonitoringReviewAction,
    MonitoringReviewDecision,
    SourceDelta,
)
from clearcut.organizations.domain.capabilities import Role, has_capability


class MonitoringReviewService:
    def __init__(self) -> None:
        self.decisions: dict[UUID, MonitoringReviewDecision] = {}
        self.audits: list[AuditEvent] = []

    async def review_monitoring_delta(
        self,
        org_id: UUID,
        project_id: UUID,
        delta: SourceDelta,
        actor_id: UUID,
        actor_role: Role,
        action: MonitoringReviewAction,
        rationale: str,
    ) -> tuple[MonitoringReviewDecision, AuditEvent]:
        if not has_capability(actor_role, "item:decide"):
            raise PermissionError(
                f"Insufficient capability for role '{actor_role.value}' "
                "to review monitoring deltas."
            )

        decision = MonitoringReviewDecision.create(
            org_id=org_id,
            project_id=project_id,
            item_id=delta.item_id,
            delta_id=delta.delta_id,
            actor_id=actor_id,
            action=action,
            rationale=rationale,
        )
        self.decisions[decision.review_id] = decision

        audit = AuditEvent.create(
            org_id=org_id,
            project_id=project_id,
            action="monitoring_review_decided",
            actor_id=actor_id,
            target_id=decision.review_id,
            target_type="monitoring_review_decision",
            details={
                "delta_id": str(delta.delta_id),
                "action": action.value,
                "rationale": rationale,
            },
        )
        self.audits.append(audit)

        return decision, audit

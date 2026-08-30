from uuid import UUID

from clearcut.decisions.domain.models import (
    AuditEvent,
    EvidenceDecision,
    EvidenceDecisionType,
    ItemReferral,
)
from clearcut.organizations.domain.capabilities import Role, has_capability


class DecisionCommandService:
    def __init__(self) -> None:
        self.decisions: dict[UUID, EvidenceDecision] = {}
        self.referrals: dict[UUID, ItemReferral] = {}
        self.audits: list[AuditEvent] = []

    async def record_evidence_decision(
        self,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        actor_id: UUID,
        actor_role: Role,
        decision_type: EvidenceDecisionType,
        rationale: str,
    ) -> tuple[EvidenceDecision, AuditEvent]:
        # Enforce capability
        if not has_capability(actor_role, "item:decide"):
            raise PermissionError(
                f"Insufficient capability for role '{actor_role.value}' "
                "to record evidence decisions."
            )

        decision = EvidenceDecision.create(
            org_id=org_id,
            project_id=project_id,
            item_id=item_id,
            actor_id=actor_id,
            decision_type=decision_type,
            rationale=rationale,
        )
        self.decisions[decision.decision_id] = decision

        audit = AuditEvent.create(
            org_id=org_id,
            project_id=project_id,
            action="evidence_decision_recorded",
            actor_id=actor_id,
            target_id=decision.decision_id,
            target_type="evidence_decision",
            details={
                "item_id": str(item_id),
                "decision_type": decision_type.value,
                "rationale": rationale,
            },
        )
        self.audits.append(audit)

        return decision, audit

    async def refer_clearance_item(
        self,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        actor_id: UUID,
        target_role: str,
        notes: str,
    ) -> tuple[ItemReferral, AuditEvent]:
        referral = ItemReferral.create(
            item_id=item_id,
            actor_id=actor_id,
            target_role=target_role,
            notes=notes,
        )
        self.referrals[referral.referral_id] = referral

        audit = AuditEvent.create(
            org_id=org_id,
            project_id=project_id,
            action="item_referred",
            actor_id=actor_id,
            target_id=referral.referral_id,
            target_type="item_referral",
            details={
                "item_id": str(item_id),
                "target_role": target_role,
                "notes": notes,
            },
        )
        self.audits.append(audit)

        return referral, audit

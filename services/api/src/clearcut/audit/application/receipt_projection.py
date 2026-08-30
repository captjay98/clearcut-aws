from clearcut.audit.domain.events import AuthoritativeAuditEvent, DecisionReceipt


class ReceiptProjectionService:
    def rebuild_receipt_from_audit(self, audit: AuthoritativeAuditEvent) -> DecisionReceipt:
        decision_type = str(audit.payload_redacted.get("decision_type", "unknown"))
        rationale = str(audit.payload_redacted.get("rationale", ""))

        return DecisionReceipt.create(
            decision_id=audit.target_id,
            decision_type=decision_type,
            actor_id=audit.actor_id,
            rationale=rationale,
        )

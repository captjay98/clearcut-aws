import uuid6
from clearcut.audit.application.receipt_projection import ReceiptProjectionService
from clearcut.audit.domain.events import AuthoritativeAuditEvent


def test_rebuild_receipt_from_authoritative_audit():
    service = ReceiptProjectionService()
    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    actor_id = uuid6.uuid7()
    target_id = uuid6.uuid7()

    audit = AuthoritativeAuditEvent.create(
        org_id=org_id,
        project_id=project_id,
        actor_id=actor_id,
        action="evidence_decision_recorded",
        target_type="evidence_decision",
        target_id=target_id,
        payload_redacted={"decision_type": "accept_as_is", "rationale": "Clear historic match"},
    )

    receipt = service.rebuild_receipt_from_audit(audit)

    assert receipt.decision_id == target_id
    assert receipt.decision_type == "accept_as_is"
    assert receipt.actor_id == actor_id

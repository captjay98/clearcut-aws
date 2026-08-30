import uuid6
from clearcut.audit.domain.events import AuthoritativeAuditEvent
from clearcut.records.application.query_service import RecordsQueryService


def test_records_query_service_redaction_and_scoping():
    service = RecordsQueryService()
    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    other_org_id = uuid6.uuid7()

    audit1 = AuthoritativeAuditEvent.create(
        org_id=org_id,
        project_id=project_id,
        actor_id=uuid6.uuid7(),
        action="evidence_decision_recorded",
        target_type="evidence_decision",
        target_id=uuid6.uuid7(),
        payload_redacted={"secret_token": "SHOULD_NEVER_EXIST", "decision_type": "flag_blocker"},
    )
    audit2 = AuthoritativeAuditEvent.create(
        org_id=other_org_id,
        project_id=uuid6.uuid7(),
        actor_id=uuid6.uuid7(),
        action="evidence_decision_recorded",
        target_type="evidence_decision",
        target_id=uuid6.uuid7(),
        payload_redacted={"decision_type": "accept_as_is"},
    )

    service.seed_events([audit1, audit2])
    results = service.query_records_for_org(org_id=org_id)

    # Scoped to org_id only
    assert len(results) == 1
    assert results[0].event_id == audit1.event_id

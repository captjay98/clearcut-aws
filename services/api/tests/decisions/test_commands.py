import pytest
import uuid6
from clearcut.decisions.application.commands import DecisionCommandService
from clearcut.decisions.domain.models import EvidenceDecisionType
from clearcut.organizations.domain.capabilities import Role


@pytest.mark.asyncio
async def test_record_evidence_decision_creates_decision_and_audit():
    service = DecisionCommandService()
    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    item_id = uuid6.uuid7()
    actor_id = uuid6.uuid7()

    decision, audit = await service.record_evidence_decision(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        actor_id=actor_id,
        actor_role=Role.REVIEWER,
        decision_type=EvidenceDecisionType.ACCEPT_AS_IS,
        rationale="Source is authoritative official register.",
    )

    assert decision.item_id == item_id
    assert decision.decision_type == EvidenceDecisionType.ACCEPT_AS_IS
    assert audit.action == "evidence_decision_recorded"
    assert audit.actor_id == actor_id

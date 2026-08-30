import pytest
import uuid6
from clearcut.decisions.application.commands import DecisionCommandService
from clearcut.decisions.domain.models import EvidenceDecisionType
from clearcut.organizations.domain.capabilities import Role


@pytest.mark.asyncio
async def test_editor_cannot_record_governed_evidence_decision():
    service = DecisionCommandService()
    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    item_id = uuid6.uuid7()
    actor_id = uuid6.uuid7()

    # Editor lacks capability to record governed clearance decisions
    with pytest.raises(PermissionError, match="Insufficient capability"):
        await service.record_evidence_decision(
            org_id=org_id,
            project_id=project_id,
            item_id=item_id,
            actor_id=actor_id,
            actor_role=Role.EDITOR,
            decision_type=EvidenceDecisionType.ACCEPT_AS_IS,
            rationale="Trying to clear without reviewer role",
        )

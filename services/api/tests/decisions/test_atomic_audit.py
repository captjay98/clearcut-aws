import pytest
import uuid6
from clearcut.decisions.application.commands import DecisionCommandService


@pytest.mark.asyncio
async def test_referral_generates_matching_audit_event():
    service = DecisionCommandService()
    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    item_id = uuid6.uuid7()
    actor_id = uuid6.uuid7()

    referral, audit = await service.refer_clearance_item(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        actor_id=actor_id,
        target_role="legal_counsel",
        notes="Requires external legal opinion on fair use."
    )

    assert referral.target_role == "legal_counsel"
    assert audit.action == "item_referred"
    assert audit.target_id == referral.referral_id

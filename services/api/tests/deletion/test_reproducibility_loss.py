import pytest
import uuid6
from clearcut.audit.application.deletion_service import DeletionService
from clearcut.audit.domain.deletion import DeletionState
from clearcut.organizations.domain.capabilities import Role


@pytest.mark.asyncio
async def test_purge_creates_tombstone_and_records_reproducibility_loss():
    service = DeletionService()
    org_id = uuid6.uuid7()
    owner_id = uuid6.uuid7()

    await service.schedule_org_deletion(org_id, actor_id=owner_id, actor_role=Role.OWNER)
    tombstone = await service.purge_organization(org_id)

    assert tombstone.state == DeletionState.PURGED
    assert tombstone.reproducibility_loss_recorded is True

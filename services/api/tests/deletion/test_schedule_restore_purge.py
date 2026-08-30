import pytest
import uuid6
from clearcut.audit.application.deletion_service import DeletionService
from clearcut.audit.domain.deletion import DeletionState
from clearcut.organizations.domain.capabilities import Role


@pytest.mark.asyncio
async def test_schedule_and_restore_deletion_lifecycle():
    service = DeletionService()
    org_id = uuid6.uuid7()
    owner_id = uuid6.uuid7()

    # 1. Schedule deletion by Owner sets 30-day grace period
    schedule = await service.schedule_org_deletion(org_id, actor_id=owner_id, actor_role=Role.OWNER)
    assert schedule.state == DeletionState.GRACE_PERIOD

    # 2. Restore active state
    restored = await service.restore_org_deletion(org_id, actor_id=owner_id, actor_role=Role.OWNER)
    assert restored.state == DeletionState.ACTIVE

@pytest.mark.asyncio
async def test_non_owner_cannot_schedule_deletion():
    service = DeletionService()
    org_id = uuid6.uuid7()
    admin_id = uuid6.uuid7()

    with pytest.raises(PermissionError):
        await service.schedule_org_deletion(org_id, actor_id=admin_id, actor_role=Role.ADMIN)

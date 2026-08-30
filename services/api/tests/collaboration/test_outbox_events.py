import pytest
import uuid6
from clearcut.collaboration.application.events import OutboxEventService


@pytest.mark.asyncio
async def test_stage_and_fetch_outbox_events():
    service = OutboxEventService()
    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    item_id = uuid6.uuid7()

    event = service.stage_event(
        event_type="item_comment_created.v1",
        payload={"org_id": str(org_id), "project_id": str(project_id), "item_id": str(item_id)},
    )

    assert event.event_type == "item_comment_created.v1"
    pending = service.get_pending_events()
    assert len(pending) == 1
    assert pending[0].event_id == event.event_id

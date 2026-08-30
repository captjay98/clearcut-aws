from datetime import UTC, datetime

import uuid6
from clearcut.collaboration.application.recipient_projection import NotificationProjectionService
from clearcut.collaboration.domain.notifications import NotificationTier
from clearcut.organizations.domain.models import Membership


def test_self_exclusion_actor_does_not_receive_own_notification():
    service = NotificationProjectionService()
    org_id = uuid6.uuid7()
    actor_id = uuid6.uuid7()
    teammate_id = uuid6.uuid7()

    member_actor = Membership(
        membership_id=uuid6.uuid7(),
        org_id=org_id,
        user_id=actor_id,
        role="reviewer",
        status="active",
        created_at=datetime.now(UTC),
    )
    member_teammate = Membership(
        membership_id=uuid6.uuid7(),
        org_id=org_id,
        user_id=teammate_id,
        role="reviewer",
        status="active",
        created_at=datetime.now(UTC),
    )

    notifications = service.project_event_to_notifications(
        org_id=org_id,
        actor_id=actor_id,
        title="Evidence decision recorded",
        body_redacted="A reviewer recorded a decision on an item.",
        destination_path="/o/paramount/projects/p1/items/i1",
        tier=NotificationTier.STANDARD,
        active_memberships=[member_actor, member_teammate],
    )

    # Teammate receives notification, actor is excluded
    recipient_ids = [n.recipient_id for n in notifications]
    assert teammate_id in recipient_ids
    assert actor_id not in recipient_ids

from datetime import UTC, datetime

import uuid6
from clearcut.collaboration.application.recipient_projection import NotificationProjectionService
from clearcut.collaboration.domain.notifications import NotificationTier
from clearcut.organizations.domain.models import Membership


def test_inactive_members_do_not_receive_notifications():
    service = NotificationProjectionService()
    org_id = uuid6.uuid7()
    actor_id = uuid6.uuid7()
    suspended_id = uuid6.uuid7()

    member_actor = Membership(
        membership_id=uuid6.uuid7(),
        org_id=org_id,
        user_id=actor_id,
        role="owner",
        status="active",
        created_at=datetime.now(UTC),
    )
    member_suspended = Membership(
        membership_id=uuid6.uuid7(),
        org_id=org_id,
        user_id=suspended_id,
        role="editor",
        status="deactivated",
        created_at=datetime.now(UTC),
    )

    notifications = service.project_event_to_notifications(
        org_id=org_id,
        actor_id=actor_id,
        title="New script revision",
        body_redacted="A new script revision was uploaded.",
        destination_path="/o/paramount/projects/p1/versions",
        tier=NotificationTier.INFORMATIONAL,
        active_memberships=[member_actor, member_suspended],
    )

    recipient_ids = [n.recipient_id for n in notifications]
    assert suspended_id not in recipient_ids

from uuid import UUID

from clearcut.collaboration.domain.notifications import Notification, NotificationTier
from clearcut.organizations.domain.models import Membership


class NotificationProjectionService:
    def project_event_to_notifications(
        self,
        org_id: UUID,
        actor_id: UUID,
        title: str,
        body_redacted: str,
        destination_path: str,
        tier: NotificationTier,
        active_memberships: list[Membership],
    ) -> list[Notification]:
        notifications: list[Notification] = []

        for m in active_memberships:
            # 1. Active membership check
            if m.status != "active" or m.org_id != org_id:
                continue

            # 2. Self-exclusion check (actor never receives own action notification)
            if m.user_id == actor_id:
                continue

            notifications.append(
                Notification.create(
                    org_id=org_id,
                    recipient_id=m.user_id,
                    tier=tier,
                    title=title,
                    body_redacted=body_redacted,
                    destination_path=destination_path,
                )
            )

        return notifications

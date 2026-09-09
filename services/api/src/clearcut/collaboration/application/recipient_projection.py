"""Fan-out projection from one event to per-recipient notification rows.

The projection rules are unchanged and deliberately narrow: a notification goes
to each *active* membership of the *same* organization, and never back to the
actor who caused the event. A deactivated member and a membership belonging to
another organization are skipped, not merely deprioritized.

What is new here is a persistence path. The projection used to compute
notifications and return them to nobody, so a fan-out could be computed and then
silently dropped. :meth:`NotificationProjectionService.project_and_persist` runs
the same rules and writes the result through the notification repository inside
the caller's transaction, so notifications commit atomically with the event that
caused them or not at all. The pure :meth:`project_event_to_notifications`
remains available for callers that want the rules without a database.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from clearcut.collaboration.domain.notifications import Notification, NotificationTier
from clearcut.collaboration.ports.notification_repository import NotificationRepositoryPort
from clearcut.organizations.domain.models import Membership
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class ProjectedNotifications:
    """The fan-out that was written, with the exact persisted row count."""

    notifications: tuple[Notification, ...]
    persisted_count: int


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
        occurred_at: datetime | None = None,
    ) -> list[Notification]:
        notifications: list[Notification] = []
        # One event is one moment: every recipient's row shares the occurrence
        # time, so the fan-out cannot be ordered by incidental construction skew.
        created_at = occurred_at if occurred_at is not None else datetime.now(UTC)

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
                    created_at=created_at,
                )
            )

        return notifications

    async def project_and_persist(
        self,
        session: AsyncSession,
        *,
        repository: NotificationRepositoryPort,
        org_id: UUID,
        actor_id: UUID,
        title: str,
        body_redacted: str,
        destination_path: str,
        tier: NotificationTier,
        active_memberships: list[Membership],
        occurred_at: datetime | None = None,
    ) -> ProjectedNotifications:
        """Apply the projection rules and persist the result atomically.

        Every statement runs in the caller's unit of work, so the notifications
        commit with the event that produced them. Content that would leak an
        internal identifier raises
        :class:`~clearcut.collaboration.domain.notifications.NotificationContentError`
        from the domain before anything is written.
        """
        notifications = self.project_event_to_notifications(
            org_id=org_id,
            actor_id=actor_id,
            title=title,
            body_redacted=body_redacted,
            destination_path=destination_path,
            tier=tier,
            active_memberships=active_memberships,
            occurred_at=occurred_at,
        )
        persisted = await repository.insert_notifications(session, notifications)
        return ProjectedNotifications(
            notifications=tuple(notifications),
            persisted_count=persisted.persisted_count,
        )


__all__ = ["NotificationProjectionService", "ProjectedNotifications"]

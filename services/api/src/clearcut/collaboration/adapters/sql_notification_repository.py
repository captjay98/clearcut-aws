"""Session-bound SQL adapter for the notification inbox port.

Every statement runs on the caller-provided
:class:`~sqlalchemy.ext.asyncio.AsyncSession` and never opens, commits, or rolls
back its own transaction, so a fan-out of notifications commits atomically with
the event that produced it.

Scope is enforced in SQL, not after the fact. Reads and writes on
``notifications`` always carry both ``org_id`` and ``recipient_id`` in the
``WHERE`` clause, so a row addressed to another user is not merely filtered out
of the response — it is never loaded, and the missing row surfaces as the same
typed :class:`~clearcut.collaboration.ports.notification_repository.NotificationNotFoundError`
that an entirely unknown id produces.

The project-accessibility predicate is the same one the item read model and the
governed collaboration adapter use: an active membership that either holds an
organization-wide role or an explicit ``project_grants`` row for that project.
It is duplicated as SQL rather than reimplemented as logic so a notification can
never offer a link into a project the reader could not open directly.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
import uuid6
from clearcut.collaboration.domain.notifications import Notification, NotificationTier
from clearcut.collaboration.ports.notification_repository import (
    DeliveryChannel,
    MarkAllReadResult,
    NotificationNotFoundError,
    PersistedProjection,
    StoredDeliveryPreference,
    StoredNotification,
)
from sqlalchemy.ext.asyncio import AsyncSession

_LIST_FOR_RECIPIENT = sa.text(
    """
    SELECT id, org_id, recipient_id, tier, title, body_redacted, destination_path,
           is_read, created_at
    FROM notifications
    WHERE org_id = :org_id AND recipient_id = :recipient_id
    ORDER BY created_at DESC, id DESC
    """
)

_LOAD_FOR_RECIPIENT = sa.text(
    """
    SELECT id, org_id, recipient_id, tier, title, body_redacted, destination_path,
           is_read, created_at
    FROM notifications
    WHERE id = :notification_id AND org_id = :org_id AND recipient_id = :recipient_id
    """
)

_MARK_READ = sa.text(
    """
    UPDATE notifications SET is_read = true
    WHERE id = :notification_id AND org_id = :org_id AND recipient_id = :recipient_id
    """
)

_MARK_ALL_READ = sa.text(
    """
    UPDATE notifications SET is_read = true
    WHERE org_id = :org_id AND recipient_id = :recipient_id AND is_read = false
    """
)

_ACCESSIBLE_PROJECTS = sa.text(
    """
    SELECT p.id
    FROM projects p
    JOIN memberships m ON m.org_id = p.org_id
    WHERE p.org_id = :org_id
      AND m.user_id = :user_id
      AND m.status = 'active'
      AND (
        m.role IN ('owner', 'admin')
        OR EXISTS (
          SELECT 1 FROM project_grants pg
          WHERE pg.membership_id = m.id
            AND pg.org_id = m.org_id
            AND pg.project_id = p.id
        )
      )
    """
)

_UPSERT_DELIVERY_PREFERENCE = sa.text(
    """
    INSERT INTO notification_delivery_preferences
        (id, org_id, user_id, channel, created_at, updated_at)
    VALUES (:id, :org_id, :user_id, :channel, :occurred_at, :occurred_at)
    ON CONFLICT (org_id, user_id) DO UPDATE
        SET channel = excluded.channel, updated_at = excluded.updated_at
    """
)

_LOAD_DELIVERY_PREFERENCE = sa.text(
    """
    SELECT org_id, user_id, channel, updated_at
    FROM notification_delivery_preferences
    WHERE org_id = :org_id AND user_id = :user_id
    """
)

_INSERT_NOTIFICATION = sa.text(
    """
    INSERT INTO notifications
        (id, org_id, recipient_id, tier, title, body_redacted, destination_path,
         is_read, created_at)
    VALUES (:id, :org_id, :recipient_id, :tier, :title, :body_redacted,
            :destination_path, :is_read, :created_at)
    """
)


class SqlNotificationRepository:
    """SQL implementation of ``NotificationRepositoryPort``."""

    async def list_for_recipient(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        recipient_id: UUID,
    ) -> tuple[StoredNotification, ...]:
        rows = (
            (
                await session.execute(
                    _LIST_FOR_RECIPIENT,
                    {"org_id": str(org_id), "recipient_id": str(recipient_id)},
                )
            )
            .mappings()
            .all()
        )
        return tuple(_to_stored_notification(row) for row in rows)

    async def mark_read(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        recipient_id: UUID,
        notification_id: UUID,
    ) -> StoredNotification:
        parameters = {
            "notification_id": str(notification_id),
            "org_id": str(org_id),
            "recipient_id": str(recipient_id),
        }
        row = (await session.execute(_LOAD_FOR_RECIPIENT, parameters)).mappings().first()
        if row is None:
            # Absent, foreign tenant, and another recipient's row are one shape.
            raise NotificationNotFoundError()
        await session.execute(_MARK_READ, parameters)
        stored = _to_stored_notification(row)
        if stored.is_read:
            return stored
        return StoredNotification(
            notification_id=stored.notification_id,
            org_id=stored.org_id,
            recipient_id=stored.recipient_id,
            tier=stored.tier,
            title=stored.title,
            body_redacted=stored.body_redacted,
            destination_path=stored.destination_path,
            is_read=True,
            created_at=stored.created_at,
        )

    async def mark_all_read(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        recipient_id: UUID,
    ) -> MarkAllReadResult:
        result = await session.execute(
            _MARK_ALL_READ,
            {"org_id": str(org_id), "recipient_id": str(recipient_id)},
        )
        # ``rowcount`` is the number of rows this statement actually transitioned,
        # so a repeat call truthfully reports zero rather than the prior total.
        updated = getattr(result, "rowcount", 0)
        return MarkAllReadResult(updated_count=max(int(updated), 0))

    async def accessible_project_ids(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        user_id: UUID,
        candidate_project_ids: tuple[UUID, ...],
    ) -> frozenset[UUID]:
        if not candidate_project_ids:
            return frozenset()
        accessible = (
            (
                await session.execute(
                    _ACCESSIBLE_PROJECTS,
                    {"org_id": str(org_id), "user_id": str(user_id)},
                )
            )
            .scalars()
            .all()
        )
        accessible_ids = {_as_uuid(value) for value in accessible}
        return frozenset(
            project_id for project_id in candidate_project_ids if project_id in accessible_ids
        )

    async def set_delivery_preference(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        user_id: UUID,
        channel: DeliveryChannel,
        occurred_at: datetime,
    ) -> StoredDeliveryPreference:
        if not isinstance(occurred_at, datetime):
            raise TypeError("occurred_at must be a datetime.")
        await session.execute(
            _UPSERT_DELIVERY_PREFERENCE,
            {
                "id": str(_new_id()),
                "org_id": str(org_id),
                "user_id": str(user_id),
                "channel": channel.value,
                "occurred_at": occurred_at,
            },
        )
        row = (
            (
                await session.execute(
                    _LOAD_DELIVERY_PREFERENCE,
                    {"org_id": str(org_id), "user_id": str(user_id)},
                )
            )
            .mappings()
            .one()
        )
        return StoredDeliveryPreference(
            org_id=_as_uuid(row["org_id"]),
            user_id=_as_uuid(row["user_id"]),
            channel=DeliveryChannel(str(row["channel"])),
            updated_at=_as_aware_datetime(row["updated_at"]),
        )

    async def insert_notifications(
        self,
        session: AsyncSession,
        notifications: Sequence[Notification],
        /,
    ) -> PersistedProjection:
        for notification in notifications:
            await session.execute(
                _INSERT_NOTIFICATION,
                {
                    "id": str(notification.notification_id),
                    "org_id": str(notification.org_id),
                    "recipient_id": str(notification.recipient_id),
                    "tier": notification.tier.value,
                    "title": notification.title,
                    "body_redacted": notification.body_redacted,
                    "destination_path": notification.destination_path,
                    "is_read": notification.is_read,
                    "created_at": notification.created_at,
                },
            )
        return PersistedProjection(persisted_count=len(notifications))


def _new_id() -> UUID:
    return uuid6.uuid7()


# The middle tier was renamed from "standard" to "action" to match the inbox's
# "Needs your action" heading. Any row written under the former name is read as
# the tier it always meant, rather than failing the whole inbox read.
_TIER_RENAMES = {"standard": NotificationTier.ACTION}


def _to_tier(value: str) -> NotificationTier:
    renamed = _TIER_RENAMES.get(value)
    if renamed is not None:
        return renamed
    return NotificationTier(value)


def _to_stored_notification(row: Any) -> StoredNotification:
    return StoredNotification(
        notification_id=_as_uuid(row["id"]),
        org_id=_as_uuid(row["org_id"]),
        recipient_id=_as_uuid(row["recipient_id"]),
        tier=_to_tier(str(row["tier"])),
        title=str(row["title"]),
        body_redacted=str(row["body_redacted"]),
        destination_path=str(row["destination_path"]),
        is_read=bool(row["is_read"]),
        created_at=_as_aware_datetime(row["created_at"]),
    )


def _as_uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _as_aware_datetime(value: Any) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


__all__ = ["SqlNotificationRepository"]

"""Typed persistence port for the personal notification inbox.

The inbox is not a governed decision surface: reading it, marking a row read, and
choosing a delivery channel are ordinary state changes on the caller's own data.
So this port carries no command envelope, no expected-version guard, and no audit
receipt. What it does carry is the scoping rule the surface depends on: a
notification belongs to a recipient, so every operation is keyed by
``(org_id, recipient_id)`` and a row addressed to another user is indistinguishable
from a row that does not exist — both raise
:class:`NotificationNotFoundError`, never a distinguishing forbidden error that
would confirm the row is real.

Every value crossing this boundary is a typed dataclass, a typed enum, an exact
count, or a typed error. No booleans, ``None`` sentinels, or raw rows encode an
outcome. Implementations run every statement inside the caller's unit of work and
never open, commit, or roll back their own transaction.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from clearcut.collaboration.domain.notifications import Notification, NotificationTier
from sqlalchemy.ext.asyncio import AsyncSession


class NotificationNotFoundError(Exception):
    """A notification is not visible in the caller's own inbox.

    Raised identically whether the notification does not exist, belongs to
    another organization, or is addressed to another recipient, so a caller
    cannot probe for the existence of someone else's notification.
    """

    def __init__(self, message: str = "Notification not found.") -> None:
        super().__init__(message)
        self.message = message


class DeliveryChannel(StrEnum):
    """The channel vocabulary the database check constraint enforces."""

    IN_APP = "in_app"
    EMAIL = "email"
    PUSH = "push"


@dataclass(frozen=True)
class StoredNotification:
    """One persisted inbox row resolved inside the recipient's own scope.

    Storage column names are preserved here on purpose: ``body_redacted``,
    ``is_read``, and ``destination_path`` say what the column means. The
    contract's ``body`` / ``read`` / ``link`` names are applied once, explicitly,
    at the delivery boundary.
    """

    notification_id: UUID
    org_id: UUID
    recipient_id: UUID
    tier: NotificationTier
    title: str
    body_redacted: str
    destination_path: str
    is_read: bool
    created_at: datetime


@dataclass(frozen=True)
class StoredDeliveryPreference:
    """The caller's own persisted delivery channel within one organization."""

    org_id: UUID
    user_id: UUID
    channel: DeliveryChannel
    updated_at: datetime


@dataclass(frozen=True)
class MarkAllReadResult:
    """The exact number of rows this call transitioned from unread to read.

    A repeat call reports ``0`` because nothing was left to change, which is what
    makes the operation idempotent and the count truthful.
    """

    updated_count: int


@dataclass(frozen=True)
class PersistedProjection:
    """The exact number of fan-out notification rows persisted."""

    persisted_count: int


class NotificationRepositoryPort(Protocol):
    """Session-bound persistence operations for the notification inbox."""

    async def list_for_recipient(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        recipient_id: UUID,
    ) -> tuple[StoredNotification, ...]:
        """Load the recipient's own inbox, newest first.

        Returns only rows where ``recipient_id`` and ``org_id`` both match the
        authenticated scope; another user's rows are never included, so the
        surface cannot filter its way into someone else's inbox.
        """
        ...

    async def mark_read(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        recipient_id: UUID,
        notification_id: UUID,
    ) -> StoredNotification:
        """Mark one of the caller's own notifications read and return it.

        Raises :class:`NotificationNotFoundError` when the notification is not in
        the caller's own inbox, with identical shape for an unknown id and for
        another recipient's id. The write is idempotent: an already-read row is
        returned unchanged.
        """
        ...

    async def mark_all_read(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        recipient_id: UUID,
    ) -> MarkAllReadResult:
        """Mark every unread row in the caller's own inbox read.

        The returned count is the number of rows actually transitioned, so a
        second call reports ``0`` rather than restating the first call's total.
        """
        ...

    async def accessible_project_ids(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        user_id: UUID,
        candidate_project_ids: tuple[UUID, ...],
    ) -> frozenset[UUID]:
        """Return the subset of candidate projects this user may actually open.

        A project is accessible when it still exists in the organization and the
        user is an active member who either holds an organization-wide role or an
        explicit grant on that project. A deleted project and an ungranted
        project are both simply absent from the returned set; the caller turns
        that absence into a withheld link with a stated reason.
        """
        ...

    async def set_delivery_preference(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        user_id: UUID,
        channel: DeliveryChannel,
        occurred_at: datetime,
    ) -> StoredDeliveryPreference:
        """Persist the caller's own delivery channel for this organization.

        The preference is personal and unique per ``(org_id, user_id)``, so this
        is an upsert against that uniqueness rather than an insert that could
        accumulate competing rows for one user.
        """
        ...

    async def insert_notifications(
        self,
        session: AsyncSession,
        notifications: Sequence[Notification],
        /,
    ) -> PersistedProjection:
        """Persist an already-projected fan-out inside the caller's transaction.

        The recipient rules (active membership, actor self-exclusion, foreign
        membership rejection) are decided before this call; this method only
        writes what the projection produced, so notifications commit atomically
        with the event that caused them.
        """
        ...


__all__ = [
    "DeliveryChannel",
    "MarkAllReadResult",
    "NotificationNotFoundError",
    "NotificationRepositoryPort",
    "PersistedProjection",
    "StoredDeliveryPreference",
    "StoredNotification",
]

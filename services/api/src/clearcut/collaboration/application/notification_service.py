"""Application service for the personal notification inbox.

The rule this service exists to enforce is that **a notification is not
permission**. A notification row records that something happened and where it
happened; it does not grant the reader the right to go there. Access can be
revoked, and a project can be deleted, long after the notification was written.
So the link is not a stored string that the surface renders blindly: on every
read, the destination is re-checked against the reader's current project access,
and a destination they could not open directly is withheld with a stated reason
instead of offered as a link that would navigate somewhere misleading. The check
runs here, on the server, so it holds for every client of the contract rather
than only for the one screen that remembered to ask.

The withheld reason deliberately does not distinguish "the project was deleted"
from "your access was removed". Both mean the same thing to the reader — there is
nothing here they can open — and collapsing them keeps the response from
confirming whether a project the reader cannot access still exists.

Marking a notification read and choosing a delivery channel are ordinary state
changes on the caller's own data, not governed decisions: no command envelope, no
expected-version guard, no audit event. Reading someone else's inbox is not
possible to express through this service at all, because every operation takes
the recipient identity from the authenticated scope.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from clearcut.collaboration.ports.notification_repository import (
    DeliveryChannel,
    MarkAllReadResult,
    NotificationRepositoryPort,
    StoredDeliveryPreference,
    StoredNotification,
)
from sqlalchemy.ext.asyncio import AsyncSession


class LinkWithheldReason(StrEnum):
    """Why a stored destination is not being offered to this reader."""

    PROJECT_UNAVAILABLE = "project_unavailable"
    DESTINATION_UNRESOLVABLE = "destination_unresolvable"


@dataclass(frozen=True)
class OfferedLink:
    """The destination is safe to offer: it resolves inside the reader's access."""

    path: str


@dataclass(frozen=True)
class WithheldLink:
    """The destination exists in storage but must not be offered to this reader."""

    reason: LinkWithheldReason


NotificationDestination = OfferedLink | WithheldLink


@dataclass(frozen=True)
class NotificationView:
    """One inbox row plus the server's decision about its destination."""

    notification: StoredNotification
    destination: NotificationDestination


class NotificationService:
    """Read and update the caller's own inbox, and their delivery channel."""

    def __init__(self, repository: NotificationRepositoryPort) -> None:
        self._repository = repository

    async def list_inbox(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        recipient_id: UUID,
    ) -> tuple[NotificationView, ...]:
        """Load the caller's own inbox with each destination re-checked now."""
        notifications = await self._repository.list_for_recipient(
            session,
            org_id=org_id,
            recipient_id=recipient_id,
        )
        return await self._resolve_destinations(
            session,
            org_id=org_id,
            recipient_id=recipient_id,
            notifications=notifications,
        )

    async def mark_read(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        recipient_id: UUID,
        notification_id: UUID,
    ) -> NotificationView:
        """Mark one of the caller's own notifications read.

        Propagates the port's typed
        :class:`~clearcut.collaboration.ports.notification_repository.NotificationNotFoundError`
        unchanged, so another recipient's id is answered exactly as an unknown id
        is.
        """
        notification = await self._repository.mark_read(
            session,
            org_id=org_id,
            recipient_id=recipient_id,
            notification_id=notification_id,
        )
        views = await self._resolve_destinations(
            session,
            org_id=org_id,
            recipient_id=recipient_id,
            notifications=(notification,),
        )
        return views[0]

    async def mark_all_read(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        recipient_id: UUID,
    ) -> MarkAllReadResult:
        """Mark every unread row in the caller's own inbox read."""
        return await self._repository.mark_all_read(
            session,
            org_id=org_id,
            recipient_id=recipient_id,
        )

    async def set_delivery_preference(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        user_id: UUID,
        channel: DeliveryChannel,
        occurred_at: datetime | None = None,
    ) -> StoredDeliveryPreference:
        """Persist the caller's own delivery channel for this organization.

        The preference is personal, so any active member may set their own; it
        confers no capability on anyone else and is not a governed action.
        """
        return await self._repository.set_delivery_preference(
            session,
            org_id=org_id,
            user_id=user_id,
            channel=channel,
            occurred_at=occurred_at if occurred_at is not None else datetime.now(UTC),
        )

    async def _resolve_destinations(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        recipient_id: UUID,
        notifications: Sequence[StoredNotification],
    ) -> tuple[NotificationView, ...]:
        """Decide, per row, whether its destination may be offered right now."""
        if not notifications:
            return ()

        project_targets: dict[UUID, UUID | None] = {}
        for notification in notifications:
            project_targets[notification.notification_id] = project_id_in_path(
                notification.destination_path
            )
        candidates = tuple(
            {project_id for project_id in project_targets.values() if project_id is not None}
        )
        accessible = await self._repository.accessible_project_ids(
            session,
            org_id=org_id,
            user_id=recipient_id,
            candidate_project_ids=candidates,
        )

        views: list[NotificationView] = []
        for notification in notifications:
            views.append(
                NotificationView(
                    notification=notification,
                    destination=_decide_destination(
                        destination_path=notification.destination_path,
                        project_id=project_targets[notification.notification_id],
                        accessible_project_ids=accessible,
                    ),
                )
            )
        return tuple(views)


def _decide_destination(
    *,
    destination_path: str,
    project_id: UUID | None,
    accessible_project_ids: frozenset[UUID],
) -> NotificationDestination:
    path = destination_path.strip()
    if not path:
        return WithheldLink(reason=LinkWithheldReason.DESTINATION_UNRESOLVABLE)
    if not path.startswith("/"):
        # Only in-application routes are ever offered; anything else cannot be
        # verified against the reader's access, so it is not offered at all.
        return WithheldLink(reason=LinkWithheldReason.DESTINATION_UNRESOLVABLE)
    if _names_project_segment(path) and project_id is None:
        # The route claims a project but the identifier is unreadable, so there
        # is nothing to check access against.
        return WithheldLink(reason=LinkWithheldReason.DESTINATION_UNRESOLVABLE)
    if project_id is not None and project_id not in accessible_project_ids:
        return WithheldLink(reason=LinkWithheldReason.PROJECT_UNAVAILABLE)
    return OfferedLink(path=path)


def _names_project_segment(path: str) -> bool:
    return "projects" in _segments(path)


def project_id_in_path(destination_path: str) -> UUID | None:
    """Extract the project identifier a destination route points into.

    Returns ``None`` when the route is organization-level (no project segment) or
    when the project segment is not a readable identifier; the caller
    distinguishes those two cases before deciding whether to offer the link.
    """
    segments = _segments(destination_path)
    for index, segment in enumerate(segments):
        if segment != "projects":
            continue
        if index + 1 >= len(segments):
            return None
        try:
            return UUID(segments[index + 1])
        except ValueError:
            return None
    return None


def _segments(path: str) -> list[str]:
    return [segment for segment in path.split("?")[0].split("/") if segment]


__all__ = [
    "LinkWithheldReason",
    "NotificationDestination",
    "NotificationService",
    "NotificationView",
    "OfferedLink",
    "WithheldLink",
]

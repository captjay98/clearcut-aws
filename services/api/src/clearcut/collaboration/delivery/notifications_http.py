"""Delivery boundary for the personal notification inbox.

Four canonical operations are mounted here: ``listNotifications``,
``markAllNotificationsRead``, ``markNotificationRead``, and
``setNotificationDeliveryPreference``.

Three things are decided at this boundary and nowhere else:

* **Field mapping.** Storage says ``body_redacted`` / ``is_read`` /
  ``destination_path``; the contract says ``body`` / ``read`` / ``link``. The
  translation is written out explicitly in :func:`_notification_payload` rather
  than produced by a name-mangling helper, so the two vocabularies stay legible
  and a column rename cannot silently change the wire shape.
* **Withheld links.** When the server has decided a destination must not be
  offered, ``link`` is *absent* from the payload and ``blockedReason`` carries a
  plain sentence. The row then says why it cannot take the reader anywhere,
  instead of offering a link that navigates somewhere misleading. This is the
  "a notification is not permission" invariant, enforced server-side so it holds
  for every client rather than only the one screen that remembered.
* **Neutral not-found.** Another recipient's notification id and an entirely
  unknown id produce the identical 404 envelope. A 403 would confirm the row
  exists, which is exactly the fact a caller must not be able to probe for.

Registration and revocation of push subscriptions are intentionally not mounted:
there is no subscription table, and an endpoint that accepted a subscription
without storing one would claim a capability the product does not have.

``registerPushSubscription`` and ``revokePushSubscription`` therefore remain
unimplemented rather than stubbed.
"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

import uuid6
from clearcut.collaboration.adapters.sql_notification_repository import (
    SqlNotificationRepository,
)
from clearcut.collaboration.application.notification_service import (
    LinkWithheldReason,
    NotificationService,
    NotificationView,
    OfferedLink,
    WithheldLink,
)
from clearcut.collaboration.ports.notification_repository import (
    DeliveryChannel,
    NotificationNotFoundError,
    StoredDeliveryPreference,
)
from clearcut.csrf import verify_csrf_origin
from clearcut.database import session_scope
from clearcut.delivery_errors import error_response
from clearcut.identity.delivery.scope import get_request_scope
from fastapi import APIRouter, Path, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

router = APIRouter(tags=["notifications"])

_NOTIFICATIONS_PATH = "/api/v1/organizations/{orgId}/notifications"
_MARK_READ_PATH = "/api/v1/organizations/{orgId}/notifications/{notificationId}:markRead"
_PREFERENCE_PATH = "/api/v1/organizations/{orgId}/notification-preference"

OrgIdParam = Annotated[str, Path(alias="orgId")]
NotificationIdParam = Annotated[str, Path(alias="notificationId")]

_service = NotificationService(repository=SqlNotificationRepository())

# One sentence per withheld reason, written for the reader of the inbox rather
# than for an operator: it explains what happened and implies what they can do.
_WITHHELD_SENTENCES = {
    LinkWithheldReason.PROJECT_UNAVAILABLE: (
        "The project this notification refers to is no longer available to you, "
        "so no link is offered."
    ),
    LinkWithheldReason.DESTINATION_UNRESOLVABLE: (
        "This notification's destination could not be resolved, so no link is offered."
    ),
}

_NOT_FOUND_MESSAGE = "Notification not found."


class NotificationDeliveryPreferenceBody(BaseModel):
    """Contract-aligned request body for ``setNotificationDeliveryPreference``."""

    model_config = ConfigDict(extra="forbid")

    channel: Literal["in_app", "email", "push"]


@router.get(_NOTIFICATIONS_PATH, operation_id="listNotifications")
async def list_notifications(org_id: OrgIdParam, request: Request) -> JSONResponse:
    scope = await get_request_scope(request, org_id=org_id)
    assert scope.org_id is not None  # get_request_scope enforced org membership

    async with session_scope() as session:
        views = await _service.list_inbox(
            session,
            org_id=scope.org_id,
            recipient_id=scope.user_id,
        )

    return _success([_notification_payload(view) for view in views])


@router.post(_NOTIFICATIONS_PATH, operation_id="markAllNotificationsRead")
async def mark_all_notifications_read(org_id: OrgIdParam, request: Request) -> JSONResponse:
    verify_csrf_origin(request)
    scope = await get_request_scope(request, org_id=org_id)
    assert scope.org_id is not None  # get_request_scope enforced org membership

    async with session_scope() as session:
        result = await _service.mark_all_read(
            session,
            org_id=scope.org_id,
            recipient_id=scope.user_id,
        )

    return _success({"updatedCount": result.updated_count})


@router.post(_MARK_READ_PATH, operation_id="markNotificationRead")
async def mark_notification_read(
    org_id: OrgIdParam,
    notification_id: NotificationIdParam,
    request: Request,
) -> JSONResponse:
    verify_csrf_origin(request)
    scope = await get_request_scope(request, org_id=org_id)
    assert scope.org_id is not None  # get_request_scope enforced org membership

    parsed_notification_id = _parse_uuid(notification_id)
    if parsed_notification_id is None:
        # An unreadable id names a notification that cannot exist in this inbox:
        # same neutral not-found as any other absent row.
        return _not_found()

    try:
        async with session_scope() as session:
            view = await _service.mark_read(
                session,
                org_id=scope.org_id,
                recipient_id=scope.user_id,
                notification_id=parsed_notification_id,
            )
    except NotificationNotFoundError:
        return _not_found()

    return _success(_notification_payload(view))


@router.put(_PREFERENCE_PATH, operation_id="setNotificationDeliveryPreference")
async def set_notification_delivery_preference(
    org_id: OrgIdParam,
    body: NotificationDeliveryPreferenceBody,
    request: Request,
) -> JSONResponse:
    verify_csrf_origin(request)
    # The preference is personal: any active member of the organization may set
    # their own channel. It grants nothing to anyone else, so it is not a
    # governed action and carries no capability check beyond active membership.
    scope = await get_request_scope(request, org_id=org_id)
    assert scope.org_id is not None  # get_request_scope enforced org membership

    async with session_scope() as session:
        preference = await _service.set_delivery_preference(
            session,
            org_id=scope.org_id,
            user_id=scope.user_id,
            channel=DeliveryChannel(body.channel),
        )

    return _success(_preference_payload(preference))


def _notification_payload(view: NotificationView) -> dict[str, object]:
    notification = view.notification
    payload: dict[str, object] = {
        "notificationId": str(notification.notification_id),
        "orgId": str(notification.org_id),
        "tier": notification.tier.value,
        "title": notification.title,
        # Storage column ``body_redacted`` -> contract field ``body``.
        "body": notification.body_redacted,
        # Storage column ``is_read`` -> contract field ``read``.
        "read": notification.is_read,
        "createdAt": notification.created_at.isoformat(),
    }
    destination = view.destination
    if isinstance(destination, OfferedLink):
        # Storage column ``destination_path`` -> contract field ``link``.
        payload["link"] = destination.path
    elif isinstance(destination, WithheldLink):
        # No ``link`` key at all: an absent link cannot be followed by a client
        # that ignores ``blockedReason``.
        payload["blockedReason"] = _WITHHELD_SENTENCES[destination.reason]
    return payload


def _preference_payload(preference: StoredDeliveryPreference) -> dict[str, object]:
    return {"channel": preference.channel.value}


def _parse_uuid(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


def _not_found() -> JSONResponse:
    return error_response(
        status_code=status.HTTP_404_NOT_FOUND,
        code="not_found",
        message=_NOT_FOUND_MESSAGE,
    )


def _success(data: object) -> JSONResponse:
    request_id = str(uuid6.uuid7())
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"data": data, "meta": {"requestId": request_id}},
    )


__all__ = ["router"]

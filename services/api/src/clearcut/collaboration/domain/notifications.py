"""Notification domain model: tier vocabulary, redaction guard, and identity.

Three product invariants live here rather than in a delivery handler:

* The tier vocabulary is exactly ``urgent`` / ``action`` / ``informational``,
  matching the canonical contract and the inbox headings the surface renders
  ("Urgent", "Needs your action", "Informational"). A tier the surface cannot
  group under one of those headings is not a tier.
* ``created_at`` is captured per notification at construction time. It is a
  ``default_factory`` and never a bare default expression, because a bare
  ``datetime.now(UTC)`` default on a dataclass is evaluated once at class
  definition and would stamp every notification with the process start time.
* Notification content carries no internal identifier. A prompt id, a model
  name, a rubric version, or a bare UUID tells a reader nothing they can act on,
  and the storage column is named ``body_redacted`` for exactly this reason. A
  violation is a typed :class:`NotificationContentError`, never a silently
  persisted leak.

The destination path is deliberately *not* redaction-checked: it is a route, not
prose shown to the reader, and the read boundary decides whether the recipient
may be offered it at all.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

import uuid6


class NotificationTier(StrEnum):
    """Canonical inbox grouping tiers.

    ``ACTION`` is the middle tier: the inbox groups it under "Needs your action",
    which is a statement about what the reader must do, not about volume.
    """

    URGENT = "urgent"
    ACTION = "action"
    INFORMATIONAL = "informational"


class NotificationContentError(ValueError):
    """Raised when notification content would leak an internal identifier."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


_UUID_SHAPED = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)

# Compared against content with every non-alphanumeric character removed, so
# "prompt_id", "promptId", and "prompt id" all collapse to the same token.
_INTERNAL_IDENTIFIER_TOKENS = (
    "promptid",
    "promptversion",
    "rubricversion",
    "rubricid",
    "modelname",
    "modelversion",
    "modelid",
    "runid",
    "jobid",
    "itemid",
    "snapshotid",
    "policyversion",
    "gemini",
)


def _reject_internal_identifiers(field_name: str, value: str) -> None:
    if _UUID_SHAPED.search(value):
        raise NotificationContentError(
            f"Notification {field_name} must not contain an internal identifier."
        )
    compact = re.sub(r"[^0-9a-z]", "", value.lower())
    for token in _INTERNAL_IDENTIFIER_TOKENS:
        if token in compact:
            raise NotificationContentError(
                f"Notification {field_name} must not contain an internal identifier."
            )


@dataclass(frozen=True)
class Notification:
    """One inbox row addressed to exactly one recipient in one organization."""

    notification_id: UUID
    org_id: UUID
    recipient_id: UUID
    tier: NotificationTier
    title: str
    body_redacted: str
    destination_path: str
    is_read: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(
        cls,
        org_id: UUID,
        recipient_id: UUID,
        tier: NotificationTier,
        title: str,
        body_redacted: str,
        destination_path: str,
        created_at: datetime | None = None,
    ) -> Notification:
        """Build a notification, rejecting content that leaks internal identity.

        ``created_at`` may be supplied so a single fan-out shares one occurrence
        time; when omitted it is captured now.
        """
        clean_title = title.strip()
        clean_body = body_redacted.strip()
        _reject_internal_identifiers("title", clean_title)
        _reject_internal_identifiers("body", clean_body)
        return cls(
            notification_id=uuid6.uuid7(),
            org_id=org_id,
            recipient_id=recipient_id,
            tier=tier,
            title=clean_title,
            body_redacted=clean_body,
            destination_path=destination_path.strip(),
            is_read=False,
            created_at=created_at if created_at is not None else datetime.now(UTC),
        )


__all__ = ["Notification", "NotificationContentError", "NotificationTier"]

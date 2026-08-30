from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

import uuid6


class NotificationTier(StrEnum):
    URGENT = "urgent"
    STANDARD = "standard"
    INFORMATIONAL = "informational"


@dataclass(frozen=True)
class Notification:
    notification_id: UUID
    org_id: UUID
    recipient_id: UUID
    tier: NotificationTier
    title: str
    body_redacted: str
    destination_path: str
    is_read: bool = False
    created_at: datetime = datetime.now(UTC)

    @classmethod
    def create(
        cls,
        org_id: UUID,
        recipient_id: UUID,
        tier: NotificationTier,
        title: str,
        body_redacted: str,
        destination_path: str,
    ) -> "Notification":
        return cls(
            notification_id=uuid6.uuid7(),
            org_id=org_id,
            recipient_id=recipient_id,
            tier=tier,
            title=title.strip(),
            body_redacted=body_redacted.strip(),
            destination_path=destination_path.strip(),
            is_read=False,
            created_at=datetime.now(UTC),
        )

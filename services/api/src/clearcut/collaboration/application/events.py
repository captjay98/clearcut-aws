from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import uuid6


@dataclass(frozen=True)
class OutboxEvent:
    event_id: UUID
    event_type: str
    payload: dict[str, Any]
    created_at: datetime
    processed_at: datetime | None = None


class OutboxEventService:
    def __init__(self) -> None:
        self.events: list[OutboxEvent] = []

    def stage_event(self, event_type: str, payload: dict[str, Any]) -> OutboxEvent:
        event = OutboxEvent(
            event_id=uuid6.uuid7(),
            event_type=event_type,
            payload=payload,
            created_at=datetime.now(UTC),
        )
        self.events.append(event)
        return event

    def get_pending_events(self) -> list[OutboxEvent]:
        return [e for e in self.events if e.processed_at is None]

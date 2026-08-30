from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import uuid6


@dataclass(frozen=True)
class EvidenceConflict:
    conflict_id: UUID
    item_id: UUID
    description: str
    created_at: datetime = datetime.now(UTC)

    @classmethod
    def create(
        cls,
        item_id: UUID,
        description: str,
    ) -> "EvidenceConflict":
        return cls(
            conflict_id=uuid6.uuid7(),
            item_id=item_id,
            description=description.strip(),
            created_at=datetime.now(UTC),
        )

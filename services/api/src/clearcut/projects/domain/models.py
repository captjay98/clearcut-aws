from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import uuid6


@dataclass(frozen=True)
class Project:
    project_id: UUID
    org_id: UUID
    title: str
    description: str | None
    created_at: datetime

    @classmethod
    def create(
        cls,
        org_id: UUID,
        title: str,
        description: str | None = None,
    ) -> "Project":
        return cls(
            project_id=uuid6.uuid7(),
            org_id=org_id,
            title=title.strip(),
            description=description.strip() if description else None,
            created_at=datetime.now(UTC),
        )

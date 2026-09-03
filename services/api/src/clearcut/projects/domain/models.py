from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID

import uuid6


@dataclass(frozen=True)
class Project:
    project_id: UUID
    org_id: UUID
    title: str
    description: str | None
    created_at: datetime
    production_type: str | None = None
    production_stage: str | None = None
    jurisdiction: str | None = None
    target_lock_date: date | None = None
    review_brief: str | None = None

    @classmethod
    def create(
        cls,
        org_id: UUID,
        title: str,
        description: str | None = None,
        production_type: str | None = None,
        production_stage: str | None = None,
        jurisdiction: str | None = None,
        target_lock_date: date | None = None,
        review_brief: str | None = None,
    ) -> "Project":
        return cls(
            project_id=uuid6.uuid7(),
            org_id=org_id,
            title=title.strip(),
            description=description.strip() if description else None,
            created_at=datetime.now(UTC),
            production_type=production_type.strip() if production_type else None,
            production_stage=production_stage.strip() if production_stage else None,
            jurisdiction=jurisdiction.strip() if jurisdiction else None,
            target_lock_date=target_lock_date,
            review_brief=review_brief.strip() if review_brief else None,
        )

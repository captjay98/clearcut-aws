from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import uuid6


@dataclass(frozen=True)
class Comment:
    comment_id: UUID
    org_id: UUID
    project_id: UUID
    item_id: UUID
    author_id: UUID
    content: str
    parent_comment_id: UUID | None
    mentions: list[str]
    is_edited: bool = False
    created_at: datetime = datetime.now(UTC)
    updated_at: datetime = datetime.now(UTC)

    @classmethod
    def create(
        cls,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        author_id: UUID,
        content: str,
        parent_comment_id: UUID | None = None,
        mentions: list[str] | None = None,
    ) -> "Comment":
        now = datetime.now(UTC)
        return cls(
            comment_id=uuid6.uuid7(),
            org_id=org_id,
            project_id=project_id,
            item_id=item_id,
            author_id=author_id,
            content=content.strip(),
            parent_comment_id=parent_comment_id,
            mentions=mentions or [],
            is_edited=False,
            created_at=now,
            updated_at=now,
        )

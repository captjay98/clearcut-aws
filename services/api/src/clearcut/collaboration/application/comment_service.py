import re
from uuid import UUID

from clearcut.collaboration.domain.comments import Comment


class CommentService:
    def __init__(self) -> None:
        self.comments: dict[UUID, Comment] = {}

    async def create_comment(
        self,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        author_id: UUID,
        content: str,
        parent_comment_id: UUID | None = None,
    ) -> Comment:
        # DG-01: Verify reply depth is strictly 1-level
        if parent_comment_id:
            parent = self.comments.get(parent_comment_id)
            if not parent:
                raise ValueError("Parent comment not found")
            if parent.parent_comment_id is not None:
                raise ValueError("Maximum comment depth exceeded: nested replies are not permitted")

        # Extract mentions (@username)
        mentions = re.findall(r"@([a-zA-Z0-9_]+)", content)

        comment = Comment.create(
            org_id=org_id,
            project_id=project_id,
            item_id=item_id,
            author_id=author_id,
            content=content,
            parent_comment_id=parent_comment_id,
            mentions=mentions,
        )
        self.comments[comment.comment_id] = comment
        return comment

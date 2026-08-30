import pytest
import uuid6
from clearcut.collaboration.application.comment_service import CommentService


@pytest.mark.asyncio
async def test_extract_user_mentions():
    service = CommentService()
    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    item_id = uuid6.uuid7()
    author_id = uuid6.uuid7()

    comment = await service.create_comment(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        author_id=author_id,
        content="Hey @sarah and @mike, please check this license.",
    )

    assert "sarah" in comment.mentions
    assert "mike" in comment.mentions

import pytest
import uuid6
from clearcut.collaboration.application.comment_service import CommentService


@pytest.mark.asyncio
async def test_create_parent_comment_and_reply():
    service = CommentService()
    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    item_id = uuid6.uuid7()
    author_id = uuid6.uuid7()

    parent = await service.create_comment(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        author_id=author_id,
        content="Is this product trademark active?",
    )
    assert parent.parent_comment_id is None
    assert parent.content == "Is this product trademark active?"

    reply = await service.create_comment(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        author_id=author_id,
        content="Yes, verified via USPTO snapshot.",
        parent_comment_id=parent.comment_id,
    )
    assert reply.parent_comment_id == parent.comment_id

@pytest.mark.asyncio
async def test_nested_reply_to_reply_is_rejected_dg01():
    service = CommentService()
    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    item_id = uuid6.uuid7()
    author_id = uuid6.uuid7()

    parent = await service.create_comment(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        author_id=author_id,
        content="Parent comment.",
    )
    reply = await service.create_comment(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        author_id=author_id,
        content="1st level reply.",
        parent_comment_id=parent.comment_id,
    )

    # DG-01: Threading is strictly 1-level; reply-to-reply is rejected
    with pytest.raises(ValueError, match="Maximum comment depth exceeded"):
        await service.create_comment(
            org_id=org_id,
            project_id=project_id,
            item_id=item_id,
            author_id=author_id,
            content="Attempted 2nd level reply.",
            parent_comment_id=reply.comment_id,
        )

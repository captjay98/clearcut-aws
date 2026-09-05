"""Transactional/outbox tests for the persisted comment slice (Task 8).

A comment, reply, or revision is an operational collaboration write, but it still
commits atomically with the same shared infrastructure the governed commands
use: the comment/reply/revision row(s), any mention rows, the authoritative audit
event, and a schema-versioned, deduplicated outbox event all land in one
transaction. These tests prove:

* Group 4 (happy path): an accepted comment stages exactly one schema-versioned,
  deduplicated outbox event alongside the audit event and the domain rows.
* Group 4 (dual rollback): injecting an audit failure and, separately, an outbox
  failure each rolls back the *entire* command — no comment row, no mention row,
  no audit event, and no outbox event survive.

The audit and outbox seams are resolved through the ``comments`` application
module so they can be patched at that boundary, exactly as the governed referral
rollback tests patch their seams.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
import uuid6
from clearcut.database import session_scope
from clearcut.main import app
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.asyncio

_PASSWORD = "Password123!"


def _idempotency_key(label: str) -> str:
    return f"idem-{label}-{uuid4().hex}"


def _comments_path(org_id: UUID, project_id: UUID, item_id: UUID) -> str:
    return (
        f"/api/v1/organizations/{org_id}/projects/{project_id}"
        f"/clearance-items/{item_id}/comments"
    )


async def _client() -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"origin": "http://test"},
    )


@dataclass(frozen=True)
class Fixture:
    org_id: UUID
    project_id: UUID
    item_id: UUID
    actor_id: UUID
    actor_email: str


async def _register_actor(client: AsyncClient, *, suffix: str) -> tuple[UUID, str]:
    email = f"outbox-{suffix}-{uuid4().hex}@example.com"
    registration = await client.post(
        "/api/v1/users",
        json={"name": f"Outbox {suffix}", "email": email, "password": _PASSWORD},
    )
    assert registration.status_code == 201, registration.text
    return UUID(registration.json()["data"]["userId"]), email


async def _create_org_and_project(client: AsyncClient, *, suffix: str) -> tuple[UUID, UUID]:
    organization = await client.post(
        "/api/v1/organizations",
        json={
            "name": f"Outbox Studio {suffix}",
            "slug": f"obx-{suffix}-{uuid4().hex[:8]}",
        },
    )
    assert organization.status_code == 201, organization.text
    org_id = UUID(organization.json()["data"]["orgId"])
    project = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        json={"title": f"Outbox Project {suffix}"},
    )
    assert project.status_code == 201, project.text
    project_id = UUID(project.json()["data"]["projectId"])
    return org_id, project_id


async def _insert_item(*, org_id: UUID, project_id: UUID) -> UUID:
    script_id = uuid6.uuid7()
    version_id = uuid6.uuid7()
    element_id = uuid6.uuid7()
    item_id = uuid6.uuid7()
    now = datetime.now(UTC)
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO scripts (id, org_id, project_id, title, created_at) "
                "VALUES (:id, :org_id, :project_id, 'Outbox test', :created_at)"
            ),
            {
                "id": str(script_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "created_at": now,
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO script_versions "
                "(id, script_id, org_id, project_id, ordinal, source_hash, parser_version, "
                "created_at) VALUES "
                "(:id, :script_id, :org_id, :project_id, 1, :source_hash, 'v1', :created_at)"
            ),
            {
                "id": str(version_id),
                "script_id": str(script_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "source_hash": "f" * 64,
                "created_at": now,
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO script_elements (id, version_id, ordinal, element_type, text) "
                "VALUES (:id, :version_id, 1, 'action', 'Acme Corporation')"
            ),
            {"id": str(element_id), "version_id": str(version_id)},
        )
        await session.execute(
            sa.text(
                "INSERT INTO clearance_items "
                "(id, org_id, project_id, script_id, version_id, element_id, category, text, "
                "status, research_status, workflow_status, disposition_status, created_at, "
                "version) VALUES (:id, :org_id, :project_id, :script_id, :version_id, "
                ":element_id, 'products_and_trademarks', 'Acme Corporation', 'unresolved', "
                "'completed', 'detected', 'undisposed', :created_at, 1)"
            ),
            {
                "id": str(item_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "script_id": str(script_id),
                "version_id": str(version_id),
                "element_id": str(element_id),
                "created_at": now,
            },
        )
    return item_id


async def _set_membership_role(*, org_id: UUID, user_id: UUID, role: str) -> None:
    now = datetime.now(UTC)
    async with session_scope() as session:
        membership_id = (
            await session.execute(
                sa.text(
                    "SELECT id FROM memberships "
                    "WHERE org_id = :org_id AND user_id = :user_id"
                ),
                {"org_id": str(org_id), "user_id": str(user_id)},
            )
        ).scalar_one()
        await session.execute(
            sa.text(
                "UPDATE memberships SET role = :role WHERE org_id = :org_id AND user_id = :user_id"
            ),
            {"role": role, "org_id": str(org_id), "user_id": str(user_id)},
        )
        if role not in {"owner", "admin"}:
            project_id = (
                await session.execute(
                    sa.text("SELECT id FROM projects WHERE org_id = :org_id"),
                    {"org_id": str(org_id)},
                )
            ).scalar_one()
            await session.execute(
                sa.text(
                    "INSERT INTO project_grants "
                    "(id, org_id, project_id, membership_id, granted_at) "
                    "VALUES (:id, :org_id, :project_id, :membership_id, :granted_at)"
                ),
                {
                    "id": str(uuid6.uuid7()),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                    "membership_id": str(membership_id),
                    "granted_at": now,
                },
            )


async def _add_member_with_role(
    client: AsyncClient, *, org_id: UUID, role: str, suffix: str
) -> UUID:
    authenticated_cookies = dict(client.cookies)
    user_id, _email = await _register_actor(client, suffix=suffix)
    now = datetime.now(UTC)
    membership_id = uuid6.uuid7()
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO memberships (id, org_id, user_id, role, status, created_at) "
                "VALUES (:id, :org_id, :user_id, :role, 'active', :created_at)"
            ),
            {
                "id": str(membership_id),
                "org_id": str(org_id),
                "user_id": str(user_id),
                "role": role,
                "created_at": now,
            },
        )
        if role not in {"owner", "admin"}:
            project_id = (
                await session.execute(
                    sa.text("SELECT id FROM projects WHERE org_id = :org_id"),
                    {"org_id": str(org_id)},
                )
            ).scalar_one()
            await session.execute(
                sa.text(
                    "INSERT INTO project_grants "
                    "(id, org_id, project_id, membership_id, granted_at) "
                    "VALUES (:id, :org_id, :project_id, :membership_id, :granted_at)"
                ),
                {
                    "id": str(uuid6.uuid7()),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                    "membership_id": str(membership_id),
                    "granted_at": now,
                },
            )
    client.cookies.clear()
    client.cookies.update(authenticated_cookies)
    return user_id


async def _setup(client: AsyncClient, *, suffix: str) -> Fixture:
    actor_id, actor_email = await _register_actor(client, suffix=suffix)
    org_id, project_id = await _create_org_and_project(client, suffix=suffix)
    item_id = await _insert_item(org_id=org_id, project_id=project_id)
    await _set_membership_role(org_id=org_id, user_id=actor_id, role="reviewer")
    return Fixture(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        actor_id=actor_id,
        actor_email=actor_email,
    )


async def _post_comment(
    client: AsyncClient, fixture: Fixture, *, body: dict, idempotency_key: str
):
    request_body = dict(body)
    if "content" in request_body:
        request_body["body"] = request_body.pop("content")
    async with session_scope() as session:
        current_version = (
            await session.execute(
                sa.text("SELECT version FROM clearance_items WHERE id = :item_id"),
                {"item_id": str(fixture.item_id)},
            )
        ).scalar_one()
    request_body.setdefault("expectedVersion", current_version)
    request_body.setdefault("intentHash", uuid4().hex + uuid4().hex)
    return await client.post(
        _comments_path(fixture.org_id, fixture.project_id, fixture.item_id),
        json=request_body,
        headers={"Idempotency-Key": idempotency_key},
    )


async def _counts(fixture: Fixture) -> tuple[int, int, int, int, int, int, int]:
    async with session_scope() as session:
        comments = (
            await session.execute(
                sa.text("SELECT count(*) FROM governed_comments WHERE item_id = :item_id"),
                {"item_id": str(fixture.item_id)},
            )
        ).scalar_one()
        revisions = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM governed_comment_revisions r "
                    "JOIN governed_comments c ON c.id = r.comment_id "
                    "WHERE c.item_id = :item_id"
                ),
                {"item_id": str(fixture.item_id)},
            )
        ).scalar_one()
        mentions = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM governed_comment_mentions m "
                    "JOIN governed_comments c ON c.id = m.comment_id "
                    "WHERE c.item_id = :item_id"
                ),
                {"item_id": str(fixture.item_id)},
            )
        ).scalar_one()
        receipts = (
            await session.execute(
                sa.text("SELECT count(*) FROM governed_command_receipts WHERE item_id = :item_id"),
                {"item_id": str(fixture.item_id)},
            )
        ).scalar_one()
        audit = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM authoritative_audit_events "
                    "WHERE org_id = :org_id AND project_id = :project_id AND target_type = 'comment'"
                ),
                {"org_id": str(fixture.org_id), "project_id": str(fixture.project_id)},
            )
        ).scalar_one()
        outbox = (
            await session.execute(
                sa.text("SELECT count(*) FROM governed_outbox WHERE project_id = :project_id"),
                {"project_id": str(fixture.project_id)},
            )
        ).scalar_one()
        item_version = (
            await session.execute(
                sa.text("SELECT version FROM clearance_items WHERE id = :item_id"),
                {"item_id": str(fixture.item_id)},
            )
        ).scalar_one()
    return (
        int(comments),
        int(revisions),
        int(mentions),
        int(receipts),
        int(audit),
        int(outbox),
        int(item_version),
    )


# --------------------------------------------------------------------------- #
# Group 4: Atomic commit + dual rollback.
# --------------------------------------------------------------------------- #


async def test_accepted_comment_stages_deduped_schema_versioned_outbox_event() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="happy")
        target = await _add_member_with_role(
            client, org_id=fixture.org_id, role="editor", suffix="happy-target"
        )
        response = await _post_comment(
            client,
            fixture,
            body={"content": "Atomic write check.", "mentions": [str(target)]},
            idempotency_key=_idempotency_key("happy"),
        )
        assert response.status_code == 201, response.text
        comment_id = response.json()["data"]["commentId"]

    async with session_scope() as session:
        rows = (
            await session.execute(
                sa.text(
                    "SELECT event_type, schema_version, dedupe_key "
                    "FROM governed_outbox WHERE project_id = :project_id"
                ),
                {"project_id": str(fixture.project_id)},
            )
        ).all()
    assert len(rows) == 1
    event = rows[0]
    assert event.schema_version >= 1
    assert event.event_type.endswith(".v1")
    # The dedupe key is unique to this comment so the write can never enqueue twice.
    assert str(comment_id) in event.dedupe_key

    comments, revisions, mentions, receipts, audit, outbox, item_version = await _counts(
        fixture
    )
    assert comments == 1
    assert revisions == 1
    assert mentions == 1
    assert receipts == 1
    assert audit == 1
    assert outbox == 1
    assert item_version == 2


async def test_audit_failure_rolls_back_the_entire_comment_command() -> None:
    from clearcut.collaboration.application import comments as comments_module

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("audit sink unavailable")

    async with await _client() as client:
        fixture = await _setup(client, suffix="audit-rollback")
        target = await _add_member_with_role(
            client, org_id=fixture.org_id, role="editor", suffix="audit-target"
        )
        original = comments_module.insert_authoritative_audit
        comments_module.insert_authoritative_audit = _boom  # type: ignore[assignment]
        try:
            with pytest.raises(RuntimeError, match="audit sink unavailable"):
                await _post_comment(
                    client,
                    fixture,
                    body={"content": "Should roll back.", "mentions": [str(target)]},
                    idempotency_key=_idempotency_key("audit-rollback"),
                )
        finally:
            comments_module.insert_authoritative_audit = original  # type: ignore[assignment]

    comments, revisions, mentions, receipts, audit, outbox, item_version = await _counts(
        fixture
    )
    assert comments == 0
    assert revisions == 0
    assert mentions == 0
    assert receipts == 0
    assert audit == 0
    assert outbox == 0
    assert item_version == 1


async def test_outbox_failure_rolls_back_the_entire_comment_command() -> None:
    from clearcut.collaboration.application import comments as comments_module

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("outbox sink unavailable")

    async with await _client() as client:
        fixture = await _setup(client, suffix="outbox-rollback")
        target = await _add_member_with_role(
            client, org_id=fixture.org_id, role="editor", suffix="outbox-target"
        )
        original = comments_module.insert_outbox_event
        comments_module.insert_outbox_event = _boom  # type: ignore[assignment]
        try:
            with pytest.raises(RuntimeError, match="outbox sink unavailable"):
                await _post_comment(
                    client,
                    fixture,
                    body={"content": "Should roll back too.", "mentions": [str(target)]},
                    idempotency_key=_idempotency_key("outbox-rollback"),
                )
        finally:
            comments_module.insert_outbox_event = original  # type: ignore[assignment]

    comments, revisions, mentions, receipts, audit, outbox, item_version = await _counts(
        fixture
    )
    assert comments == 0
    assert revisions == 0
    assert mentions == 0
    assert receipts == 0
    assert audit == 0
    assert outbox == 0
    assert item_version == 1



async def test_revision_mentions_receipt_audit_and_outbox_commit_atomically() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="revision-atomic")
        root = await _post_comment(
            client,
            fixture,
            body={
                "body": "Root before atomic revision.",
                "mentions": [],
                "expectedVersion": 1,
                "intentHash": "d1" * 32,
            },
            idempotency_key=_idempotency_key("revision-atomic-root"),
        )
        assert root.status_code == 201, root.text
        comment_id = root.json()["data"]["commentId"]
        target = await _add_member_with_role(
            client,
            org_id=fixture.org_id,
            role="editor",
            suffix="revision-atomic-target",
        )
        revised = await client.post(
            (
                f"/api/v1/organizations/{fixture.org_id}/projects/{fixture.project_id}"
                f"/clearance-items/{fixture.item_id}/comments/{comment_id}:revise"
            ),
            json={
                "body": "Atomic revision with mention.",
                "mentions": [str(target)],
                "expectedVersion": 2,
                "intentHash": "e1" * 32,
            },
            headers={"Idempotency-Key": _idempotency_key("revision-atomic-revise")},
        )
        assert revised.status_code == 200, revised.text

    assert await _counts(fixture) == (1, 2, 1, 2, 2, 2, 3)
    async with session_scope() as session:
        dedupe_keys = (
            await session.execute(
                sa.text(
                    "SELECT dedupe_key FROM governed_outbox "
                    "WHERE project_id = :project_id"
                ),
                {"project_id": str(fixture.project_id)},
            )
        ).scalars().all()
    assert len(dedupe_keys) == len(set(dedupe_keys)) == 2



async def test_revision_outbox_failure_rolls_back_revision_mentions_receipt_audit_and_version() -> None:
    from clearcut.collaboration.application import comments as comments_module

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("revision outbox unavailable")

    async with await _client() as client:
        fixture = await _setup(client, suffix="revision-outbox-rollback")
        root = await _post_comment(
            client,
            fixture,
            body={
                "body": "Committed root before failed revision.",
                "mentions": [],
                "expectedVersion": 1,
                "intentHash": "f1" * 32,
            },
            idempotency_key=_idempotency_key("revision-rollback-root"),
        )
        assert root.status_code == 201, root.text
        comment_id = root.json()["data"]["commentId"]
        target = await _add_member_with_role(
            client,
            org_id=fixture.org_id,
            role="editor",
            suffix="revision-rollback-target",
        )
        original = comments_module.insert_outbox_event
        comments_module.insert_outbox_event = _boom  # type: ignore[assignment]
        try:
            with pytest.raises(RuntimeError, match="revision outbox unavailable"):
                await client.post(
                    (
                        f"/api/v1/organizations/{fixture.org_id}/projects/{fixture.project_id}"
                        f"/clearance-items/{fixture.item_id}/comments/{comment_id}:revise"
                    ),
                    json={
                        "body": "This entire revision must roll back.",
                        "mentions": [str(target)],
                        "expectedVersion": 2,
                        "intentHash": "01" * 32,
                    },
                    headers={
                        "Idempotency-Key": _idempotency_key("revision-rollback-revise")
                    },
                )
        finally:
            comments_module.insert_outbox_event = original  # type: ignore[assignment]

    assert await _counts(fixture) == (1, 1, 0, 1, 1, 1, 2)



async def test_collaboration_port_uses_typed_membership_and_outbox_values() -> None:
    from typing import get_type_hints

    from clearcut.collaboration.ports.repository import (
        ActiveMember,
        CollaborationRepositoryPort,
        PendingOutboxEvent,
    )

    member_hints = get_type_hints(CollaborationRepositoryPort.load_active_project_member)
    role_hints = get_type_hints(CollaborationRepositoryPort.load_active_member_with_role)
    outbox_hints = get_type_hints(CollaborationRepositoryPort.stage_outbox_event)

    assert member_hints["return"] is ActiveMember
    assert role_hints["return"] is ActiveMember
    assert outbox_hints["event"] is PendingOutboxEvent

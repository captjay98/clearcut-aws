"""Behavioral tests for the persisted collaboration comment slice (Task 8).

These tests pin the canonical operational ``addComment``, ``replyToComment``, and
``reviseComment`` operations end to end against the real migrated 0030 schema
(``governed_comments``, ``governed_comment_revisions``,
``governed_comment_mentions``, ``governed_outbox`` and the authoritative audit
ledger). A comment is an *operational* collaboration write by an active
authorized project member — not a governed legal action — so it never advances
the clearance item's optimistic version and never asserts a legal conclusion.
Each accepted write still persists its rows, the authoritative audit event, and a
schema-versioned, deduplicated outbox event in one atomic transaction, and only
typed results or typed governed-command errors cross the boundary.

Group 1 covers comment creation and the DB-enforced single reply level:
exact item scope, the active-authorized-member requirement, blank-content
rejection, a one-level reply success, a reply-to-reply rejection that surfaces as
a typed error (never a 500), and immutable parent identity.

Group 2 covers append-only immutable revisions: each revision appends a record
with a positive, per-comment-unique ordinal, preserves attributable
author/time/history, and never destructively overwrites the original content.

Group 3 covers authorized mentions: recipients must be active authorized project
members, the actor is excluded, foreign/inactive recipients are rejected,
duplicate recipient IDs are handled, and mentions are recipient user IDs only
(no username parsing as authority).
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
    # RequiredIdempotencyKey is 16..128 chars; pad the label to satisfy it.
    return f"idem-{label}-{uuid4().hex}"


def _comments_path(org_id: UUID, project_id: UUID, item_id: UUID) -> str:
    return (
        f"/api/v1/organizations/{org_id}/projects/{project_id}"
        f"/clearance-items/{item_id}/comments"
    )


def _reply_path(org_id: UUID, project_id: UUID, item_id: UUID, comment_id: UUID) -> str:
    return (
        f"/api/v1/organizations/{org_id}/projects/{project_id}"
        f"/clearance-items/{item_id}/comments/{comment_id}:reply"
    )


def _revise_path(org_id: UUID, project_id: UUID, item_id: UUID, comment_id: UUID) -> str:
    return (
        f"/api/v1/organizations/{org_id}/projects/{project_id}"
        f"/clearance-items/{item_id}/comments/{comment_id}:revise"
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


@dataclass(frozen=True)
class Actor:
    user_id: UUID
    email: str


async def _register_actor(client: AsyncClient, *, suffix: str) -> Actor:
    email = f"comment-{suffix}-{uuid4().hex}@example.com"
    registration = await client.post(
        "/api/v1/users",
        json={"name": f"Commenter {suffix}", "email": email, "password": _PASSWORD},
    )
    assert registration.status_code == 201, registration.text
    return Actor(user_id=UUID(registration.json()["data"]["userId"]), email=email)


async def _login(client: AsyncClient, *, email: str) -> None:
    response = await client.post(
        "/api/v1/sessions",
        json={"email": email, "password": _PASSWORD},
    )
    assert response.status_code == 201, response.text


async def _create_org_and_project(client: AsyncClient, *, suffix: str) -> tuple[UUID, UUID]:
    slug_suffix = suffix.replace("_", "-")
    organization = await client.post(
        "/api/v1/organizations",
        json={
            "name": f"Comment Studio {suffix}",
            "slug": f"cmt-{slug_suffix}-{uuid4().hex[:8]}",
        },
    )
    assert organization.status_code == 201, organization.text
    org_id = UUID(organization.json()["data"]["orgId"])
    project = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        json={"title": f"Comment Project {suffix}"},
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
                "VALUES (:id, :org_id, :project_id, 'Comment test', :created_at)"
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
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "UPDATE memberships SET role = :role WHERE org_id = :org_id AND user_id = :user_id"
            ),
            {"role": role, "org_id": str(org_id), "user_id": str(user_id)},
        )


async def _deactivate_membership(*, org_id: UUID, user_id: UUID) -> None:
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "UPDATE memberships SET status = 'inactive' "
                "WHERE org_id = :org_id AND user_id = :user_id"
            ),
            {"org_id": str(org_id), "user_id": str(user_id)},
        )


async def _grant_project(*, org_id: UUID, project_id: UUID, user_id: UUID) -> None:
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
                "INSERT INTO project_grants "
                "(id, org_id, project_id, membership_id, granted_at) "
                "VALUES (:id, :org_id, :project_id, :membership_id, :granted_at)"
            ),
            {
                "id": str(uuid6.uuid7()),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "membership_id": str(membership_id),
                "granted_at": datetime.now(UTC),
            },
        )


async def _add_member_with_role(
    client: AsyncClient,
    *,
    org_id: UUID,
    role: str,
    suffix: str,
    grant_project: bool = True,
) -> Actor:
    """Register a second member without changing the caller's authenticated actor."""
    authenticated_cookies = dict(client.cookies)
    actor = await _register_actor(client, suffix=suffix)
    membership_id = uuid6.uuid7()
    now = datetime.now(UTC)
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO memberships (id, org_id, user_id, role, status, created_at) "
                "VALUES (:id, :org_id, :user_id, :role, 'active', :created_at)"
            ),
            {
                "id": str(membership_id),
                "org_id": str(org_id),
                "user_id": str(actor.user_id),
                "role": role,
                "created_at": now,
            },
        )
        if grant_project and role not in {"owner", "admin"}:
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
    return actor


async def _setup(client: AsyncClient, *, suffix: str, role: str = "reviewer") -> Fixture:
    actor = await _register_actor(client, suffix=suffix)
    org_id, project_id = await _create_org_and_project(client, suffix=suffix)
    item_id = await _insert_item(org_id=org_id, project_id=project_id)
    await _set_membership_role(org_id=org_id, user_id=actor.user_id, role=role)
    if role not in {"owner", "admin"}:
        await _grant_project(org_id=org_id, project_id=project_id, user_id=actor.user_id)
    return Fixture(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        actor_id=actor.user_id,
        actor_email=actor.email,
    )


def _comment_body(
    *,
    content: str = "Please double-check the trademark status on this item.",
    mentions: list[str | UUID] | None = None,
) -> dict:
    body: dict = {"body": content}
    if mentions is not None:
        body["mentions"] = [str(m) for m in mentions]
    return body


async def _post_comment(
    client: AsyncClient,
    fixture: Fixture,
    *,
    body: dict,
    idempotency_key: str,
    org_id: UUID | None = None,
    project_id: UUID | None = None,
    item_id: UUID | None = None,
):
    request_body = dict(body)
    if "content" in request_body:
        request_body["body"] = request_body.pop("content")
    target_item_id = item_id or fixture.item_id
    async with session_scope() as session:
        current_version = (
            await session.execute(
                sa.text("SELECT version FROM clearance_items WHERE id = :item_id"),
                {"item_id": str(target_item_id)},
            )
        ).scalar_one_or_none()
    request_body.setdefault("expectedVersion", current_version or 1)
    request_body.setdefault("intentHash", uuid4().hex + uuid4().hex)
    return await client.post(
        _comments_path(
            org_id or fixture.org_id,
            project_id or fixture.project_id,
            target_item_id,
        ),
        json=request_body,
        headers={"Idempotency-Key": idempotency_key},
    )


async def _post_reply(
    client: AsyncClient,
    fixture: Fixture,
    parent_comment_id: UUID,
    *,
    body: dict,
    idempotency_key: str,
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
        _reply_path(
            fixture.org_id, fixture.project_id, fixture.item_id, parent_comment_id
        ),
        json=request_body,
        headers={"Idempotency-Key": idempotency_key},
    )


async def _post_revise(
    client: AsyncClient,
    fixture: Fixture,
    comment_id: UUID,
    *,
    body: dict,
    idempotency_key: str,
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
        _revise_path(fixture.org_id, fixture.project_id, fixture.item_id, comment_id),
        json=request_body,
        headers={"Idempotency-Key": idempotency_key},
    )


async def _add_root_comment(
    client: AsyncClient,
    fixture: Fixture,
    *,
    content: str = "Root comment for later threading.",
    label: str = "seed",
    mentions: list[str | UUID] | None = None,
) -> UUID:
    response = await _post_comment(
        client,
        fixture,
        body=_comment_body(content=content, mentions=mentions),
        idempotency_key=_idempotency_key(label),
    )
    assert response.status_code == 201, response.text
    return UUID(response.json()["data"]["commentId"])


# --------------------------------------------------------------------------- #
# Group 1: Comment creation and the DB-enforced single reply level.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("role", ["owner", "admin", "editor", "reviewer"])
async def test_active_authorized_member_may_add_comment(role: str) -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix=f"add-{role}", role=role)
        response = await _post_comment(
            client, fixture, body=_comment_body(), idempotency_key=_idempotency_key(role)
        )

    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["itemId"] == str(fixture.item_id)
    assert data["commentId"]
    assert "parentId" not in data
    assert response.json()["meta"]["requestId"]


async def test_comment_is_scoped_to_the_exact_item_and_attributable() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="scope")
        comment_id = await _add_root_comment(client, fixture, label="scope")

    async with session_scope() as session:
        row = (
            await session.execute(
                sa.text(
                    "SELECT org_id, project_id, item_id, author_id, parent_comment_id, reply_depth "
                    "FROM governed_comments WHERE id = :id"
                ),
                {"id": str(comment_id)},
            )
        ).one()
    assert str(row.org_id) == str(fixture.org_id)
    assert str(row.project_id) == str(fixture.project_id)
    assert str(row.item_id) == str(fixture.item_id)
    assert str(row.author_id) == str(fixture.actor_id)
    assert row.parent_comment_id is None
    assert row.reply_depth == 0


async def test_non_member_may_not_comment_403() -> None:
    async with await _client() as owner, await _client() as outsider:
        fixture = await _setup(owner, suffix="member-owner")
        # A registered user who is not a member of the org.
        await _register_actor(outsider, suffix="outsider")
        # The outsider must first authenticate; then attempt to comment in the
        # owner's org where they hold no membership.
        response = await _post_comment(
            outsider,
            fixture,
            body=_comment_body(),
            idempotency_key=_idempotency_key("outsider"),
        )

    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "permission_denied"


async def test_deactivated_member_may_not_comment_403() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="deactivated")
        await _deactivate_membership(org_id=fixture.org_id, user_id=fixture.actor_id)
        response = await _post_comment(
            client, fixture, body=_comment_body(), idempotency_key=_idempotency_key("deactivated")
        )

    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "permission_denied"
    # No comment row persisted for a denied actor.
    async with session_scope() as session:
        count = (
            await session.execute(
                sa.text("SELECT count(*) FROM governed_comments WHERE item_id = :item_id"),
                {"item_id": str(fixture.item_id)},
            )
        ).scalar_one()
    assert count == 0


@pytest.mark.parametrize("content", ["", "   ", "\n\t "])
async def test_blank_comment_content_is_rejected_422(content: str) -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="blank")
        response = await _post_comment(
            client,
            fixture,
            body={"content": content},
            idempotency_key=_idempotency_key("blank"),
        )

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "validation_failed"


async def test_unknown_item_is_safe_not_found() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="unknown-item")
        response = await _post_comment(
            client,
            fixture,
            body=_comment_body(),
            idempotency_key=_idempotency_key("unknown"),
            item_id=uuid6.uuid7(),
        )

    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "not_found"


async def test_one_level_reply_succeeds_and_is_attributable() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="reply-ok")
        root_id = await _add_root_comment(client, fixture, label="reply-root")
        reply = await _post_reply(
            client,
            fixture,
            root_id,
            body=_comment_body(content="Confirmed against the USPTO snapshot."),
            idempotency_key=_idempotency_key("reply-ok"),
        )

    assert reply.status_code == 201, reply.text
    data = reply.json()["data"]
    assert data["parentId"] == str(root_id)
    async with session_scope() as session:
        row = (
            await session.execute(
                sa.text(
                    "SELECT parent_comment_id, reply_depth, author_id "
                    "FROM governed_comments WHERE id = :id"
                ),
                {"id": str(data["commentId"])},
            )
        ).one()
    assert str(row.parent_comment_id) == str(root_id)
    assert row.reply_depth == 1
    assert str(row.author_id) == str(fixture.actor_id)


async def test_reply_to_reply_is_rejected_as_typed_error_not_500() -> None:
    """The DB single-reply-level guarantee (composite FK + CHECK) must surface as
    a typed validation error (422), never an unhandled 500."""
    async with await _client() as client:
        fixture = await _setup(client, suffix="reply-to-reply")
        root_id = await _add_root_comment(client, fixture, label="grand-root")
        first_reply = await _post_reply(
            client,
            fixture,
            root_id,
            body=_comment_body(content="First-level reply."),
            idempotency_key=_idempotency_key("first-reply"),
        )
        assert first_reply.status_code == 201, first_reply.text
        reply_id = UUID(first_reply.json()["data"]["commentId"])
        grandchild = await _post_reply(
            client,
            fixture,
            reply_id,
            body=_comment_body(content="Illegal second-level reply."),
            idempotency_key=_idempotency_key("grandchild"),
        )

    assert grandchild.status_code == 422, grandchild.text
    assert grandchild.json()["error"]["code"] == "validation_failed"
    # No grandchild row is persisted.
    async with session_scope() as session:
        depth_two = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM governed_comments "
                    "WHERE item_id = :item_id AND reply_depth >= 2"
                ),
                {"item_id": str(fixture.item_id)},
            )
        ).scalar_one()
    assert depth_two == 0


async def test_reply_to_unknown_parent_is_safe_not_found() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="reply-unknown")
        response = await _post_reply(
            client,
            fixture,
            uuid6.uuid7(),
            body=_comment_body(content="Reply to a nonexistent parent."),
            idempotency_key=_idempotency_key("reply-unknown"),
        )

    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "not_found"


async def test_foreign_parent_reply_has_safe_not_found_parity() -> None:
    async with await _client() as owner, await _client() as foreign:
        owned = await _setup(owner, suffix="owned-reply-parity")
        alien = await _setup(foreign, suffix="foreign-reply-parity")
        alien_root = await _add_root_comment(foreign, alien, label="alien-root")
        # Try to reply to the alien parent through the owned tenant scope.
        response = await _post_reply(
            owner,
            owned,
            alien_root,
            body=_comment_body(content="Cross-tenant reply attempt."),
            idempotency_key=_idempotency_key("foreign-reply"),
        )

    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "not_found"


async def test_parent_identity_is_immutable_across_reply_and_revision() -> None:
    """A reply's parent identity is fixed at creation; a later revision of the
    reply never rewrites its parent linkage."""
    async with await _client() as client:
        fixture = await _setup(client, suffix="immutable-parent")
        root_id = await _add_root_comment(client, fixture, label="imm-root")
        reply = await _post_reply(
            client,
            fixture,
            root_id,
            body=_comment_body(content="Reply whose parent stays fixed."),
            idempotency_key=_idempotency_key("imm-reply"),
        )
        reply_id = UUID(reply.json()["data"]["commentId"])
        revise = await _post_revise(
            client,
            fixture,
            reply_id,
            body=_comment_body(content="Revised reply body; parent must not change."),
            idempotency_key=_idempotency_key("imm-revise"),
        )
        assert revise.status_code == 200, revise.text

    async with session_scope() as session:
        row = (
            await session.execute(
                sa.text(
                    "SELECT parent_comment_id, reply_depth FROM governed_comments WHERE id = :id"
                ),
                {"id": str(reply_id)},
            )
        ).one()
    assert str(row.parent_comment_id) == str(root_id)
    assert row.reply_depth == 1


async def test_comment_never_asserts_legal_conclusion() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="legal-boundary")
        response = await _post_comment(
            client, fixture, body=_comment_body(), idempotency_key=_idempotency_key("legal")
        )

    assert response.status_code == 201, response.text
    body_text = response.text.lower()
    for forbidden in ("legally cleared", "legal clearance", "clearance guaranteed"):
        assert forbidden not in body_text


# --------------------------------------------------------------------------- #
# Group 2: Append-only immutable revisions.
# --------------------------------------------------------------------------- #


async def test_creating_a_comment_seeds_the_first_revision() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="rev-seed")
        comment_id = await _add_root_comment(
            client, fixture, content="Original body.", label="rev-seed"
        )

    async with session_scope() as session:
        rows = (
            await session.execute(
                sa.text(
                    "SELECT ordinal, body FROM governed_comment_revisions "
                    "WHERE comment_id = :id ORDER BY ordinal"
                ),
                {"id": str(comment_id)},
            )
        ).all()
    assert [(r.ordinal, r.body) for r in rows] == [(1, "Original body.")]


async def test_revisions_append_with_positive_unique_ordinals() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="rev-append")
        comment_id = await _add_root_comment(
            client, fixture, content="Version one.", label="rev-append"
        )
        second = await _post_revise(
            client,
            fixture,
            comment_id,
            body=_comment_body(content="Version two."),
            idempotency_key=_idempotency_key("rev-2"),
        )
        assert second.status_code == 200, second.text
        third = await _post_revise(
            client,
            fixture,
            comment_id,
            body=_comment_body(content="Version three."),
            idempotency_key=_idempotency_key("rev-3"),
        )
        assert third.status_code == 200, third.text

    async with session_scope() as session:
        rows = (
            await session.execute(
                sa.text(
                    "SELECT ordinal, body FROM governed_comment_revisions "
                    "WHERE comment_id = :id ORDER BY ordinal"
                ),
                {"id": str(comment_id)},
            )
        ).all()
    ordinals = [r.ordinal for r in rows]
    assert ordinals == [1, 2, 3]
    assert all(o >= 1 for o in ordinals)
    assert len(ordinals) == len(set(ordinals))
    assert [r.body for r in rows] == ["Version one.", "Version two.", "Version three."]


async def test_revision_preserves_original_content_non_destructively() -> None:
    """A revision appends; it never overwrites the original revision body."""
    async with await _client() as client:
        fixture = await _setup(client, suffix="rev-nondestructive")
        comment_id = await _add_root_comment(
            client, fixture, content="First body kept forever.", label="rev-nd"
        )
        revise = await _post_revise(
            client,
            fixture,
            comment_id,
            body=_comment_body(content="Second body added."),
            idempotency_key=_idempotency_key("rev-nd-2"),
        )
        assert revise.status_code == 200, revise.text

    async with session_scope() as session:
        first_body = (
            await session.execute(
                sa.text(
                    "SELECT body FROM governed_comment_revisions "
                    "WHERE comment_id = :id AND ordinal = 1"
                ),
                {"id": str(comment_id)},
            )
        ).scalar_one()
    assert first_body == "First body kept forever."


async def test_revision_records_attributable_author_time_and_history() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="rev-attrib")
        comment_id = await _add_root_comment(
            client, fixture, content="History start.", label="rev-attrib"
        )
        revise = await _post_revise(
            client,
            fixture,
            comment_id,
            body=_comment_body(content="History continued."),
            idempotency_key=_idempotency_key("rev-attrib-2"),
        )
        assert revise.status_code == 200, revise.text

    async with session_scope() as session:
        author_id = (
            await session.execute(
                sa.text("SELECT author_id FROM governed_comments WHERE id = :id"),
                {"id": str(comment_id)},
            )
        ).scalar_one()
        rows = (
            await session.execute(
                sa.text(
                    "SELECT ordinal, created_at FROM governed_comment_revisions "
                    "WHERE comment_id = :id ORDER BY ordinal"
                ),
                {"id": str(comment_id)},
            )
        ).all()
    assert str(author_id) == str(fixture.actor_id)
    # Attributable history: two ordered revisions each carrying a creation time.
    assert [r.ordinal for r in rows] == [1, 2]
    assert all(r.created_at is not None for r in rows)


async def test_revise_unknown_comment_is_safe_not_found() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="rev-unknown")
        response = await _post_revise(
            client,
            fixture,
            uuid6.uuid7(),
            body=_comment_body(content="Revising nothing."),
            idempotency_key=_idempotency_key("rev-unknown"),
        )

    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "not_found"


@pytest.mark.parametrize("content", ["", "   "])
async def test_blank_revision_content_is_rejected_422(content: str) -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="rev-blank")
        comment_id = await _add_root_comment(client, fixture, label="rev-blank")
        response = await _post_revise(
            client,
            fixture,
            comment_id,
            body={"content": content},
            idempotency_key=_idempotency_key("rev-blank-2"),
        )

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "validation_failed"


# --------------------------------------------------------------------------- #
# Group 3: Authorized mentions.
# --------------------------------------------------------------------------- #


async def test_mentions_persist_for_active_authorized_members() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="mention-ok")
        target = await _add_member_with_role(
            client, org_id=fixture.org_id, role="editor", suffix="mention-target"
        )
        comment_id = await _add_root_comment(
            client,
            fixture,
            content="Flagging this for review.",
            label="mention-ok",
            mentions=[target.user_id],
        )

    async with session_scope() as session:
        recipients = (
            (
                await session.execute(
                    sa.text(
                        "SELECT recipient_user_id FROM governed_comment_mentions "
                        "WHERE comment_id = :id"
                    ),
                    {"id": str(comment_id)},
                )
            )
            .scalars()
            .all()
        )
    assert [str(r) for r in recipients] == [str(target.user_id)]


async def test_actor_self_mention_is_excluded() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="mention-self")
        target = await _add_member_with_role(
            client, org_id=fixture.org_id, role="reviewer", suffix="mention-other"
        )
        comment_id = await _add_root_comment(
            client,
            fixture,
            content="Mentioning myself and a colleague.",
            label="mention-self",
            mentions=[fixture.actor_id, target.user_id],
        )

    async with session_scope() as session:
        recipients = (
            (
                await session.execute(
                    sa.text(
                        "SELECT recipient_user_id FROM governed_comment_mentions "
                        "WHERE comment_id = :id"
                    ),
                    {"id": str(comment_id)},
                )
            )
            .scalars()
            .all()
        )
    recipient_ids = {str(r) for r in recipients}
    assert str(fixture.actor_id) not in recipient_ids
    assert recipient_ids == {str(target.user_id)}


async def test_foreign_recipient_mention_is_rejected() -> None:
    """A mention of a user who is not an active authorized member of the project
    org is rejected; no comment or mention is persisted."""
    async with await _client() as client, await _client() as foreign:
        fixture = await _setup(client, suffix="mention-foreign")
        outsider = await _register_actor(foreign, suffix="mention-outsider")
        response = await _post_comment(
            client,
            fixture,
            body=_comment_body(
                content="Mentioning a non-member.", mentions=[outsider.user_id]
            ),
            idempotency_key=_idempotency_key("mention-foreign"),
        )

    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "not_found"
    async with session_scope() as session:
        comments = (
            await session.execute(
                sa.text("SELECT count(*) FROM governed_comments WHERE item_id = :item_id"),
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
    assert comments == 0
    assert mentions == 0


async def test_inactive_recipient_mention_is_rejected() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="mention-inactive")
        target = await _add_member_with_role(
            client, org_id=fixture.org_id, role="editor", suffix="mention-inactive-target"
        )
        await _deactivate_membership(org_id=fixture.org_id, user_id=target.user_id)
        response = await _post_comment(
            client,
            fixture,
            body=_comment_body(
                content="Mentioning a deactivated member.", mentions=[target.user_id]
            ),
            idempotency_key=_idempotency_key("mention-inactive"),
        )

    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "not_found"


async def test_duplicate_recipient_ids_are_rejected_by_canonical_contract() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="mention-dupe")
        target = await _add_member_with_role(
            client, org_id=fixture.org_id, role="reviewer", suffix="mention-dupe-target"
        )
        response = await _post_comment(
            client,
            fixture,
            body=_comment_body(
                content="Mentioning the same person twice.",
                mentions=[target.user_id, target.user_id],
            ),
            idempotency_key=_idempotency_key("mention-dupe"),
        )

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "validation_failed"
    async with session_scope() as session:
        count = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM governed_comment_mentions "
                    "WHERE recipient_user_id = :recipient_user_id"
                ),
                {"recipient_user_id": str(target.user_id)},
            )
        ).scalar_one()
    assert count == 0


async def test_usernames_in_content_are_not_treated_as_mention_authority() -> None:
    """Mentions are recipient user IDs only. An ``@username`` string in the
    content body is never parsed into a mention row."""
    async with await _client() as client:
        fixture = await _setup(client, suffix="mention-noparse")
        comment_id = await _add_root_comment(
            client,
            fixture,
            content="Hey @sarah and @mike, please check this license.",
            label="mention-noparse",
        )

    async with session_scope() as session:
        count = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM governed_comment_mentions WHERE comment_id = :id"
                ),
                {"id": str(comment_id)},
            )
        ).scalar_one()
    assert count == 0



async def test_add_comment_matches_canonical_versioned_contract() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="canonical-add")
        response = await _post_comment(
            client,
            fixture,
            body={
                "body": "Canonical attributable comment.",
                "mentions": [],
                "expectedVersion": 1,
                "intentHash": "a" * 64,
            },
            idempotency_key=_idempotency_key("canonical-add"),
        )

    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["itemId"] == str(fixture.item_id)
    assert data["itemVersion"] == 2
    assert data["authorId"] == str(fixture.actor_id)
    assert data["body"] == "Canonical attributable comment."
    assert "parentId" not in data
    assert datetime.fromisoformat(data["createdAt"]).tzinfo is not None
    async with session_scope() as session:
        item_version = (
            await session.execute(
                sa.text("SELECT version FROM clearance_items WHERE id = :item_id"),
                {"item_id": str(fixture.item_id)},
            )
        ).scalar_one()
    assert item_version == 2



async def test_add_comment_same_key_same_intent_replays_original_identity() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="add-replay")
        payload = {
            "body": "Replay exactly once.",
            "mentions": [],
            "expectedVersion": 1,
            "intentHash": "b" * 64,
        }
        key = _idempotency_key("add-replay")
        first = await _post_comment(client, fixture, body=payload, idempotency_key=key)
        second = await _post_comment(client, fixture, body=payload, idempotency_key=key)

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert second.json()["data"] == first.json()["data"]
    async with session_scope() as session:
        counts = (
            await session.execute(
                sa.text(
                    "SELECT "
                    "(SELECT count(*) FROM governed_comments WHERE item_id = :item_id), "
                    "(SELECT count(*) FROM governed_comment_revisions r "
                    " JOIN governed_comments c ON c.id = r.comment_id "
                    " WHERE c.item_id = :item_id), "
                    "(SELECT count(*) FROM governed_command_receipts WHERE item_id = :item_id), "
                    "(SELECT count(*) FROM authoritative_audit_events "
                    " WHERE target_type = 'comment' AND project_id = :project_id), "
                    "(SELECT count(*) FROM governed_outbox WHERE project_id = :project_id)"
                ),
                {"item_id": str(fixture.item_id), "project_id": str(fixture.project_id)},
            )
        ).one()
    assert tuple(counts) == (1, 1, 1, 1, 1)



async def test_reply_comment_matches_canonical_item_scoped_contract() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="canonical-reply")
        root = await _post_comment(
            client,
            fixture,
            body={
                "body": "Canonical root.",
                "mentions": [],
                "expectedVersion": 1,
                "intentHash": "c" * 64,
            },
            idempotency_key=_idempotency_key("canonical-root"),
        )
        assert root.status_code == 201, root.text
        root_id = UUID(root.json()["data"]["commentId"])
        response = await client.post(
            (
                f"/api/v1/organizations/{fixture.org_id}/projects/{fixture.project_id}"
                f"/clearance-items/{fixture.item_id}/comments/{root_id}:reply"
            ),
            json={
                "body": "Canonical one-level reply.",
                "mentions": [],
                "expectedVersion": 2,
                "intentHash": "d" * 64,
            },
            headers={"Idempotency-Key": _idempotency_key("canonical-reply")},
        )

    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["itemId"] == str(fixture.item_id)
    assert data["itemVersion"] == 3
    assert data["parentId"] == str(root_id)
    assert data["body"] == "Canonical one-level reply."



async def test_revise_comment_matches_canonical_item_scoped_contract() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="canonical-revise")
        root = await _post_comment(
            client,
            fixture,
            body={
                "body": "Original canonical body.",
                "mentions": [],
                "expectedVersion": 1,
                "intentHash": "e" * 64,
            },
            idempotency_key=_idempotency_key("canonical-revise-root"),
        )
        assert root.status_code == 201, root.text
        comment_id = UUID(root.json()["data"]["commentId"])
        response = await client.post(
            (
                f"/api/v1/organizations/{fixture.org_id}/projects/{fixture.project_id}"
                f"/clearance-items/{fixture.item_id}/comments/{comment_id}:revise"
            ),
            json={
                "body": "Revised canonical body.",
                "mentions": [],
                "expectedVersion": 2,
                "intentHash": "f" * 64,
            },
            headers={"Idempotency-Key": _idempotency_key("canonical-revise")},
        )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["commentId"] == str(comment_id)
    assert data["itemId"] == str(fixture.item_id)
    assert data["itemVersion"] == 3
    assert data["body"] == "Revised canonical body."



async def test_revision_record_preserves_revising_author_and_aware_time() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="revision-author")
        root = await _post_comment(
            client,
            fixture,
            body={
                "body": "Authored by the original actor.",
                "mentions": [],
                "expectedVersion": 1,
                "intentHash": "1" * 64,
            },
            idempotency_key=_idempotency_key("revision-author-root"),
        )
        assert root.status_code == 201, root.text
        comment_id = UUID(root.json()["data"]["commentId"])
        reviser = await _add_member_with_role(
            client,
            org_id=fixture.org_id,
            role="reviewer",
            suffix="revision-author-reviser",
        )
        await _login(client, email=reviser.email)
        path = (
            f"/api/v1/organizations/{fixture.org_id}/projects/{fixture.project_id}"
            f"/clearance-items/{fixture.item_id}/comments/{comment_id}:revise"
        )
        payload = {
            "body": "Revised by another attributable actor.",
            "mentions": [],
            "expectedVersion": 2,
            "intentHash": "2" * 64,
        }
        key = _idempotency_key("revision-author-revise")
        revised = await client.post(
            path,
            json=payload,
            headers={"Idempotency-Key": key},
        )
        replay = await client.post(
            path,
            json=payload,
            headers={"Idempotency-Key": key},
        )
        assert revised.status_code == 200, revised.text
        assert replay.status_code == 200, replay.text
        assert revised.json()["data"]["authorId"] == str(reviser.user_id)
        assert replay.json()["data"]["authorId"] == str(reviser.user_id)

    async with session_scope() as session:
        row = (
            await session.execute(
                sa.text(
                    "SELECT author_id, created_at FROM governed_comment_revisions "
                    "WHERE comment_id = :comment_id AND ordinal = 2"
                ),
                {"comment_id": str(comment_id)},
            )
        ).one()
    assert str(row.author_id) == str(reviser.user_id)
    assert row.created_at is not None



async def test_revision_persists_explicit_active_recipient_mentions() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="revision-mention")
        root_target = await _add_member_with_role(
            client,
            org_id=fixture.org_id,
            role="editor",
            suffix="revision-mention-root-target",
        )
        revision_target = await _add_member_with_role(
            client,
            org_id=fixture.org_id,
            role="reviewer",
            suffix="revision-mention-revision-target",
        )
        root = await _post_comment(
            client,
            fixture,
            body={
                "body": "Root before revision mention.",
                "mentions": [str(root_target.user_id)],
                "expectedVersion": 1,
                "intentHash": "3" * 64,
            },
            idempotency_key=_idempotency_key("revision-mention-root"),
        )
        assert root.status_code == 201, root.text
        comment_id = UUID(root.json()["data"]["commentId"])
        revised = await client.post(
            (
                f"/api/v1/organizations/{fixture.org_id}/projects/{fixture.project_id}"
                f"/clearance-items/{fixture.item_id}/comments/{comment_id}:revise"
            ),
            json={
                "body": "Revision explicitly mentioning a recipient.",
                "mentions": [str(revision_target.user_id)],
                "expectedVersion": 2,
                "intentHash": "4" * 64,
            },
            headers={"Idempotency-Key": _idempotency_key("revision-mention-revise")},
        )
        assert revised.status_code == 200, revised.text

    async with session_scope() as session:
        recipients_by_revision = (
            await session.execute(
                sa.text(
                    "SELECT r.ordinal, m.recipient_user_id "
                    "FROM governed_comment_revisions r "
                    "JOIN governed_comment_mentions m ON m.revision_id = r.id "
                    "WHERE r.comment_id = :comment_id ORDER BY r.ordinal"
                ),
                {"comment_id": str(comment_id)},
            )
        ).all()
    assert [(row.ordinal, str(row.recipient_user_id)) for row in recipients_by_revision] == [
        (1, str(root_target.user_id)),
        (2, str(revision_target.user_id)),
    ]



async def test_foreign_mention_recipient_has_safe_not_found_contract_shape() -> None:
    async with await _client() as client, await _client() as foreign:
        fixture = await _setup(client, suffix="mention-safe-not-found")
        outsider = await _register_actor(foreign, suffix="mention-safe-outsider")
        response = await _post_comment(
            client,
            fixture,
            body={
                "body": "Do not disclose foreign recipient membership.",
                "mentions": [str(outsider.user_id)],
                "expectedVersion": 1,
                "intentHash": "5" * 64,
            },
            idempotency_key=_idempotency_key("mention-safe-not-found"),
        )

    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "not_found"



async def test_add_comment_stale_version_returns_safe_409_without_writes() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="add-stale")
        response = await _post_comment(
            client,
            fixture,
            body={
                "body": "Stale command must not write.",
                "mentions": [],
                "expectedVersion": 2,
                "intentHash": "6" * 64,
            },
            idempotency_key=_idempotency_key("add-stale"),
        )

    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "conflict_stale_version"
    async with session_scope() as session:
        counts = (
            await session.execute(
                sa.text(
                    "SELECT "
                    "(SELECT count(*) FROM governed_comments WHERE item_id = :item_id), "
                    "(SELECT count(*) FROM governed_command_receipts WHERE item_id = :item_id), "
                    "(SELECT count(*) FROM governed_outbox WHERE project_id = :project_id), "
                    "(SELECT version FROM clearance_items WHERE id = :item_id)"
                ),
                {"item_id": str(fixture.item_id), "project_id": str(fixture.project_id)},
            )
        ).one()
    assert tuple(counts) == (0, 0, 0, 1)



async def test_add_comment_reused_key_with_different_intent_returns_409() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="add-intent-conflict")
        key = _idempotency_key("add-intent-conflict")
        first = await _post_comment(
            client,
            fixture,
            body={
                "body": "Original intent.",
                "mentions": [],
                "expectedVersion": 1,
                "intentHash": "7" * 64,
            },
            idempotency_key=key,
        )
        conflict = await _post_comment(
            client,
            fixture,
            body={
                "body": "Different intent under the same key.",
                "mentions": [],
                "expectedVersion": 1,
                "intentHash": "8" * 64,
            },
            idempotency_key=key,
        )

    assert first.status_code == 201, first.text
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["error"]["code"] == "conflict_idempotency_mismatch"



async def test_reply_same_key_same_intent_replays_without_duplicate_rows() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="reply-replay")
        root = await _post_comment(
            client,
            fixture,
            body={
                "body": "Reply replay root.",
                "mentions": [],
                "expectedVersion": 1,
                "intentHash": "9" * 64,
            },
            idempotency_key=_idempotency_key("reply-replay-root"),
        )
        root_id = UUID(root.json()["data"]["commentId"])
        path = (
            f"/api/v1/organizations/{fixture.org_id}/projects/{fixture.project_id}"
            f"/clearance-items/{fixture.item_id}/comments/{root_id}:reply"
        )
        payload = {
            "body": "Reply exactly once.",
            "mentions": [],
            "expectedVersion": 2,
            "intentHash": "a1" * 32,
        }
        key = _idempotency_key("reply-replay")
        first = await client.post(path, json=payload, headers={"Idempotency-Key": key})
        second = await client.post(
            path,
            json={**payload, "mentions": [str(uuid6.uuid7())]},
            headers={"Idempotency-Key": key},
        )

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert second.json()["data"] == first.json()["data"]
    async with session_scope() as session:
        counts = (
            await session.execute(
                sa.text(
                    "SELECT "
                    "(SELECT count(*) FROM governed_comments WHERE item_id = :item_id), "
                    "(SELECT count(*) FROM governed_comment_revisions r "
                    " JOIN governed_comments c ON c.id = r.comment_id "
                    " WHERE c.item_id = :item_id), "
                    "(SELECT count(*) FROM governed_command_receipts WHERE item_id = :item_id), "
                    "(SELECT count(*) FROM governed_outbox WHERE project_id = :project_id)"
                ),
                {"item_id": str(fixture.item_id), "project_id": str(fixture.project_id)},
            )
        ).one()
    assert tuple(counts) == (2, 2, 2, 2)



async def test_revision_same_key_same_intent_replays_without_duplicate_history() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="revision-replay")
        root = await _post_comment(
            client,
            fixture,
            body={
                "body": "Revision replay root.",
                "mentions": [],
                "expectedVersion": 1,
                "intentHash": "b1" * 32,
            },
            idempotency_key=_idempotency_key("revision-replay-root"),
        )
        comment_id = UUID(root.json()["data"]["commentId"])
        path = (
            f"/api/v1/organizations/{fixture.org_id}/projects/{fixture.project_id}"
            f"/clearance-items/{fixture.item_id}/comments/{comment_id}:revise"
        )
        payload = {
            "body": "Revision exactly once.",
            "mentions": [],
            "expectedVersion": 2,
            "intentHash": "c1" * 32,
        }
        key = _idempotency_key("revision-replay")
        first = await client.post(path, json=payload, headers={"Idempotency-Key": key})
        second = await client.post(
            path,
            json={**payload, "mentions": [str(uuid6.uuid7())]},
            headers={"Idempotency-Key": key},
        )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.json()["data"] == first.json()["data"]
    async with session_scope() as session:
        counts = (
            await session.execute(
                sa.text(
                    "SELECT "
                    "(SELECT count(*) FROM governed_comment_revisions "
                    " WHERE comment_id = :comment_id), "
                    "(SELECT count(*) FROM governed_command_receipts WHERE item_id = :item_id), "
                    "(SELECT count(*) FROM governed_outbox WHERE project_id = :project_id)"
                ),
                {
                    "comment_id": str(comment_id),
                    "item_id": str(fixture.item_id),
                    "project_id": str(fixture.project_id),
                },
            )
        ).one()
    assert tuple(counts) == (2, 2, 2)



async def test_active_non_admin_without_project_grant_may_not_comment() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="actor-no-grant", role="owner")
        ungranted = await _add_member_with_role(
            client,
            org_id=fixture.org_id,
            role="reviewer",
            suffix="actor-no-grant-reviewer",
            grant_project=False,
        )
        await _login(client, email=ungranted.email)
        response = await _post_comment(
            client,
            fixture,
            body={
                "body": "An ungranted reviewer must not reach this project.",
                "mentions": [],
                "expectedVersion": 1,
                "intentHash": "11" * 32,
            },
            idempotency_key=_idempotency_key("actor-no-grant"),
        )

    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "permission_denied"



async def test_same_org_member_without_project_grant_may_not_be_mentioned() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="mention-no-grant", role="owner")
        ungranted = await _add_member_with_role(
            client,
            org_id=fixture.org_id,
            role="reviewer",
            suffix="mention-no-grant-reviewer",
            grant_project=False,
        )
        response = await _post_comment(
            client,
            fixture,
            body=_comment_body(
                content="An ungranted member must not be disclosed as mentionable.",
                mentions=[ungranted.user_id],
            ),
            idempotency_key=_idempotency_key("mention-no-grant"),
        )

    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "not_found"



async def test_add_replay_uses_persisted_body_not_retry_projection() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="replay-persisted-body")
        key = _idempotency_key("replay-persisted-body")
        original = {
            "body": "The immutable persisted body.",
            "mentions": [],
            "expectedVersion": 1,
            "intentHash": "12" * 32,
        }
        retry = {
            **original,
            "body": "A retry payload must never become replay authority.",
            "mentions": [str(uuid6.uuid7())],
        }
        first = await _post_comment(client, fixture, body=original, idempotency_key=key)
        replay = await _post_comment(client, fixture, body=retry, idempotency_key=key)

    assert first.status_code == 201, first.text
    assert replay.status_code == 201, replay.text
    assert replay.json()["data"] == first.json()["data"]
    assert replay.json()["data"]["body"] == original["body"]



async def test_add_replay_key_cannot_cross_item_target() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="add-replay-target")
        second_item_id = await _insert_item(
            org_id=fixture.org_id,
            project_id=fixture.project_id,
        )
        key = _idempotency_key("add-replay-target")
        payload = {
            "body": "Target-bound add replay.",
            "mentions": [],
            "expectedVersion": 1,
            "intentHash": "d1" * 32,
        }
        first = await _post_comment(
            client,
            fixture,
            body=payload,
            idempotency_key=key,
        )
        conflict = await _post_comment(
            client,
            fixture,
            item_id=second_item_id,
            body=payload,
            idempotency_key=key,
        )

    assert first.status_code == 201, first.text
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["error"]["code"] == "conflict_idempotency_mismatch"


async def test_reply_replay_key_cannot_cross_parent_target() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="reply-replay-target")
        first_root = await _add_root_comment(
            client,
            fixture,
            content="First replay target root.",
            label="reply-target-first-root",
        )
        second_root = await _add_root_comment(
            client,
            fixture,
            content="Second replay target root.",
            label="reply-target-second-root",
        )
        key = _idempotency_key("reply-replay-target")
        payload = {
            "body": "Target-bound reply replay.",
            "mentions": [],
            "expectedVersion": 3,
            "intentHash": "d2" * 32,
        }
        first = await client.post(
            _reply_path(
                fixture.org_id,
                fixture.project_id,
                fixture.item_id,
                first_root,
            ),
            json=payload,
            headers={"Idempotency-Key": key},
        )
        conflict = await client.post(
            _reply_path(
                fixture.org_id,
                fixture.project_id,
                fixture.item_id,
                second_root,
            ),
            json=payload,
            headers={"Idempotency-Key": key},
        )

    assert first.status_code == 201, first.text
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["error"]["code"] == "conflict_idempotency_mismatch"


async def test_revision_replay_key_cannot_cross_comment_target() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="revision-replay-target")
        first_comment = await _add_root_comment(
            client,
            fixture,
            content="First revision target.",
            label="revision-target-first",
        )
        second_comment = await _add_root_comment(
            client,
            fixture,
            content="Second revision target.",
            label="revision-target-second",
        )
        key = _idempotency_key("revision-replay-target")
        payload = {
            "body": "Target-bound revision replay.",
            "mentions": [],
            "expectedVersion": 3,
            "intentHash": "d3" * 32,
        }
        first = await client.post(
            _revise_path(
                fixture.org_id,
                fixture.project_id,
                fixture.item_id,
                first_comment,
            ),
            json=payload,
            headers={"Idempotency-Key": key},
        )
        conflict = await client.post(
            _revise_path(
                fixture.org_id,
                fixture.project_id,
                fixture.item_id,
                second_comment,
            ),
            json=payload,
            headers={"Idempotency-Key": key},
        )

    assert first.status_code == 200, first.text
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["error"]["code"] == "conflict_idempotency_mismatch"

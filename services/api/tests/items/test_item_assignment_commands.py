"""Behavioral tests for the governed ``assignClearanceItem`` operation.

These tests pin the canonical ``:assign`` operation end to end: an authorized
member (Owner/Admin/Editor/Reviewer) assigns (or unassigns) exactly one
tenant-and-project-scoped clearance item to an active authorized member of the
same scope, with server-derived capability enforcement, expected-version
optimistic concurrency, intent/idempotency, and a same-transaction
authoritative audit event. Assignment is *operational*: it never asserts a
legal conclusion, only routes work to an accountable human.

The tests drive the mounted FastAPI route (reusing the shared governed-command
kernel and migration 0030 tables) rather than any in-memory stub, so tenant
scope, safe not-found parity, the version guard, idempotent replay, and the
transactional version+receipt+audit boundary are all covered against the real
migrated schema. They also directly assert the two deferred findings for the
assignment endpoint: the previous handler had no capability gate and returned
success on zero-row (absent/foreign) updates.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
import uuid6
from clearcut.database import session_scope
from clearcut.init_db import init_and_seed_db
from clearcut.main import app
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.asyncio

_PASSWORD = "Password123!"


def _intent_hash(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _idempotency_key(label: str) -> str:
    # RequiredIdempotencyKey is 16..128 chars; pad the label to satisfy it.
    return f"idem-{label}-{uuid4().hex}"


def _assign_path(org_id: UUID, project_id: UUID, item_id: UUID) -> str:
    return f"/api/v1/organizations/{org_id}/projects/{project_id}/clearance-items/{item_id}:assign"


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
    assignee_id: UUID


async def _register_actor(client: AsyncClient, *, suffix: str) -> UUID:
    registration = await client.post(
        "/api/v1/users",
        json={
            "name": f"Actor {suffix}",
            "email": f"actor-{suffix}-{uuid4().hex}@example.com",
            "password": _PASSWORD,
        },
    )
    assert registration.status_code == 201, registration.text
    return UUID(registration.json()["data"]["userId"])


async def _create_org_and_project(client: AsyncClient, *, suffix: str) -> tuple[UUID, UUID]:
    slug_suffix = suffix.replace("_", "-")
    organization = await client.post(
        "/api/v1/organizations",
        json={
            "name": f"Assign Studio {suffix}",
            "slug": f"assign-{slug_suffix}-{uuid4().hex[:8]}",
        },
    )
    assert organization.status_code == 201, organization.text
    org_id = UUID(organization.json()["data"]["orgId"])
    project = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        json={"title": f"Assign Project {suffix}"},
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
                "VALUES (:id, :org_id, :project_id, 'Assign test', :created_at)"
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
                "version) "
                "VALUES (:id, :org_id, :project_id, :script_id, :version_id, :element_id, "
                "'products_and_trademarks', 'Acme Corporation', 'unresolved', 'completed', "
                "'detected', 'undisposed', :created_at, 1)"
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


async def _add_member(*, org_id: UUID, role: str = "reviewer", status: str = "active") -> UUID:
    """Create a distinct user with a membership in ``org_id`` and return the user id."""
    user_id = uuid6.uuid7()
    now = datetime.now(UTC)
    async with session_scope() as session:
        await session.execute(
            sa.text("INSERT INTO users (id, email, created_at) VALUES (:id, :email, :created_at)"),
            {"id": str(user_id), "email": f"member-{uuid4().hex}@example.com", "created_at": now},
        )
        await session.execute(
            sa.text(
                "INSERT INTO memberships (id, org_id, user_id, role, status, created_at) "
                "VALUES (:id, :org_id, :user_id, :role, :status, :created_at)"
            ),
            {
                "id": str(uuid6.uuid7()),
                "org_id": str(org_id),
                "user_id": str(user_id),
                "role": role,
                "status": status,
                "created_at": now,
            },
        )
    return user_id


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


async def _setup(client: AsyncClient, *, suffix: str) -> Fixture:
    actor_id = await _register_actor(client, suffix=suffix)
    org_id, project_id = await _create_org_and_project(client, suffix=suffix)
    item_id = await _insert_item(org_id=org_id, project_id=project_id)
    assignee_id = await _add_member(org_id=org_id, role="reviewer", status="active")
    return Fixture(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        actor_id=actor_id,
        assignee_id=assignee_id,
    )


def _body(
    *,
    assignee_id: str,
    expected_version: int = 1,
    intent_hash: str | None = None,
) -> dict:
    return {
        "assigneeId": assignee_id,
        "expectedVersion": expected_version,
        "intentHash": intent_hash or _intent_hash("assign", assignee_id, str(expected_version)),
    }


async def _post_assign(
    client: AsyncClient,
    fixture: Fixture,
    *,
    body: dict,
    idempotency_key: str,
    org_id: UUID | None = None,
    project_id: UUID | None = None,
    item_id: UUID | None = None,
):
    return await client.post(
        _assign_path(
            org_id or fixture.org_id,
            project_id or fixture.project_id,
            item_id or fixture.item_id,
        ),
        json=body,
        headers={"Idempotency-Key": idempotency_key},
    )


# --------------------------------------------------------------------------- #
# Group 1: Authorization / assignee / scope / safe not-found parity.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("role", ["owner", "admin", "editor", "reviewer"])
async def test_authorized_roles_assign_clearance_item(role: str) -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix=f"authz-{role}")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role=role)
        response = await _post_assign(
            client,
            fixture,
            body=_body(assignee_id=str(fixture.assignee_id)),
            idempotency_key=_idempotency_key(role),
        )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["itemId"] == str(fixture.item_id)
    assert data["projectId"] == str(fixture.project_id)
    assert data["version"] == 2
    assert data["assignedTo"] == str(fixture.assignee_id)
    assert response.json()["meta"]["requestId"]

    # The item version advanced and the assignee is persisted.
    async with session_scope() as session:
        row = (
            (
                await session.execute(
                    sa.text(
                        "SELECT version, assigned_to_user_id FROM clearance_items WHERE id = :id"
                    ),
                    {"id": str(fixture.item_id)},
                )
            )
            .mappings()
            .one()
        )
    assert row["version"] == 2
    assert UUID(str(row["assigned_to_user_id"])) == fixture.assignee_id


async def test_viewer_is_denied_with_typed_403_and_no_write() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="deny-viewer")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="viewer")
        response = await _post_assign(
            client,
            fixture,
            body=_body(assignee_id=str(fixture.assignee_id)),
            idempotency_key=_idempotency_key("viewer"),
        )

    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "permission_denied"
    # No assignment, version change, or receipt was written for a denied actor.
    async with session_scope() as session:
        row = (
            (
                await session.execute(
                    sa.text(
                        "SELECT version, assigned_to_user_id FROM clearance_items WHERE id = :id"
                    ),
                    {"id": str(fixture.item_id)},
                )
            )
            .mappings()
            .one()
        )
        receipts = (
            await session.execute(
                sa.text("SELECT count(*) FROM governed_command_receipts WHERE item_id = :item_id"),
                {"item_id": str(fixture.item_id)},
            )
        ).scalar_one()
    assert row["version"] == 1
    assert row["assigned_to_user_id"] is None
    assert receipts == 0


async def test_deactivated_actor_membership_cannot_assign() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="deactivated-actor")
        await _deactivate_membership(org_id=fixture.org_id, user_id=fixture.actor_id)
        response = await _post_assign(
            client,
            fixture,
            body=_body(assignee_id=str(fixture.assignee_id)),
            idempotency_key=_idempotency_key("deactivated-actor"),
        )

    # A deactivated membership is not an active member: denied at the org boundary.
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "permission_denied"


async def test_inactive_assignee_is_rejected() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="inactive-assignee")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")
        # The assignee's membership is deactivated: not an active authorized member.
        await _deactivate_membership(org_id=fixture.org_id, user_id=fixture.assignee_id)
        response = await _post_assign(
            client,
            fixture,
            body=_body(assignee_id=str(fixture.assignee_id)),
            idempotency_key=_idempotency_key("inactive-assignee"),
        )

    # An inactive assignee cannot receive work: a not-found in the authorized scope.
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "not_found"
    async with session_scope() as session:
        row = (
            (
                await session.execute(
                    sa.text(
                        "SELECT version, assigned_to_user_id FROM clearance_items WHERE id = :id"
                    ),
                    {"id": str(fixture.item_id)},
                )
            )
            .mappings()
            .one()
        )
    assert row["version"] == 1
    assert row["assigned_to_user_id"] is None


async def test_foreign_assignee_from_another_org_is_rejected() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client, await _client() as other:
        fixture = await _setup(client, suffix="foreign-assignee")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")
        # A member of an entirely different org is not authorized in this scope.
        await _register_actor(other, suffix="foreign-assignee-owner")
        _foreign_org_id, _ = await _create_org_and_project(other, suffix="foreign-assignee-org")
        foreign_assignee = await _add_member(
            org_id=_foreign_org_id, role="reviewer", status="active"
        )
        response = await _post_assign(
            client,
            fixture,
            body=_body(assignee_id=str(foreign_assignee)),
            idempotency_key=_idempotency_key("foreign-assignee"),
        )

    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "not_found"
    async with session_scope() as session:
        row = (
            (
                await session.execute(
                    sa.text(
                        "SELECT version, assigned_to_user_id FROM clearance_items WHERE id = :id"
                    ),
                    {"id": str(fixture.item_id)},
                )
            )
            .mappings()
            .one()
        )
    assert row["version"] == 1
    assert row["assigned_to_user_id"] is None


async def test_unknown_item_is_safe_not_found_without_success() -> None:
    """The retired handler returned 200 on a zero-row update; the governed
    command must return a neutral 404 when the exact scoped item does not exist."""
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="unknown-item")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")
        missing_item = uuid6.uuid7()
        response = await _post_assign(
            client,
            fixture,
            body=_body(assignee_id=str(fixture.assignee_id)),
            idempotency_key=_idempotency_key("unknown-item"),
            item_id=missing_item,
        )

    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "not_found"


async def test_foreign_item_and_tenant_have_safe_not_found_parity() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as owner, await _client() as foreign:
        owned = await _setup(owner, suffix="owned-parity")
        await _set_membership_role(org_id=owned.org_id, user_id=owned.actor_id, role="reviewer")
        alien = await _setup(foreign, suffix="foreign-parity")

        # Foreign item id addressed through the owner's own authorized scope:
        # the item is not visible, so a neutral 404 (never a 200 or a
        # distinguishing 403) is returned.
        foreign_item_through_owned_scope = await _post_assign(
            owner,
            owned,
            body=_body(assignee_id=str(owned.assignee_id)),
            idempotency_key=_idempotency_key("foreign-item"),
            item_id=alien.item_id,
        )
        # Foreign org/project addressed with the owner's session: membership is
        # absent, denied at the organization boundary.
        foreign_tenant_through_owner_session = await _post_assign(
            owner,
            owned,
            body=_body(assignee_id=str(owned.assignee_id)),
            idempotency_key=_idempotency_key("foreign-tenant"),
            org_id=alien.org_id,
            project_id=alien.project_id,
            item_id=alien.item_id,
        )

    assert foreign_item_through_owned_scope.status_code == 404
    assert foreign_item_through_owned_scope.json()["error"]["code"] == "not_found"
    assert foreign_tenant_through_owner_session.status_code == 403
    assert foreign_tenant_through_owner_session.json()["error"]["code"] == "permission_denied"


async def test_unassign_is_operational_and_allowed() -> None:
    """Assignment is operational: unassigning (clearing the assignee) is a
    first-class outcome that advances the version and audits, never a legal
    judgment. The assignee is cleared by omitting or nulling ``assigneeId``."""
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="unassign")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")
        # First assign to a real member.
        first = await _post_assign(
            client,
            fixture,
            body=_body(assignee_id=str(fixture.assignee_id)),
            idempotency_key=_idempotency_key("unassign-first"),
        )
        assert first.status_code == 200, first.text
        assert first.json()["data"]["version"] == 2

        # Then unassign by clearing the assignee at the advanced version.
        unassign_body = {
            "assigneeId": None,
            "expectedVersion": 2,
            "intentHash": _intent_hash("assign", "none", "2"),
        }
        second = await _post_assign(
            client,
            fixture,
            body=unassign_body,
            idempotency_key=_idempotency_key("unassign-second"),
        )

    assert second.status_code == 200, second.text
    assert second.json()["data"]["version"] == 3
    assert "assignedTo" not in second.json()["data"]
    async with session_scope() as session:
        assigned = (
            await session.execute(
                sa.text("SELECT assigned_to_user_id FROM clearance_items WHERE id = :id"),
                {"id": str(fixture.item_id)},
            )
        ).scalar_one()
    assert assigned is None


# --------------------------------------------------------------------------- #
# Group 2: Version / idempotency / audit.
# --------------------------------------------------------------------------- #


async def test_stale_expected_version_returns_409() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="stale")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")
        first = await _post_assign(
            client,
            fixture,
            body=_body(assignee_id=str(fixture.assignee_id)),
            idempotency_key=_idempotency_key("stale-a"),
        )
        # A different idempotency key with the same stale expected_version=1 must
        # observe the advanced version and lose optimistically.
        second = await _post_assign(
            client,
            fixture,
            body=_body(assignee_id=str(fixture.assignee_id)),
            idempotency_key=_idempotency_key("stale-b"),
        )

    assert first.status_code == 200, first.text
    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] in {"conflict", "conflict_stale_version"}


async def test_same_key_same_intent_returns_original_result() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="replay")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")
        key = _idempotency_key("replay")
        body = _body(assignee_id=str(fixture.assignee_id))
        first = await _post_assign(client, fixture, body=body, idempotency_key=key)
        second = await _post_assign(client, fixture, body=body, idempotency_key=key)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    # The replay reproduces the original result without advancing the version again.
    assert first.json()["data"]["version"] == 2
    assert second.json()["data"]["version"] == 2
    async with session_scope() as session:
        receipts = (
            await session.execute(
                sa.text("SELECT count(*) FROM governed_command_receipts WHERE item_id = :item_id"),
                {"item_id": str(fixture.item_id)},
            )
        ).scalar_one()
    assert receipts == 1


async def test_same_key_different_intent_returns_409() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="intent-conflict")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")
        second_assignee = await _add_member(org_id=fixture.org_id, role="reviewer")
        key = _idempotency_key("intent-conflict")
        first = await _post_assign(
            client,
            fixture,
            body=_body(assignee_id=str(fixture.assignee_id)),
            idempotency_key=key,
        )
        # Same key, different intent (a different assignee): a typed conflict.
        second = await _post_assign(
            client,
            fixture,
            body=_body(assignee_id=str(second_assignee)),
            idempotency_key=key,
        )

    assert first.status_code == 200, first.text
    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] in {"conflict", "conflict_idempotency_mismatch"}


async def test_zero_row_update_never_reports_success() -> None:
    """The retired direct-SQL handler reported success even when the UPDATE
    affected zero rows (absent/foreign item). The governed command must never
    report success for a scoped item that does not exist: a neutral 404, with no
    version change and no receipt."""
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="zero-row")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")
        missing_item = uuid6.uuid7()
        response = await _post_assign(
            client,
            fixture,
            body=_body(assignee_id=str(fixture.assignee_id)),
            idempotency_key=_idempotency_key("zero-row"),
            item_id=missing_item,
        )

    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "not_found"
    async with session_scope() as session:
        receipts = (
            await session.execute(
                sa.text("SELECT count(*) FROM governed_command_receipts WHERE item_id = :item_id"),
                {"item_id": str(missing_item)},
            )
        ).scalar_one()
    assert receipts == 0


async def test_duplicate_idempotency_key_replays_prior_receipt_not_500() -> None:
    """A receipt insert that loses a unique-constraint race is reconciled into
    the prior receipt's idempotent replay, not a 500."""
    from clearcut.commanding.domain import CommandEnvelope
    from clearcut.commanding.sql import insert_command_receipt

    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="dup-key")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")
        key = _idempotency_key("dup-key")
        intent = _intent_hash("assign", str(fixture.assignee_id), "1")

        prior_result_id = uuid6.uuid7()
        async with session_scope() as session:
            envelope = CommandEnvelope(
                org_id=fixture.org_id,
                project_id=fixture.project_id,
                actor_id=fixture.actor_id,
                operation="item.assignment.assign",
                idempotency_key=key,
                intent_hash=intent,
                expected_version=1,
            )
            # A concurrent writer already committed the receipt for this scope.
            await insert_command_receipt(
                session,
                envelope,
                item_id=fixture.item_id,
                resulting_version=2,
                result_id=prior_result_id,
                occurred_at=datetime.now(UTC),
            )

        # Force the service past the pre-commit lookup so the receipt insert is
        # the statement that observes the duplicate, exercising the race branch.
        import clearcut.items.application.assign_item as service_module

        async def _no_prior(_session, _envelope):  # type: ignore[no-untyped-def]
            return None

        original_lookup = service_module.lookup_command_receipt
        service_module.lookup_command_receipt = _no_prior  # type: ignore[assignment]
        try:
            response = await _post_assign(
                client,
                fixture,
                body=_body(assignee_id=str(fixture.assignee_id), intent_hash=intent),
                idempotency_key=key,
            )
        finally:
            service_module.lookup_command_receipt = original_lookup  # type: ignore[assignment]

    # The duplicate receipt is reconciled into the prior result, not a 500.
    assert response.status_code == 200, response.text
    assert response.json()["data"]["version"] == 2
    async with session_scope() as session:
        receipts = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM governed_command_receipts WHERE idempotency_key = :key"
                ),
                {"key": key},
            )
        ).scalar_one()
    assert receipts == 1


async def test_assignment_persists_version_receipt_and_audit_atomically() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="atomic")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")
        key = _idempotency_key("atomic")
        response = await _post_assign(
            client,
            fixture,
            body=_body(assignee_id=str(fixture.assignee_id)),
            idempotency_key=key,
        )

    assert response.status_code == 200, response.text
    async with session_scope() as session:
        version = (
            await session.execute(
                sa.text("SELECT version FROM clearance_items WHERE id = :id"),
                {"id": str(fixture.item_id)},
            )
        ).scalar_one()
        receipts = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM governed_command_receipts WHERE idempotency_key = :key"
                ),
                {"key": key},
            )
        ).scalar_one()
        audits = (
            (
                await session.execute(
                    sa.text(
                        "SELECT action, target_type, target_id FROM authoritative_audit_events "
                        "WHERE target_id = :item_id AND action = 'item.assignment.assigned'"
                    ),
                    {"item_id": str(fixture.item_id)},
                )
            )
            .mappings()
            .all()
        )
    assert version == 2
    assert receipts == 1
    assert len(audits) == 1
    assert audits[0]["target_type"] == "clearance_item"
    assert UUID(str(audits[0]["target_id"])) == fixture.item_id


async def test_authoritative_audit_failure_rolls_back_version_and_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await init_and_seed_db(seed_if_empty=False)

    import clearcut.items.application.assign_item as service_module

    class _InjectedAuditError(RuntimeError):
        pass

    async def _boom(*_args: object, **_kwargs: object) -> None:
        raise _InjectedAuditError("injected authoritative audit failure")

    monkeypatch.setattr(service_module, "insert_authoritative_audit", _boom)

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
        headers={"origin": "http://test"},
    ) as client:
        fixture = await _setup(client, suffix="rollback")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")
        key = _idempotency_key("rollback")
        response = await _post_assign(
            client,
            fixture,
            body=_body(assignee_id=str(fixture.assignee_id)),
            idempotency_key=key,
        )

    # The injected failure surfaces as an internal error, not a partial success.
    assert response.status_code == 500, response.text

    async with session_scope() as session:
        row = (
            (
                await session.execute(
                    sa.text(
                        "SELECT version, assigned_to_user_id FROM clearance_items WHERE id = :id"
                    ),
                    {"id": str(fixture.item_id)},
                )
            )
            .mappings()
            .one()
        )
        receipts = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM governed_command_receipts WHERE idempotency_key = :key"
                ),
                {"key": key},
            )
        ).scalar_one()
    assert row["version"] == 1
    assert row["assigned_to_user_id"] is None
    assert receipts == 0



async def test_assign_with_due_at_persists_and_clearing_it_works() -> None:
    """An optional ``dueAt`` is persisted onto the item in the same governed
    transaction as the assignment, is recorded in the authoritative audit
    payload, and a later assignment with ``dueAt`` null clears it. The due date
    is operational scheduling; it never changes assignee semantics."""
    await init_and_seed_db(seed_if_empty=False)
    due_at = datetime(2030, 6, 1, 12, 0, tzinfo=UTC)
    async with await _client() as client:
        fixture = await _setup(client, suffix="due-at")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")

        # Assign with a due date at version 1.
        first = await _post_assign(
            client,
            fixture,
            body={
                "assigneeId": str(fixture.assignee_id),
                "dueAt": due_at.isoformat(),
                "expectedVersion": 1,
                "intentHash": _intent_hash("assign", str(fixture.assignee_id), "1"),
            },
            idempotency_key=_idempotency_key("due-at-set"),
        )
        assert first.status_code == 200, first.text
        assert first.json()["data"]["version"] == 2
        assert first.json()["data"]["assignedTo"] == str(fixture.assignee_id)

        # The due date is persisted onto the row and recorded in the audit payload.
        async with session_scope() as session:
            persisted_due = (
                await session.execute(
                    sa.text("SELECT due_at FROM clearance_items WHERE id = :id"),
                    {"id": str(fixture.item_id)},
                )
            ).scalar_one()
            audit_payload = (
                await session.execute(
                    sa.text(
                        "SELECT payload_redacted FROM authoritative_audit_events "
                        "WHERE target_id = :item_id AND action = 'item.assignment.assigned' "
                        "ORDER BY occurred_at DESC LIMIT 1"
                    ),
                    {"item_id": str(fixture.item_id)},
                )
            ).scalar_one()
        assert persisted_due is not None
        # Compare instant-in-time; storage may normalize timezone representation.
        assert _as_utc(persisted_due) == due_at
        assert _payload_due_at(audit_payload) == due_at.isoformat()

        # Re-assign at the advanced version with dueAt null to clear it.
        cleared = await _post_assign(
            client,
            fixture,
            body={
                "assigneeId": str(fixture.assignee_id),
                "dueAt": None,
                "expectedVersion": 2,
                "intentHash": _intent_hash("assign", str(fixture.assignee_id), "2"),
            },
            idempotency_key=_idempotency_key("due-at-clear"),
        )
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()["data"]["version"] == 3
        # Assignee is unchanged; only the due date was cleared.
        assert cleared.json()["data"]["assignedTo"] == str(fixture.assignee_id)

    async with session_scope() as session:
        row = (
            (
                await session.execute(
                    sa.text(
                        "SELECT due_at, assigned_to_user_id FROM clearance_items WHERE id = :id"
                    ),
                    {"id": str(fixture.item_id)},
                )
            )
            .mappings()
            .one()
        )
    assert row["due_at"] is None
    assert UUID(str(row["assigned_to_user_id"])) == fixture.assignee_id


def _as_utc(value: object) -> datetime:
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    assert isinstance(parsed, datetime)
    return parsed.astimezone(UTC) if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _payload_due_at(payload: object) -> str | None:
    import json

    data = json.loads(payload) if isinstance(payload, str) else payload
    assert isinstance(data, dict)
    return data.get("dueAt")

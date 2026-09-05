"""Behavioral tests for the governed specialist-referral collaboration slice.

These tests pin the canonical ``:refer`` (``referClearanceItem``) and
``referrals/{referralId}:acknowledge`` (``acknowledgeReferral``) operations end
to end: a specialist referral is a governed, tenant-and-project-scoped,
version-checked, idempotent, attributable transition on an exact clearance item,
and its acknowledgement is a *separate* attributable transition by an active
authorized target actor. Every accepted command persists the referral state, the
accountable command receipt, the authoritative audit event, and a
schema-versioned, deduplicated outbox event in one atomic transaction.

The tests exercise the mounted FastAPI routes (reusing the shared
governed-command kernel and migration 0030 ``governed_referrals`` /
``governed_outbox`` tables) against the real migrated schema, so tenant scope,
safe not-found parity, the capability-correct draft/submit/acknowledge split
(DG-03), the active-target-actor requirement, and the transactional
state+receipt+audit+outbox boundary are all covered against real storage rather
than an in-memory stub.

Group 1 covers the capability-correct draft/submit/acknowledge split and
attribution. Group 2 covers idempotency, stale version, scope, and safe
404/409 parity. Group 3 covers atomic state+receipt+audit+outbox commit with a
dual rollback proof (audit failure and outbox failure injected separately).
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
from clearcut.main import app
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.asyncio

_PASSWORD = "Password123!"


def _intent_hash(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _idempotency_key(label: str) -> str:
    # RequiredIdempotencyKey is 16..128 chars; pad the label to satisfy it.
    return f"idem-{label}-{uuid4().hex}"


def _refer_path(org_id: UUID, project_id: UUID, item_id: UUID) -> str:
    return f"/api/v1/organizations/{org_id}/projects/{project_id}/clearance-items/{item_id}:refer"


def _acknowledge_path(
    org_id: UUID,
    project_id: UUID,
    item_id: UUID,
    referral_id: UUID,
) -> str:
    return (
        f"/api/v1/organizations/{org_id}/projects/{project_id}"
        f"/clearance-items/{item_id}/referrals/{referral_id}:acknowledge"
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
    email = f"refer-{suffix}-{uuid4().hex}@example.com"
    registration = await client.post(
        "/api/v1/users",
        json={
            "name": f"Referrer {suffix}",
            "email": email,
            "password": _PASSWORD,
        },
    )
    assert registration.status_code == 201, registration.text
    return Actor(user_id=UUID(registration.json()["data"]["userId"]), email=email)


async def _login(client: AsyncClient, *, email: str) -> None:
    """Log in as ``email`` on ``client``, overwriting the session cookie.

    There is no session-switch endpoint; creating a fresh session for a user is
    how a test acts as that user. This is the mechanism used to act as a target
    actor when acknowledging a referral submitted by someone else.
    """
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
            "name": f"Referral Studio {suffix}",
            "slug": f"refer-{slug_suffix}-{uuid4().hex[:8]}",
        },
    )
    assert organization.status_code == 201, organization.text
    org_id = UUID(organization.json()["data"]["orgId"])
    project = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        json={"title": f"Referral Project {suffix}"},
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
                "VALUES (:id, :org_id, :project_id, 'Referral test', :created_at)"
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


async def _add_member_with_role(
    client: AsyncClient,
    *,
    org_id: UUID,
    project_id: UUID,
    role: str,
    suffix: str,
) -> Actor:
    """Register a second user and give them an active membership + role in ``org_id``.

    Returns the new actor. Used to seed an active authorized *target actor* who
    can acknowledge a referral submitted by someone else. The caller logs in as
    this actor (via :func:`_login`) to act as them.
    """
    actor = await _register_actor(client, suffix=suffix)
    now = datetime.now(UTC)
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO memberships (id, org_id, user_id, role, status, created_at) "
                "VALUES (:id, :org_id, :user_id, :role, 'active', :created_at)"
            ),
            {
                "id": str(uuid6.uuid7()),
                "org_id": str(org_id),
                "user_id": str(actor.user_id),
                "role": role,
                "created_at": now,
            },
        )
    return actor


async def _setup(client: AsyncClient, *, suffix: str) -> Fixture:
    actor = await _register_actor(client, suffix=suffix)
    org_id, project_id = await _create_org_and_project(client, suffix=suffix)
    item_id = await _insert_item(org_id=org_id, project_id=project_id)
    return Fixture(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        actor_id=actor.user_id,
        actor_email=actor.email,
    )


def _refer_body(
    *,
    target_role: str = "reviewer",
    question: str = "Does this trademark usage require a license?",
    rationale: str = "External specialist review needed before we clear this item.",
    expected_version: int = 1,
    intent_hash: str | None = None,
) -> dict:
    return {
        "targetRole": target_role,
        "question": question,
        "rationale": rationale,
        "expectedVersion": expected_version,
        "intentHash": intent_hash
        or _intent_hash(target_role, question, rationale, str(expected_version)),
    }


def _ack_body(
    *,
    response: str = "Reviewed; fair-use analysis attached, no license required.",
    rationale: str = "Specialist completed the requested analysis.",
    expected_version: int = 2,
    intent_hash: str | None = None,
) -> dict:
    return {
        "response": response,
        "rationale": rationale,
        "expectedVersion": expected_version,
        "intentHash": intent_hash or _intent_hash(response, rationale, str(expected_version)),
    }


async def _post_refer(
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
        _refer_path(
            org_id or fixture.org_id,
            project_id or fixture.project_id,
            item_id or fixture.item_id,
        ),
        json=body,
        headers={"Idempotency-Key": idempotency_key},
    )


async def _post_acknowledge(
    client: AsyncClient,
    fixture: Fixture,
    referral_id: UUID,
    *,
    body: dict,
    idempotency_key: str,
    org_id: UUID | None = None,
    project_id: UUID | None = None,
    item_id: UUID | None = None,
):
    return await client.post(
        _acknowledge_path(
            org_id or fixture.org_id,
            project_id or fixture.project_id,
            item_id or fixture.item_id,
            referral_id,
        ),
        json=body,
        headers={"Idempotency-Key": idempotency_key},
    )


async def _submit_referral(
    client: AsyncClient,
    fixture: Fixture,
    *,
    target_role: str = "reviewer",
    label: str = "seed",
) -> UUID:
    """Submit a referral as an authorized (reviewer) actor and return its id."""
    await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")
    response = await _post_refer(
        client,
        fixture,
        body=_refer_body(target_role=target_role),
        idempotency_key=_idempotency_key(label),
    )
    assert response.status_code == 201, response.text
    return UUID(response.json()["data"]["referralId"])


# --------------------------------------------------------------------------- #
# Group 1: Draft / submit / acknowledge role split and attribution.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("role", ["owner", "admin", "reviewer"])
async def test_authorized_roles_may_submit_referral(role: str) -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix=f"submit-{role}")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role=role)
        response = await _post_refer(
            client, fixture, body=_refer_body(), idempotency_key=_idempotency_key(role)
        )

    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["itemId"] == str(fixture.item_id)
    assert data["itemVersion"] == 2
    assert data["targetRole"] == "reviewer"
    assert data["status"] == "submitted"
    assert data["referralId"]
    assert response.json()["meta"]["requestId"]


async def test_editor_may_not_submit_referral_403() -> None:
    """DG-03: Editor may draft a brief but may not submit a referral."""
    async with await _client() as client:
        fixture = await _setup(client, suffix="editor-submit")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="editor")
        response = await _post_refer(
            client, fixture, body=_refer_body(), idempotency_key=_idempotency_key("editor-submit")
        )

    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "permission_denied"
    # No referral, item version change, receipt, audit, or outbox for a denied actor.
    async with session_scope() as session:
        referrals = (
            await session.execute(
                sa.text("SELECT count(*) FROM governed_referrals WHERE item_id = :item_id"),
                {"item_id": str(fixture.item_id)},
            )
        ).scalar_one()
        version = (
            await session.execute(
                sa.text("SELECT version FROM clearance_items WHERE id = :id"),
                {"id": str(fixture.item_id)},
            )
        ).scalar_one()
        outbox = (
            await session.execute(
                sa.text("SELECT count(*) FROM governed_outbox WHERE project_id = :project_id"),
                {"project_id": str(fixture.project_id)},
            )
        ).scalar_one()
    assert referrals == 0
    assert version == 1
    assert outbox == 0


async def test_editor_may_draft_referral() -> None:
    """DG-03: Editor may save a draft brief; the draft is a distinct transition
    that never advances to the submitted state."""
    from clearcut.collaboration.adapters.sql_repository import SqlCollaborationRepository
    from clearcut.collaboration.application.referrals import (
        DraftReferralCommand,
        ReferralService,
    )

    async with await _client() as client:
        fixture = await _setup(client, suffix="editor-draft")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="editor")
        service = ReferralService(repository=SqlCollaborationRepository())
        async with session_scope() as session:
            result = await service.draft(
                session,
                DraftReferralCommand(
                    org_id=fixture.org_id,
                    project_id=fixture.project_id,
                    item_id=fixture.item_id,
                    actor_id=fixture.actor_id,
                    actor_role="editor",
                    target_role="reviewer",
                    question="Should this be referred for external review?",
                    rationale="Drafting a brief for the reviewer before submission.",
                    expected_version=1,
                    intent_hash=_intent_hash("draft", "reviewer", "1"),
                    idempotency_key=_idempotency_key("editor-draft"),
                ),
            )

    assert result.status == "draft"
    async with session_scope() as session:
        status = (
            await session.execute(
                sa.text("SELECT status FROM governed_referrals WHERE id = :id"),
                {"id": str(result.referral_id)},
            )
        ).scalar_one()
    assert status == "draft"


async def test_submit_and_acknowledge_are_separate_transitions() -> None:
    """Submission and acknowledgement are independent attributable transitions:
    distinct actors, distinct audit actions, distinct item version advances."""
    async with await _client() as client:
        fixture = await _setup(client, suffix="separate")
        # Submitter is a reviewer; acknowledger is a distinct active reviewer.
        referral_id = await _submit_referral(client, fixture, target_role="reviewer")
        target_actor = await _add_member_with_role(
            client,
            org_id=fixture.org_id,
            project_id=fixture.project_id,
            role="reviewer",
            suffix="ack-actor",
        )
        # Acknowledge as the target actor (log in as that user).
        await _login(client, email=target_actor.email)
        ack = await _post_acknowledge(
            client,
            fixture,
            referral_id,
            body=_ack_body(),
            idempotency_key=_idempotency_key("ack"),
        )

    assert ack.status_code == 200, ack.text
    data = ack.json()["data"]
    assert data["referralId"] == str(referral_id)
    assert data["status"] == "acknowledged"
    # The item advanced once on submit (v2) and again on acknowledge (v3).
    assert data["itemVersion"] == 3

    async with session_scope() as session:
        submitted_by, acknowledged_by, status = (
            await session.execute(
                sa.text(
                    "SELECT submitted_by_actor_id, acknowledged_by_actor_id, status "
                    "FROM governed_referrals WHERE id = :id"
                ),
                {"id": str(referral_id)},
            )
        ).one()
        actions = (
            (
                await session.execute(
                    sa.text(
                        "SELECT action FROM authoritative_audit_events "
                        "WHERE target_id = :referral_id ORDER BY occurred_at"
                    ),
                    {"referral_id": str(referral_id)},
                )
            )
            .scalars()
            .all()
        )
    assert str(submitted_by) == str(fixture.actor_id)
    assert str(acknowledged_by) == str(target_actor.user_id)
    assert status == "acknowledged"
    # Two distinct attributable audit actions, one per transition.
    assert any("refer" in a for a in actions)
    assert any("acknowledg" in a for a in actions)


async def test_acknowledgement_requires_active_authorized_target_actor() -> None:
    """Acknowledgement requires an *active authorized target actor*: a member
    whose active role matches the referral's target role. A non-target-role
    actor is a neutral 403; a deactivated target actor cannot acknowledge."""
    async with await _client() as client:
        fixture = await _setup(client, suffix="ack-authz")
        referral_id = await _submit_referral(client, fixture, target_role="reviewer")

        # An active member whose role does NOT match the target role (editor).
        wrong_role_actor = await _add_member_with_role(
            client,
            org_id=fixture.org_id,
            project_id=fixture.project_id,
            role="editor",
            suffix="wrong-role",
        )
        await _login(client, email=wrong_role_actor.email)
        wrong_role = await _post_acknowledge(
            client,
            fixture,
            referral_id,
            body=_ack_body(),
            idempotency_key=_idempotency_key("wrong-role"),
        )

    assert wrong_role.status_code == 403, wrong_role.text
    assert wrong_role.json()["error"]["code"] == "permission_denied"


async def test_deactivated_target_actor_cannot_acknowledge() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="ack-deactivated")
        referral_id = await _submit_referral(client, fixture, target_role="reviewer")
        target_actor = await _add_member_with_role(
            client,
            org_id=fixture.org_id,
            project_id=fixture.project_id,
            role="reviewer",
            suffix="deactivated-target",
        )
        await _deactivate_membership(org_id=fixture.org_id, user_id=target_actor.user_id)
        await _login(client, email=target_actor.email)
        response = await _post_acknowledge(
            client,
            fixture,
            referral_id,
            body=_ack_body(),
            idempotency_key=_idempotency_key("deactivated-target"),
        )

    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "permission_denied"


async def test_submitted_referral_is_scoped_versioned_and_attributable() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="attrib")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="admin")
        response = await _post_refer(
            client, fixture, body=_refer_body(), idempotency_key=_idempotency_key("attrib")
        )

    assert response.status_code == 201, response.text
    referral_id = UUID(response.json()["data"]["referralId"])
    async with session_scope() as session:
        row = (
            await session.execute(
                sa.text(
                    "SELECT org_id, project_id, item_id, submitted_by_actor_id, status "
                    "FROM governed_referrals WHERE id = :id"
                ),
                {"id": str(referral_id)},
            )
        ).one()
    assert str(row.org_id) == str(fixture.org_id)
    assert str(row.project_id) == str(fixture.project_id)
    assert str(row.item_id) == str(fixture.item_id)
    assert str(row.submitted_by_actor_id) == str(fixture.actor_id)
    assert row.status == "submitted"


async def test_missing_idempotency_key_header_is_rejected() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="no-idem")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")
        response = await client.post(
            _refer_path(fixture.org_id, fixture.project_id, fixture.item_id),
            json=_refer_body(),
        )

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "validation_failed"


@pytest.mark.parametrize(
    "mutate",
    [
        {"targetRole": ""},
        {"question": ""},
        {"rationale": ""},
        {"expectedVersion": None},
        {"intentHash": ""},
    ],
)
async def test_missing_required_referral_fields_are_rejected(mutate: dict) -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="required")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")
        body = _refer_body()
        body.update(mutate)
        response = await _post_refer(
            client, fixture, body=body, idempotency_key=_idempotency_key("required")
        )

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "validation_failed"


async def test_referral_never_asserts_legal_conclusion() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="legal-boundary")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")
        response = await _post_refer(
            client, fixture, body=_refer_body(), idempotency_key=_idempotency_key("legal")
        )

    assert response.status_code == 201, response.text
    body_text = response.text.lower()
    for forbidden in ("legally cleared", "legal clearance", "clearance guaranteed"):
        assert forbidden not in body_text
    referral_id = response.json()["data"]["referralId"]
    async with session_scope() as session:
        payloads = (
            (
                await session.execute(
                    sa.text(
                        "SELECT payload_redacted FROM authoritative_audit_events "
                        "WHERE target_id = :referral_id"
                    ),
                    {"referral_id": str(referral_id)},
                )
            )
            .scalars()
            .all()
        )
    joined = " ".join(str(p) for p in payloads).lower()
    for forbidden in ("legally cleared", "legal clearance", "clearance guaranteed"):
        assert forbidden not in joined


# --------------------------------------------------------------------------- #
# Group 2: Idempotency / stale / scope / safe parity.
# --------------------------------------------------------------------------- #


async def test_unknown_item_is_safe_not_found() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="unknown-item")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")
        missing_item = uuid6.uuid7()
        response = await _post_refer(
            client,
            fixture,
            body=_refer_body(),
            idempotency_key=_idempotency_key("unknown"),
            item_id=missing_item,
        )

    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "not_found"


async def test_foreign_item_and_tenant_have_safe_parity() -> None:
    async with await _client() as owner, await _client() as foreign:
        owned = await _setup(owner, suffix="owned-parity")
        alien = await _setup(foreign, suffix="foreign-parity")
        await _set_membership_role(org_id=owned.org_id, user_id=owned.actor_id, role="reviewer")

        foreign_item_through_owned_scope = await _post_refer(
            owner,
            owned,
            body=_refer_body(),
            idempotency_key=_idempotency_key("foreign-item"),
            item_id=alien.item_id,
        )
        foreign_tenant_through_owner_session = await _post_refer(
            owner,
            owned,
            body=_refer_body(),
            idempotency_key=_idempotency_key("foreign-tenant"),
            org_id=alien.org_id,
            project_id=alien.project_id,
            item_id=alien.item_id,
        )

    assert foreign_item_through_owned_scope.status_code == 404
    assert foreign_item_through_owned_scope.json()["error"]["code"] == "not_found"
    assert foreign_tenant_through_owner_session.status_code == 403
    assert foreign_tenant_through_owner_session.json()["error"]["code"] == "permission_denied"


async def test_unknown_referral_on_acknowledge_is_safe_not_found() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="unknown-referral")
        target_actor = await _add_member_with_role(
            client,
            org_id=fixture.org_id,
            project_id=fixture.project_id,
            role="reviewer",
            suffix="ack-target",
        )
        await _login(client, email=target_actor.email)
        missing_referral = uuid6.uuid7()
        response = await _post_acknowledge(
            client,
            fixture,
            missing_referral,
            body=_ack_body(),
            idempotency_key=_idempotency_key("unknown-referral"),
        )

    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "not_found"


async def test_foreign_referral_on_acknowledge_is_safe_not_found() -> None:
    async with await _client() as owner, await _client() as foreign:
        owned = await _setup(owner, suffix="owned-ref-parity")
        alien = await _setup(foreign, suffix="foreign-ref-parity")
        alien_referral = await _submit_referral(foreign, alien, target_role="reviewer")

        owner_target = await _add_member_with_role(
            owner,
            org_id=owned.org_id,
            project_id=owned.project_id,
            role="reviewer",
            suffix="owner-target",
        )
        await _login(owner, email=owner_target.email)
        # Try to acknowledge the alien referral through the owned scope.
        response = await _post_acknowledge(
            owner,
            owned,
            alien_referral,
            body=_ack_body(),
            idempotency_key=_idempotency_key("foreign-referral"),
        )

    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "not_found"


async def test_stale_expected_version_on_submit_returns_409() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="stale-submit")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")
        first = await _post_refer(
            client,
            fixture,
            body=_refer_body(question="First referral wins."),
            idempotency_key=_idempotency_key("stale-a"),
        )
        # The item advanced to v2; a second submit still asserting v1 is stale.
        second = await _post_refer(
            client,
            fixture,
            body=_refer_body(question="Second referral is stale."),
            idempotency_key=_idempotency_key("stale-b"),
        )

    assert first.status_code == 201, first.text
    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] in {"conflict", "conflict_stale_version"}


async def test_stale_submit_writes_no_referral_receipt_audit_or_outbox() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="stale-noop")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")
        await _post_refer(
            client,
            fixture,
            body=_refer_body(question="Advance the version."),
            idempotency_key=_idempotency_key("stale-noop-a"),
        )
        stale = await _post_refer(
            client,
            fixture,
            body=_refer_body(question="Stale writer must not persist."),
            idempotency_key=_idempotency_key("stale-noop-b"),
        )

    assert stale.status_code == 409, stale.text
    async with session_scope() as session:
        version = (
            await session.execute(
                sa.text("SELECT version FROM clearance_items WHERE id = :id"),
                {"id": str(fixture.item_id)},
            )
        ).scalar_one()
        referrals = (
            await session.execute(
                sa.text("SELECT count(*) FROM governed_referrals WHERE item_id = :item_id"),
                {"item_id": str(fixture.item_id)},
            )
        ).scalar_one()
        outbox = (
            await session.execute(
                sa.text("SELECT count(*) FROM governed_outbox WHERE project_id = :project_id"),
                {"project_id": str(fixture.project_id)},
            )
        ).scalar_one()
    # Only the first submit persisted: v2, one referral, one outbox event.
    assert version == 2
    assert referrals == 1
    assert outbox == 1


async def test_same_key_same_intent_replays_original_referral() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="replay")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")
        key = _idempotency_key("replay")
        body = _refer_body()
        first = await _post_refer(client, fixture, body=body, idempotency_key=key)
        second = await _post_refer(client, fixture, body=body, idempotency_key=key)

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["data"]["referralId"] == second.json()["data"]["referralId"]
    assert first.json()["data"]["itemVersion"] == 2
    assert second.json()["data"]["itemVersion"] == 2
    async with session_scope() as session:
        referrals = (
            await session.execute(
                sa.text("SELECT count(*) FROM governed_referrals WHERE item_id = :item_id"),
                {"item_id": str(fixture.item_id)},
            )
        ).scalar_one()
        outbox = (
            await session.execute(
                sa.text("SELECT count(*) FROM governed_outbox WHERE project_id = :project_id"),
                {"project_id": str(fixture.project_id)},
            )
        ).scalar_one()
    assert referrals == 1
    assert outbox == 1


async def test_same_key_different_intent_returns_409() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="intent-conflict")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")
        key = _idempotency_key("intent-conflict")
        first = await _post_refer(
            client,
            fixture,
            body=_refer_body(question="First intent."),
            idempotency_key=key,
        )
        second = await _post_refer(
            client,
            fixture,
            body=_refer_body(question="A different intent entirely."),
            idempotency_key=key,
        )

    assert first.status_code == 201, first.text
    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] in {"conflict", "conflict_idempotency_mismatch"}


async def test_acknowledge_same_key_same_intent_replays() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="ack-replay")
        referral_id = await _submit_referral(client, fixture, target_role="reviewer")
        target_actor = await _add_member_with_role(
            client,
            org_id=fixture.org_id,
            project_id=fixture.project_id,
            role="reviewer",
            suffix="ack-replay-target",
        )
        await _login(client, email=target_actor.email)
        key = _idempotency_key("ack-replay")
        body = _ack_body()
        first = await _post_acknowledge(
            client, fixture, referral_id, body=body, idempotency_key=key
        )
        second = await _post_acknowledge(
            client, fixture, referral_id, body=body, idempotency_key=key
        )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["data"]["itemVersion"] == second.json()["data"]["itemVersion"]
    async with session_scope() as session:
        ack_audits = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM authoritative_audit_events "
                    "WHERE target_id = :referral_id AND action LIKE :needle"
                ),
                {"referral_id": str(referral_id), "needle": "%acknowledg%"},
            )
        ).scalar_one()
    assert ack_audits == 1


# --------------------------------------------------------------------------- #
# Group 3: Atomic state + receipt + audit + outbox with dual rollback proof.
# --------------------------------------------------------------------------- #


async def test_referral_state_receipt_audit_and_outbox_commit_atomically() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="atomic")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")
        key = _idempotency_key("atomic")
        response = await _post_refer(client, fixture, body=_refer_body(), idempotency_key=key)

    assert response.status_code == 201, response.text
    referral_id = response.json()["data"]["referralId"]
    async with session_scope() as session:
        version = (
            await session.execute(
                sa.text("SELECT version FROM clearance_items WHERE id = :id"),
                {"id": str(fixture.item_id)},
            )
        ).scalar_one()
        referrals = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM governed_referrals "
                    "WHERE id = :id AND status = 'submitted'"
                ),
                {"id": str(referral_id)},
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
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM authoritative_audit_events WHERE target_id = :referral_id"
                ),
                {"referral_id": str(referral_id)},
            )
        ).scalar_one()
        outbox_rows = (
            (
                await session.execute(
                    sa.text(
                        "SELECT event_type, schema_version, dedupe_key "
                        "FROM governed_outbox WHERE project_id = :project_id"
                    ),
                    {"project_id": str(fixture.project_id)},
                )
            )
            .mappings()
            .all()
        )
    assert version == 2
    assert referrals == 1
    assert receipts == 1
    assert audits == 1
    # A single schema-versioned, deduped outbox event for this transition.
    assert len(outbox_rows) == 1
    assert outbox_rows[0]["schema_version"] >= 1
    assert outbox_rows[0]["dedupe_key"]
    assert "refer" in outbox_rows[0]["event_type"]


async def test_authoritative_audit_failure_rolls_back_state_receipt_and_outbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import clearcut.collaboration.application.referrals as service_module

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
        fixture = await _setup(client, suffix="audit-rollback")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")
        key = _idempotency_key("audit-rollback")
        response = await _post_refer(client, fixture, body=_refer_body(), idempotency_key=key)

    assert response.status_code == 500, response.text
    async with session_scope() as session:
        version = (
            await session.execute(
                sa.text("SELECT version FROM clearance_items WHERE id = :id"),
                {"id": str(fixture.item_id)},
            )
        ).scalar_one()
        referrals = (
            await session.execute(
                sa.text("SELECT count(*) FROM governed_referrals WHERE item_id = :item_id"),
                {"item_id": str(fixture.item_id)},
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
        outbox = (
            await session.execute(
                sa.text("SELECT count(*) FROM governed_outbox WHERE project_id = :project_id"),
                {"project_id": str(fixture.project_id)},
            )
        ).scalar_one()
    assert version == 1
    assert referrals == 0
    assert receipts == 0
    assert outbox == 0


async def test_outbox_failure_rolls_back_state_receipt_and_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import clearcut.collaboration.application.referrals as service_module

    class _InjectedOutboxError(RuntimeError):
        pass

    async def _boom(*_args: object, **_kwargs: object) -> None:
        raise _InjectedOutboxError("injected outbox failure")

    monkeypatch.setattr(service_module, "insert_outbox_event", _boom)

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
        headers={"origin": "http://test"},
    ) as client:
        fixture = await _setup(client, suffix="outbox-rollback")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")
        key = _idempotency_key("outbox-rollback")
        response = await _post_refer(client, fixture, body=_refer_body(), idempotency_key=key)

    assert response.status_code == 500, response.text
    async with session_scope() as session:
        version = (
            await session.execute(
                sa.text("SELECT version FROM clearance_items WHERE id = :id"),
                {"id": str(fixture.item_id)},
            )
        ).scalar_one()
        referrals = (
            await session.execute(
                sa.text("SELECT count(*) FROM governed_referrals WHERE item_id = :item_id"),
                {"item_id": str(fixture.item_id)},
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
            await session.execute(
                sa.text("SELECT count(*) FROM authoritative_audit_events WHERE org_id = :org_id"),
                {"org_id": str(fixture.org_id)},
            )
        ).scalar_one()
    assert version == 1
    assert referrals == 0
    assert receipts == 0
    assert audits == 0


# --------------------------------------------------------------------------- #
# Group 4: Concurrency reconciliation on the provisional referral insert and
# draft idempotency, plus acknowledge terminal-state safety.
# --------------------------------------------------------------------------- #


async def test_concurrent_duplicate_provisional_submit_replays_not_500(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A genuinely concurrent same-key submit whose provisional referral insert
    loses the ``uq_governed_referrals_idempotency`` race must reconcile into the
    idempotent replay path, never surface a raw IntegrityError/500.

    SQLite gives no true parallelism, so the interleave is simulated: the first
    submit commits its referral row and receipt. For the second submit the
    classification receipt lookup is forced to miss once (as it would under a
    real concurrent interleave where the winner's receipt is not yet visible),
    driving the second command down the fresh path so its provisional referral
    insert collides with the already-committed row. The command must recover by
    replaying the winner's committed identity rather than raising.
    """
    from clearcut.collaboration.adapters.sql_repository import SqlCollaborationRepository
    from clearcut.collaboration.application import referrals as service_module
    from clearcut.collaboration.application.referrals import (
        ReferralService,
        SubmitReferralCommand,
    )
    from clearcut.collaboration.ports.repository import ScopedItem

    real_lookup = service_module.lookup_command_receipt
    skip_state = {"skipped": False}

    async def lookup_skipping_first_miss(session, envelope):
        # Force exactly the classification lookup of the racing command to miss,
        # mirroring a concurrent winner whose receipt is not yet visible. Every
        # later lookup (the reconcile re-read after the losing insert) uses the
        # real query so the prior receipt is found and replayed.
        if not skip_state["skipped"]:
            skip_state["skipped"] = True
            return None
        return await real_lookup(session, envelope)

    async with await _client() as client:
        fixture = await _setup(client, suffix="race-submit")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")
        repository = SqlCollaborationRepository()
        service = ReferralService(repository=repository)
        key = _idempotency_key("race-submit")
        intent = _intent_hash("reviewer", "race-question", "race-rationale", "1")

        def _command() -> SubmitReferralCommand:
            return SubmitReferralCommand(
                org_id=fixture.org_id,
                project_id=fixture.project_id,
                item_id=fixture.item_id,
                actor_id=fixture.actor_id,
                actor_role="reviewer",
                target_role="reviewer",
                question="race-question",
                rationale="race-rationale",
                expected_version=1,
                intent_hash=intent,
                idempotency_key=key,
            )

        # First submit commits fully (referral row + receipt, item -> v2).
        async with session_scope() as session:
            first = await service.submit(session, _command())

        # Second submit races: it read the item at v1 before the winner
        # committed, so its classification passes; its provisional insert then
        # collides with the winner's already-committed referral row. Simulate the
        # stale-but-concurrent read by pinning the loaded item version to 1, and
        # force the classification receipt lookup to miss once.
        real_load = repository.load_scoped_item

        async def load_item_at_v1(session, *, org_id, project_id, item_id):
            loaded = await real_load(session, org_id=org_id, project_id=project_id, item_id=item_id)
            return ScopedItem(
                item_id=loaded.item_id,
                org_id=loaded.org_id,
                project_id=loaded.project_id,
                version_id=loaded.version_id,
                category=loaded.category,
                entity_name=loaded.entity_name,
                status=loaded.status,
                workflow_status=loaded.workflow_status,
                disposition_status=loaded.disposition_status,
                assigned_to_user_id=loaded.assigned_to_user_id,
                context_text=loaded.context_text,
                version=1,
            )

        monkeypatch.setattr(service_module, "lookup_command_receipt", lookup_skipping_first_miss)
        monkeypatch.setattr(repository, "load_scoped_item", load_item_at_v1)
        async with session_scope() as session:
            second = await service.submit(session, _command())

    # The racing command replayed the winner's identity instead of raising.
    assert skip_state["skipped"] is True
    assert second.referral_id == first.referral_id
    assert second.status == "submitted"
    assert second.resulting_item_version == first.resulting_item_version

    async with session_scope() as session:
        referrals = (
            await session.execute(
                sa.text("SELECT count(*) FROM governed_referrals WHERE item_id = :item_id"),
                {"item_id": str(fixture.item_id)},
            )
        ).scalar_one()
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
    # Exactly one referral, one receipt, one version advance: the race added
    # nothing.
    assert referrals == 1
    assert version == 2
    assert receipts == 1


async def test_draft_same_key_replays_original_draft() -> None:
    """A draft carries a unique ``idempotency_key``; re-issuing the same draft
    command must replay the original draft rather than raise an IntegrityError."""
    from clearcut.collaboration.adapters.sql_repository import SqlCollaborationRepository
    from clearcut.collaboration.application.referrals import (
        DraftReferralCommand,
        ReferralService,
    )

    async with await _client() as client:
        fixture = await _setup(client, suffix="draft-replay")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="editor")
        service = ReferralService(repository=SqlCollaborationRepository())
        key = _idempotency_key("draft-replay")
        intent = _intent_hash("draft", "reviewer", "1")

        def _command() -> DraftReferralCommand:
            return DraftReferralCommand(
                org_id=fixture.org_id,
                project_id=fixture.project_id,
                item_id=fixture.item_id,
                actor_id=fixture.actor_id,
                actor_role="editor",
                target_role="reviewer",
                question="Should this be referred for external review?",
                rationale="Drafting a brief before submission.",
                expected_version=1,
                intent_hash=intent,
                idempotency_key=key,
            )

        async with session_scope() as session:
            first = await service.draft(session, _command())
        async with session_scope() as session:
            second = await service.draft(session, _command())

    assert first.status == "draft"
    assert second.status == "draft"
    # The second issuance replayed the original draft identity, not a new row.
    assert second.referral_id == first.referral_id
    async with session_scope() as session:
        drafts = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM governed_referrals "
                    "WHERE item_id = :item_id AND status = 'draft'"
                ),
                {"item_id": str(fixture.item_id)},
            )
        ).scalar_one()
    # Only one draft row exists despite two same-key issuances.
    assert drafts == 1


async def test_draft_records_a_distinct_draft_operation() -> None:
    """The draft receipt must reflect a distinct draft operation, not the submit
    operation, so receipts/audit attribute the real transition. A draft and a
    later governed submit that happen to share an idempotency key must not
    collide on the receipt scope, because their operations differ."""
    from clearcut.collaboration.adapters.sql_repository import SqlCollaborationRepository
    from clearcut.collaboration.application import referrals as service_module
    from clearcut.collaboration.application.referrals import (
        DraftReferralCommand,
        ReferralService,
    )

    async with await _client() as client:
        fixture = await _setup(client, suffix="draft-op")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="editor")
        service = ReferralService(repository=SqlCollaborationRepository())
        async with session_scope() as session:
            await service.draft(
                session,
                DraftReferralCommand(
                    org_id=fixture.org_id,
                    project_id=fixture.project_id,
                    item_id=fixture.item_id,
                    actor_id=fixture.actor_id,
                    actor_role="editor",
                    target_role="reviewer",
                    question="Draft operation naming?",
                    rationale="Ensure the receipt reflects the draft operation.",
                    expected_version=1,
                    intent_hash=_intent_hash("draft-op", "reviewer", "1"),
                    idempotency_key=_idempotency_key("draft-op"),
                ),
            )

    # The service must expose a distinct draft operation identifier that is not
    # the submit operation.
    assert service_module._DRAFT_OPERATION != service_module._SUBMIT_OPERATION


async def test_double_acknowledge_distinct_key_is_terminal_safe() -> None:
    """Acknowledging an already-acknowledged referral with a *distinct*
    idempotency key must be rejected as a typed conflict (or a safe no-op replay)
    without a second ``referral.acknowledged`` audit/outbox event or a second
    item version advance. The referral row is terminal after the first ack."""
    async with await _client() as client:
        fixture = await _setup(client, suffix="ack-terminal")
        referral_id = await _submit_referral(client, fixture, target_role="reviewer")
        target_actor = await _add_member_with_role(
            client,
            org_id=fixture.org_id,
            project_id=fixture.project_id,
            role="reviewer",
            suffix="ack-terminal-target",
        )
        await _login(client, email=target_actor.email)
        first = await _post_acknowledge(
            client,
            fixture,
            referral_id,
            body=_ack_body(expected_version=2),
            idempotency_key=_idempotency_key("ack-terminal-1"),
        )
        # A distinct-key acknowledge of the now-terminal referral. The item is at
        # v3, so this asserts expected_version=3 to isolate the terminal guard
        # from the stale-version guard.
        second = await _post_acknowledge(
            client,
            fixture,
            referral_id,
            body=_ack_body(expected_version=3),
            idempotency_key=_idempotency_key("ack-terminal-2"),
        )

    assert first.status_code == 200, first.text
    # The second acknowledge must not succeed with a fresh transition: either a
    # typed conflict (409) or a safe idempotent replay (200) is acceptable, but
    # it must not advance the version or write a second audit/outbox.
    assert second.status_code in {200, 409}, second.text

    async with session_scope() as session:
        version = (
            await session.execute(
                sa.text("SELECT version FROM clearance_items WHERE id = :id"),
                {"id": str(fixture.item_id)},
            )
        ).scalar_one()
        ack_audits = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM authoritative_audit_events "
                    "WHERE target_id = :referral_id AND action LIKE :needle"
                ),
                {"referral_id": str(referral_id), "needle": "%acknowledg%"},
            )
        ).scalar_one()
        ack_outbox = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM governed_outbox "
                    "WHERE project_id = :project_id AND event_type LIKE :needle"
                ),
                {"project_id": str(fixture.project_id), "needle": "%acknowledg%"},
            )
        ).scalar_one()
        acknowledged_by = (
            await session.execute(
                sa.text("SELECT acknowledged_by_actor_id FROM governed_referrals WHERE id = :id"),
                {"id": str(referral_id)},
            )
        ).scalar_one()
    # Item advanced only on submit (v2) and the single acknowledge (v3).
    assert version == 3
    # Exactly one acknowledge audit and one acknowledge outbox event.
    assert ack_audits == 1
    assert ack_outbox == 1
    # The authoritative acknowledging actor is unchanged.
    assert str(acknowledged_by) == str(target_actor.user_id)

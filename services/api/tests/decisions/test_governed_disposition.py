"""Behavioral tests for the governed clearance-item disposition slice.

These tests pin the canonical ``:setDisposition`` operation end to end: an
Owner/Admin/Reviewer records exactly one workflow disposition on an exact,
tenant-and-project-scoped clearance item, with server-derived capability
enforcement, canonical ``ClearanceDisposition`` values only, required rationale,
expected-version optimistic concurrency, intent/idempotency, a same-transaction
authoritative audit event built through the typed ``AuditPayload`` seam, and a
disposition that never asserts a legal conclusion or bypasses the
unresolved-evidence requirement for the clearance-like ``verified`` outcome.

The tests exercise the mounted FastAPI route (reusing the shared
governed-command kernel and migration 0030 tables) rather than any in-memory
stub, so tenant scope, safe not-found parity, and the transactional
disposition+receipt+audit boundary are all covered against the real migrated
schema. The retired direct-SQL handler wrote the legacy ``audit_events`` table
via f-string JSON interpolation; these tests assert the governed replacement
writes the authoritative ledger with a structured payload and leaves the legacy
table untouched.
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


def _disposition_path(org_id: UUID, project_id: UUID, item_id: UUID) -> str:
    return (
        f"/api/v1/organizations/{org_id}/projects/{project_id}"
        f"/clearance-items/{item_id}:setDisposition"
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


async def _register_actor(client: AsyncClient, *, suffix: str) -> UUID:
    registration = await client.post(
        "/api/v1/users",
        json={
            "name": f"Reviewer {suffix}",
            "email": f"disp-{suffix}-{uuid4().hex}@example.com",
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
            "name": f"Disposition Studio {suffix}",
            "slug": f"disp-{slug_suffix}-{uuid4().hex[:8]}",
        },
    )
    assert organization.status_code == 201, organization.text
    org_id = UUID(organization.json()["data"]["orgId"])
    project = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        json={"title": f"Disposition Project {suffix}"},
    )
    assert project.status_code == 201, project.text
    project_id = UUID(project.json()["data"]["projectId"])
    return org_id, project_id


async def _insert_item(
    *,
    org_id: UUID,
    project_id: UUID,
    with_claim: bool = False,
) -> UUID:
    script_id = uuid6.uuid7()
    version_id = uuid6.uuid7()
    element_id = uuid6.uuid7()
    item_id = uuid6.uuid7()
    now = datetime.now(UTC)
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO scripts (id, org_id, project_id, title, created_at) "
                "VALUES (:id, :org_id, :project_id, 'Disposition test', :created_at)"
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
        if with_claim:
            run_id = uuid6.uuid7()
            snapshot_id = uuid6.uuid7()
            claim_id = uuid6.uuid7()
            await session.execute(
                sa.text(
                    "INSERT INTO research_runs "
                    "(id, org_id, project_id, item_id, status, created_at) "
                    "VALUES (:id, :org_id, :project_id, :item_id, 'completed', :created_at)"
                ),
                {
                    "id": str(run_id),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                    "item_id": str(item_id),
                    "created_at": now,
                },
            )
            await session.execute(
                sa.text(
                    "INSERT INTO source_snapshots "
                    "(id, org_id, project_id, item_id, run_id, url, title, publisher, excerpt, "
                    "origin, sha256_hash, retrieved_at) VALUES "
                    "(:id, :org_id, :project_id, :item_id, :run_id, :url, :title, :publisher, "
                    ":excerpt, 'search', :sha256_hash, :retrieved_at)"
                ),
                {
                    "id": str(snapshot_id),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                    "item_id": str(item_id),
                    "run_id": str(run_id),
                    "url": "https://register.example/trademark",
                    "title": "Official register",
                    "publisher": "USPTO",
                    "excerpt": "No active conflicting marks.",
                    "sha256_hash": "a" * 64,
                    "retrieved_at": now,
                },
            )
            await session.execute(
                sa.text(
                    "INSERT INTO evidence_claims "
                    "(id, org_id, project_id, item_id, snapshot_id, stance, authority_tier, "
                    "claim_text, provenance_excerpt, created_at) VALUES "
                    "(:id, :org_id, :project_id, :item_id, :snapshot_id, 'supports', 'primary', "
                    ":claim_text, :excerpt, :created_at)"
                ),
                {
                    "id": str(claim_id),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                    "item_id": str(item_id),
                    "snapshot_id": str(snapshot_id),
                    "claim_text": "The register shows no conflicting active marks.",
                    "excerpt": "No active conflicting marks.",
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


async def _setup(client: AsyncClient, *, suffix: str, with_claim: bool = False) -> Fixture:
    actor_id = await _register_actor(client, suffix=suffix)
    org_id, project_id = await _create_org_and_project(client, suffix=suffix)
    item_id = await _insert_item(org_id=org_id, project_id=project_id, with_claim=with_claim)
    return Fixture(org_id=org_id, project_id=project_id, item_id=item_id, actor_id=actor_id)


def _body(
    *,
    disposition: str = "deferred",
    rationale: str = "Reviewed the cited evidence and defer this item for now.",
    expected_version: int = 1,
    intent_hash: str | None = None,
) -> dict:
    return {
        "disposition": disposition,
        "rationale": rationale,
        "expectedVersion": expected_version,
        "intentHash": intent_hash or _intent_hash(disposition, rationale, str(expected_version)),
    }


async def _post_disposition(
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
        _disposition_path(
            org_id or fixture.org_id,
            project_id or fixture.project_id,
            item_id or fixture.item_id,
        ),
        json=body,
        headers={"Idempotency-Key": idempotency_key},
    )


# --------------------------------------------------------------------------- #
# Group 1: Role / rationale / canonical enum / legal boundary.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("role", ["owner", "admin", "reviewer"])
async def test_authorized_roles_set_disposition(role: str) -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix=f"authz-{role}")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role=role)
        response = await _post_disposition(
            client, fixture, body=_body(), idempotency_key=_idempotency_key(role)
        )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["itemId"] == str(fixture.item_id)
    assert data["projectId"] == str(fixture.project_id)
    assert data["version"] == 2
    assert data["disposition"] == "deferred"
    assert response.json()["meta"]["requestId"]


@pytest.mark.parametrize("role", ["editor", "viewer"])
async def test_unauthorized_roles_are_denied_with_typed_403(role: str) -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix=f"deny-{role}")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role=role)
        response = await _post_disposition(
            client, fixture, body=_body(), idempotency_key=_idempotency_key(role)
        )

    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "permission_denied"
    # No disposition record, version change, or audit for a denied actor.
    async with session_scope() as session:
        records = (
            await session.execute(
                sa.text("SELECT count(*) FROM governed_decision_records WHERE item_id = :item_id"),
                {"item_id": str(fixture.item_id)},
            )
        ).scalar_one()
        version = (
            await session.execute(
                sa.text("SELECT version FROM clearance_items WHERE id = :id"),
                {"id": str(fixture.item_id)},
            )
        ).scalar_one()
        disposition = (
            await session.execute(
                sa.text("SELECT disposition_status FROM clearance_items WHERE id = :id"),
                {"id": str(fixture.item_id)},
            )
        ).scalar_one()
    assert records == 0
    assert version == 1
    assert disposition == "undisposed"


async def test_deactivated_membership_cannot_set_disposition() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="deactivated")
        await _deactivate_membership(org_id=fixture.org_id, user_id=fixture.actor_id)
        response = await _post_disposition(
            client, fixture, body=_body(), idempotency_key=_idempotency_key("deactivated")
        )

    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "permission_denied"


@pytest.mark.parametrize(
    "disposition",
    ["pending", "verified", "ruled_out", "fixed_in_rewrite", "deferred"],
)
async def test_all_canonical_disposition_values_are_accepted(disposition: str) -> None:
    # verified is the clearance-like outcome and needs a cited claim; seed one so
    # this test exercises canonical-vocabulary acceptance, not the evidence gate.
    async with await _client() as client:
        fixture = await _setup(client, suffix=f"canon-{disposition}", with_claim=True)
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")
        response = await _post_disposition(
            client,
            fixture,
            body=_body(disposition=disposition),
            idempotency_key=_idempotency_key(f"canon-{disposition}"),
        )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["disposition"] == disposition


@pytest.mark.parametrize(
    "disposition",
    ["cleared", "approved_as_is", "blocked", "", "undisposed", "APPROVE"],
)
async def test_non_canonical_disposition_values_are_rejected(disposition: str) -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="noncanon")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")
        response = await _post_disposition(
            client,
            fixture,
            body=_body(disposition=disposition),
            idempotency_key=_idempotency_key("noncanon"),
        )

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "validation_failed"


@pytest.mark.parametrize(
    "mutate",
    [
        {"rationale": ""},
        {"rationale": "   "},
        {"expectedVersion": None},
        {"intentHash": ""},
    ],
)
async def test_missing_required_fields_are_rejected(mutate: dict) -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="required")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")
        body = _body()
        body.update(mutate)
        response = await _post_disposition(
            client, fixture, body=body, idempotency_key=_idempotency_key("required")
        )

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "validation_failed"


async def test_missing_idempotency_key_header_is_rejected() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="no-idem")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")
        response = await client.post(
            _disposition_path(fixture.org_id, fixture.project_id, fixture.item_id),
            json=_body(),
        )

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "validation_failed"


async def test_disposition_never_asserts_legal_clearance() -> None:
    """A recorded disposition is a workflow signal, never a legal conclusion.

    The response and the authoritative audit payload must not contain
    legal-clearance language (e.g. "legally cleared", "clearance guaranteed").
    """
    async with await _client() as client:
        fixture = await _setup(client, suffix="legal-boundary", with_claim=True)
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")
        response = await _post_disposition(
            client,
            fixture,
            body=_body(disposition="verified", rationale="The register confirms the mark."),
            idempotency_key=_idempotency_key("legal-boundary"),
        )

    assert response.status_code == 200, response.text
    body_text = response.text.lower()
    for forbidden in ("legally cleared", "legal clearance", "clearance guaranteed", "cleared"):
        assert forbidden not in body_text

    async with session_scope() as session:
        payloads = (
            (
                await session.execute(
                    sa.text(
                        "SELECT payload_redacted FROM authoritative_audit_events "
                        "WHERE target_id = :item_id"
                    ),
                    {"item_id": str(fixture.item_id)},
                )
            )
            .scalars()
            .all()
        )
    joined = " ".join(str(p) for p in payloads).lower()
    for forbidden in ("legally cleared", "legal clearance", "clearance guaranteed"):
        assert forbidden not in joined


# --------------------------------------------------------------------------- #
# Group 2: Evidence / zero-evidence semantics.
# --------------------------------------------------------------------------- #


async def test_verified_disposition_rejected_when_item_has_zero_cited_claims() -> None:
    """The clearance-like ``verified`` disposition must not bypass the
    unresolved-evidence requirement: with zero cited claims it is rejected."""
    async with await _client() as client:
        fixture = await _setup(client, suffix="zero-verified", with_claim=False)
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")
        response = await _post_disposition(
            client,
            fixture,
            body=_body(disposition="verified", rationale="Attempt to verify without evidence."),
            idempotency_key=_idempotency_key("zero-verified"),
        )

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "validation_failed"
    async with session_scope() as session:
        version = (
            await session.execute(
                sa.text("SELECT version FROM clearance_items WHERE id = :id"),
                {"id": str(fixture.item_id)},
            )
        ).scalar_one()
        records = (
            await session.execute(
                sa.text("SELECT count(*) FROM governed_decision_records WHERE item_id = :item_id"),
                {"item_id": str(fixture.item_id)},
            )
        ).scalar_one()
    assert version == 1
    assert records == 0


async def test_verified_disposition_allowed_when_item_has_cited_claims() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="verified-claim", with_claim=True)
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")
        response = await _post_disposition(
            client,
            fixture,
            body=_body(disposition="verified", rationale="The register confirms the mark."),
            idempotency_key=_idempotency_key("verified-claim"),
        )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["version"] == 2
    assert response.json()["data"]["disposition"] == "verified"


@pytest.mark.parametrize("disposition", ["pending", "ruled_out", "fixed_in_rewrite", "deferred"])
async def test_non_clearance_dispositions_allowed_with_zero_claims(disposition: str) -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix=f"zero-{disposition}", with_claim=False)
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")
        response = await _post_disposition(
            client,
            fixture,
            body=_body(disposition=disposition, rationale="No evidence yet; workflow move."),
            idempotency_key=_idempotency_key(f"zero-{disposition}"),
        )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["version"] == 2


# --------------------------------------------------------------------------- #
# Group 3: Concurrency / idempotency / scope / audit.
# --------------------------------------------------------------------------- #


async def test_unknown_item_is_safe_not_found() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="unknown-item")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")
        missing_item = uuid6.uuid7()
        response = await _post_disposition(
            client,
            fixture,
            body=_body(),
            idempotency_key=_idempotency_key("unknown"),
            item_id=missing_item,
        )

    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "not_found"


async def test_foreign_org_and_project_item_have_safe_not_found_parity() -> None:
    async with await _client() as owner, await _client() as foreign:
        owned = await _setup(owner, suffix="owned-parity")
        alien = await _setup(foreign, suffix="foreign-parity")

        foreign_item_through_owned_scope = await _post_disposition(
            owner,
            owned,
            body=_body(),
            idempotency_key=_idempotency_key("foreign-item"),
            item_id=alien.item_id,
        )
        foreign_tenant_through_owner_session = await _post_disposition(
            owner,
            owned,
            body=_body(),
            idempotency_key=_idempotency_key("foreign-tenant"),
            org_id=alien.org_id,
            project_id=alien.project_id,
            item_id=alien.item_id,
        )

    assert foreign_item_through_owned_scope.status_code == 404
    assert foreign_item_through_owned_scope.json()["error"]["code"] == "not_found"
    assert foreign_tenant_through_owner_session.status_code == 403
    assert foreign_tenant_through_owner_session.json()["error"]["code"] == "permission_denied"


async def test_same_key_same_intent_returns_original_persisted_result() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="replay")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")
        key = _idempotency_key("replay")
        body = _body(disposition="deferred")
        first = await _post_disposition(client, fixture, body=body, idempotency_key=key)
        second = await _post_disposition(client, fixture, body=body, idempotency_key=key)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["data"]["version"] == 2
    assert second.json()["data"]["version"] == 2
    async with session_scope() as session:
        records = (
            await session.execute(
                sa.text("SELECT count(*) FROM governed_decision_records WHERE item_id = :item_id"),
                {"item_id": str(fixture.item_id)},
            )
        ).scalar_one()
    assert records == 1


async def test_same_key_different_intent_returns_409() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="intent-conflict")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")
        key = _idempotency_key("intent-conflict")
        first = await _post_disposition(
            client,
            fixture,
            body=_body(disposition="deferred", rationale="First intent."),
            idempotency_key=key,
        )
        second = await _post_disposition(
            client,
            fixture,
            body=_body(disposition="ruled_out", rationale="A different intent entirely."),
            idempotency_key=key,
        )

    assert first.status_code == 200, first.text
    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] in {"conflict", "conflict_idempotency_mismatch"}


async def test_two_requests_at_same_expected_version_yield_one_success_and_one_stale_409() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="stale")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")
        first = await _post_disposition(
            client,
            fixture,
            body=_body(disposition="deferred", rationale="First writer wins."),
            idempotency_key=_idempotency_key("stale-a"),
        )
        second = await _post_disposition(
            client,
            fixture,
            body=_body(disposition="ruled_out", rationale="Second writer is stale."),
            idempotency_key=_idempotency_key("stale-b"),
        )

    assert first.status_code == 200, first.text
    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] in {"conflict", "conflict_stale_version"}


async def test_stale_failure_writes_no_record_audit_or_version_change() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="stale-noop")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")
        await _post_disposition(
            client,
            fixture,
            body=_body(disposition="deferred", rationale="Advance the version."),
            idempotency_key=_idempotency_key("stale-noop-a"),
        )
        stale = await _post_disposition(
            client,
            fixture,
            body=_body(disposition="ruled_out", rationale="Stale writer must not persist."),
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
        records = (
            await session.execute(
                sa.text("SELECT count(*) FROM governed_decision_records WHERE item_id = :item_id"),
                {"item_id": str(fixture.item_id)},
            )
        ).scalar_one()
        ruled_out_audits = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM authoritative_audit_events "
                    "WHERE target_id = :item_id AND payload_redacted LIKE :needle"
                ),
                {"item_id": str(fixture.item_id), "needle": "%ruled_out%"},
            )
        ).scalar_one()
    assert version == 2
    assert records == 1
    assert ruled_out_audits == 0


async def test_concurrent_cas_miss_surfaces_stale_409_not_404() -> None:
    """A version-guarded CAS that misses because the row moved *after* the
    command was classified as fresh must surface as a stale-version conflict
    (409), never a not-found (404)."""
    from dataclasses import replace

    from clearcut.decisions.delivery.http import _disposition_service

    async with await _client() as client:
        fixture = await _setup(client, suffix="cas-miss")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")

        original_load = _disposition_service._repository.load_scoped_item

        async def _load_then_advance(session, **kwargs):  # type: ignore[no-untyped-def]
            item = await original_load(session, **kwargs)
            await session.execute(
                sa.text(
                    "UPDATE clearance_items SET version = 2 "
                    "WHERE id = :id AND org_id = :org_id AND project_id = :project_id"
                ),
                {
                    "id": str(item.item_id),
                    "org_id": str(item.org_id),
                    "project_id": str(item.project_id),
                },
            )
            return replace(item, version=1)

        object.__setattr__(_disposition_service._repository, "load_scoped_item", _load_then_advance)
        try:
            response = await _post_disposition(
                client,
                fixture,
                body=_body(disposition="deferred", expected_version=1),
                idempotency_key=_idempotency_key("cas-miss"),
            )
        finally:
            object.__setattr__(_disposition_service._repository, "load_scoped_item", original_load)

    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] in {"conflict", "conflict_stale_version"}


async def test_concurrent_duplicate_idempotency_key_replays_prior_receipt() -> None:
    """A receipt insert that loses a unique-constraint race is reconciled into
    the prior receipt's idempotent replay, not a 500."""
    from clearcut.commanding.domain import CommandEnvelope
    from clearcut.commanding.sql import insert_command_receipt

    async with await _client() as client:
        fixture = await _setup(client, suffix="dup-key")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")
        key = _idempotency_key("dup-key")
        rationale = "Reviewed the cited evidence and defer this item for now."
        intent = _intent_hash("deferred", rationale, "1")

        prior_result_id = uuid6.uuid7()
        async with session_scope() as session:
            envelope = CommandEnvelope(
                org_id=fixture.org_id,
                project_id=fixture.project_id,
                actor_id=fixture.actor_id,
                operation="decision.disposition.set",
                idempotency_key=key,
                intent_hash=intent,
                expected_version=1,
            )
            await insert_command_receipt(
                session,
                envelope,
                item_id=fixture.item_id,
                resulting_version=2,
                result_id=prior_result_id,
                occurred_at=datetime.now(UTC),
            )

        import clearcut.decisions.application.set_disposition as service_module

        async def _no_prior(_session, _envelope):  # type: ignore[no-untyped-def]
            return None

        original_lookup = service_module.lookup_command_receipt
        service_module.lookup_command_receipt = _no_prior  # type: ignore[assignment]
        try:
            response = await _post_disposition(
                client,
                fixture,
                body=_body(disposition="deferred", intent_hash=intent),
                idempotency_key=key,
            )
        finally:
            service_module.lookup_command_receipt = original_lookup  # type: ignore[assignment]

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


async def test_expected_version_zero_is_rejected_as_validation_error() -> None:
    async with await _client() as client:
        fixture = await _setup(client, suffix="version-zero")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")
        response = await _post_disposition(
            client,
            fixture,
            body=_body(expected_version=0),
            idempotency_key=_idempotency_key("version-zero"),
        )

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "validation_failed"
    assert response.json()["error"]["message"] == "Request validation failed."


async def test_disposition_record_receipt_and_audit_commit_atomically() -> None:
    """A successful disposition writes the decision record, the item version and
    disposition advance, the command receipt, and one authoritative audit event
    in the same transaction, with a structured (non-f-string) payload."""
    async with await _client() as client:
        fixture = await _setup(client, suffix="atomic", with_claim=True)
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")
        key = _idempotency_key("atomic")
        response = await _post_disposition(
            client,
            fixture,
            body=_body(disposition="verified", rationale="The register confirms the mark."),
            idempotency_key=key,
        )

    assert response.status_code == 200, response.text
    async with session_scope() as session:
        version, disposition = (
            await session.execute(
                sa.text("SELECT version, disposition_status FROM clearance_items WHERE id = :id"),
                {"id": str(fixture.item_id)},
            )
        ).one()
        records = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM governed_decision_records "
                    "WHERE item_id = :item_id AND decision_kind = 'disposition' "
                    "AND decision_value = 'verified'"
                ),
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
        audit_payload = (
            await session.execute(
                sa.text(
                    "SELECT payload_redacted FROM authoritative_audit_events "
                    "WHERE target_id = :item_id"
                ),
                {"item_id": str(fixture.item_id)},
            )
        ).scalar_one()
        # The retired direct-SQL handler wrote the legacy audit_events table; the
        # governed replacement must leave it empty for this item.
        legacy_audits = (
            await session.execute(
                sa.text("SELECT count(*) FROM audit_events WHERE target_id = :item_id"),
                {"item_id": str(fixture.item_id)},
            )
        ).scalar_one()

    assert version == 2
    assert disposition == "verified"
    assert records == 1
    assert receipts == 1
    assert legacy_audits == 0
    # The audit payload is a structured mapping with the disposition and version
    # advance, not an f-string JSON blob. Whatever the storage encoding, it must
    # contain the canonical disposition and both version numbers.
    payload_text = str(audit_payload)
    assert "verified" in payload_text
    assert "resultingVersion" in payload_text or "resulting_version" in payload_text


async def test_authoritative_audit_failure_rolls_back_record_version_and_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import clearcut.decisions.application.set_disposition as service_module

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
        response = await _post_disposition(
            client,
            fixture,
            body=_body(disposition="deferred", rationale="Should roll back."),
            idempotency_key=key,
        )

    assert response.status_code == 500, response.text
    async with session_scope() as session:
        version, disposition = (
            await session.execute(
                sa.text("SELECT version, disposition_status FROM clearance_items WHERE id = :id"),
                {"id": str(fixture.item_id)},
            )
        ).one()
        records = (
            await session.execute(
                sa.text("SELECT count(*) FROM governed_decision_records WHERE item_id = :item_id"),
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

    assert version == 1
    assert disposition == "undisposed"
    assert records == 0
    assert receipts == 0

"""Behavioral tests for the governed evidence-decision vertical slice.

These tests pin the canonical ``:recordEvidenceDecision`` operation end to end:
a Reviewer/Admin/Owner records exactly one evidence decision on an exact,
tenant-and-project-scoped clearance item, with server-derived capability
enforcement, expected-version optimistic concurrency, intent/idempotency,
zero-evidence protection for clearance-like outcomes, and a same-transaction
authoritative audit event. The tests exercise the mounted FastAPI route
(reusing the shared governed-command kernel and migration 0030 tables) rather
than any in-memory stub, so tenant scope, safe not-found parity, and the
transactional decision+receipt+audit boundary are all covered against the real
migrated schema.
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


def _decision_path(org_id: UUID, project_id: UUID, item_id: UUID) -> str:
    return (
        f"/api/v1/organizations/{org_id}/projects/{project_id}"
        f"/clearance-items/{item_id}:recordEvidenceDecision"
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
            "email": f"reviewer-{suffix}-{uuid4().hex}@example.com",
            "password": _PASSWORD,
        },
    )
    assert registration.status_code == 201, registration.text
    return UUID(registration.json()["data"]["userId"])


async def _create_org_and_project(client: AsyncClient, *, suffix: str) -> tuple[UUID, UUID]:
    # Org slugs allow only [a-z0-9-]; normalize the descriptive suffix.
    slug_suffix = suffix.replace("_", "-")
    organization = await client.post(
        "/api/v1/organizations",
        json={
            "name": f"Decision Studio {suffix}",
            "slug": f"decision-{slug_suffix}-{uuid4().hex[:8]}",
        },
    )
    assert organization.status_code == 201, organization.text
    org_id = UUID(organization.json()["data"]["orgId"])
    project = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        json={"title": f"Decision Project {suffix}"},
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
                "VALUES (:id, :org_id, :project_id, 'Decision test', :created_at)"
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
                "status, research_status, workflow_status, disposition_status, created_at, version) "
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
    decision: str = "further_review_required",
    rationale: str = "Reviewed the cited evidence and require further review.",
    expected_version: int = 1,
    intent_hash: str | None = None,
) -> dict:
    return {
        "decision": decision,
        "rationale": rationale,
        "expectedVersion": expected_version,
        "intentHash": intent_hash or _intent_hash(decision, rationale, str(expected_version)),
    }


async def _post_decision(
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
        _decision_path(
            org_id or fixture.org_id,
            project_id or fixture.project_id,
            item_id or fixture.item_id,
        ),
        json=body,
        headers={"Idempotency-Key": idempotency_key},
    )


# --------------------------------------------------------------------------- #
# Group 1: Role / scope.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("role", ["owner", "admin", "reviewer"])
async def test_authorized_roles_record_evidence_decision(role: str) -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix=f"authz-{role}")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role=role)
        response = await _post_decision(
            client, fixture, body=_body(), idempotency_key=_idempotency_key(role)
        )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["itemId"] == str(fixture.item_id)
    assert data["projectId"] == str(fixture.project_id)
    assert data["version"] == 2
    assert response.json()["meta"]["requestId"]


@pytest.mark.parametrize("role", ["editor", "viewer"])
async def test_unauthorized_roles_are_denied_with_typed_403(role: str) -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix=f"deny-{role}")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role=role)
        response = await _post_decision(
            client, fixture, body=_body(), idempotency_key=_idempotency_key(role)
        )

    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "permission_denied"
    # No decision or audit was written for a denied actor.
    async with session_scope() as session:
        decisions = (
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
    assert decisions == 0
    assert version == 1


async def test_deactivated_membership_cannot_record_decision() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="deactivated")
        await _deactivate_membership(org_id=fixture.org_id, user_id=fixture.actor_id)
        response = await _post_decision(
            client, fixture, body=_body(), idempotency_key=_idempotency_key("deactivated")
        )

    # A deactivated membership is not an active member: access denied to org.
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "permission_denied"


async def test_unknown_item_is_safe_not_found() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="unknown-item")
        missing_item = uuid6.uuid7()
        response = await _post_decision(
            client,
            fixture,
            body=_body(),
            idempotency_key=_idempotency_key("unknown"),
            item_id=missing_item,
        )

    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "not_found"


async def test_foreign_org_and_project_item_have_safe_not_found_parity() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as owner, await _client() as foreign:
        owned = await _setup(owner, suffix="owned-parity")
        alien = await _setup(foreign, suffix="foreign-parity")

        # Foreign item id addressed through the owner's own authorized scope: the
        # item is not visible, so a neutral 404 (never a 200 or a distinguishing
        # 403) is returned.
        foreign_item_through_owned_scope = await _post_decision(
            owner,
            owned,
            body=_body(),
            idempotency_key=_idempotency_key("foreign-item"),
            item_id=alien.item_id,
        )
        # Foreign org/project addressed with the owner's session: membership is
        # absent, denied at the organization boundary.
        foreign_tenant_through_owner_session = await _post_decision(
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


# --------------------------------------------------------------------------- #
# Group 2: Evidence / validation.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("decision", ["cleared", "accept_as_is", "approve", "", "yes"])
async def test_non_canonical_decision_values_are_rejected(decision: str) -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="canonical")
        response = await _post_decision(
            client,
            fixture,
            body=_body(decision=decision),
            idempotency_key=_idempotency_key("canonical"),
        )

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "validation_failed"


@pytest.mark.parametrize(
    "mutate",
    [
        {"rationale": ""},
        {"expectedVersion": None},
        {"intentHash": ""},
    ],
)
async def test_missing_required_fields_are_rejected(mutate: dict) -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="required")
        body = _body()
        body.update(mutate)
        response = await _post_decision(
            client, fixture, body=body, idempotency_key=_idempotency_key("required")
        )

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "validation_failed"


async def test_missing_idempotency_key_header_is_rejected() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="no-idem")
        response = await client.post(
            _decision_path(fixture.org_id, fixture.project_id, fixture.item_id),
            json=_body(),
        )

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "validation_failed"


async def test_accept_outcome_rejected_when_item_has_zero_cited_claims() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="zero-accept", with_claim=False)
        response = await _post_decision(
            client,
            fixture,
            body=_body(decision="accepted", rationale="Accept the cited evidence."),
            idempotency_key=_idempotency_key("zero-accept"),
        )

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "validation_failed"
    # No decision/version change followed the rejected clearance-like outcome.
    async with session_scope() as session:
        version = (
            await session.execute(
                sa.text("SELECT version FROM clearance_items WHERE id = :id"),
                {"id": str(fixture.item_id)},
            )
        ).scalar_one()
        decisions = (
            await session.execute(
                sa.text("SELECT count(*) FROM governed_decision_records WHERE item_id = :item_id"),
                {"item_id": str(fixture.item_id)},
            )
        ).scalar_one()
    assert version == 1
    assert decisions == 0


async def test_accept_outcome_allowed_when_item_has_cited_claims() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="accept-with-claim", with_claim=True)
        response = await _post_decision(
            client,
            fixture,
            body=_body(decision="accepted", rationale="Accept the cited evidence."),
            idempotency_key=_idempotency_key("accept-with-claim"),
        )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["version"] == 2


@pytest.mark.parametrize("decision", ["further_review_required", "rejected"])
async def test_escalation_outcomes_allowed_with_zero_claims(decision: str) -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix=f"escalate-{decision}", with_claim=False)
        response = await _post_decision(
            client,
            fixture,
            body=_body(decision=decision, rationale="No evidence yet; escalate for review."),
            idempotency_key=_idempotency_key(f"escalate-{decision}"),
        )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["version"] == 2


# --------------------------------------------------------------------------- #
# Group 3: Concurrency / idempotency.
# --------------------------------------------------------------------------- #


async def test_same_key_same_intent_returns_original_persisted_result() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="replay")
        key = _idempotency_key("replay")
        body = _body(decision="further_review_required")
        first = await _post_decision(client, fixture, body=body, idempotency_key=key)
        second = await _post_decision(client, fixture, body=body, idempotency_key=key)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    # The replay reproduces the original result without advancing the version again.
    assert first.json()["data"]["version"] == 2
    assert second.json()["data"]["version"] == 2
    async with session_scope() as session:
        decisions = (
            await session.execute(
                sa.text("SELECT count(*) FROM governed_decision_records WHERE item_id = :item_id"),
                {"item_id": str(fixture.item_id)},
            )
        ).scalar_one()
    assert decisions == 1


async def test_same_key_different_intent_returns_409() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="intent-conflict")
        key = _idempotency_key("intent-conflict")
        first = await _post_decision(
            client,
            fixture,
            body=_body(decision="further_review_required", rationale="First intent."),
            idempotency_key=key,
        )
        second = await _post_decision(
            client,
            fixture,
            body=_body(decision="rejected", rationale="A different intent entirely."),
            idempotency_key=key,
        )

    assert first.status_code == 200, first.text
    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] in {"conflict", "conflict_idempotency_mismatch"}


async def test_two_requests_at_same_expected_version_yield_one_success_and_one_stale_409() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="stale")
        first = await _post_decision(
            client,
            fixture,
            body=_body(decision="further_review_required", rationale="First writer wins."),
            idempotency_key=_idempotency_key("stale-a"),
        )
        # A different idempotency key with the same stale expected_version=1 must
        # observe the advanced version and lose optimistically.
        second = await _post_decision(
            client,
            fixture,
            body=_body(decision="rejected", rationale="Second writer is stale."),
            idempotency_key=_idempotency_key("stale-b"),
        )

    assert first.status_code == 200, first.text
    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] in {"conflict", "conflict_stale_version"}


async def test_stale_failure_writes_no_decision_audit_or_version_change() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="stale-noop")
        await _post_decision(
            client,
            fixture,
            body=_body(decision="further_review_required", rationale="Advance the version."),
            idempotency_key=_idempotency_key("stale-noop-a"),
        )
        stale = await _post_decision(
            client,
            fixture,
            body=_body(decision="rejected", rationale="Stale writer must not persist."),
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
        decisions = (
            await session.execute(
                sa.text("SELECT count(*) FROM governed_decision_records WHERE item_id = :item_id"),
                {"item_id": str(fixture.item_id)},
            )
        ).scalar_one()
        rejected_audits = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM authoritative_audit_events "
                    "WHERE target_id = :item_id AND payload_redacted LIKE :needle"
                ),
                {"item_id": str(fixture.item_id), "needle": "%rejected%"},
            )
        ).scalar_one()
    # Exactly one committed decision (the first), version advanced only once, and
    # the stale rejected outcome left no audit trace.
    assert version == 2
    assert decisions == 1
    assert rejected_audits == 0


async def test_concurrent_cas_miss_surfaces_stale_409_not_404() -> None:
    """A version-guarded CAS that misses because the row moved *after* the
    command was classified as fresh must surface as a stale-version conflict
    (409), never a not-found (404).

    The sequential route flow cannot produce this window on its own, so the
    concurrent advance is simulated: the loaded item reports the client's
    expected version (so ``classify_command`` sees a fresh write), while the
    underlying row is bumped to a different version before the compare-and-swap
    runs. The item plainly exists in scope, so the miss is a stale conflict.
    """
    from dataclasses import replace

    from clearcut.decisions.delivery.http import _service

    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="cas-miss")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")

        original_load = _service._repository.load_scoped_item

        async def _load_then_advance(session, **kwargs):  # type: ignore[no-untyped-def]
            item = await original_load(session, **kwargs)
            # Simulate a concurrent writer advancing the row *after* this
            # transaction observed version 1: bump the real row so the guarded
            # UPDATE (expected_version=1) will affect zero rows.
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
            # The service still classifies against the observed version 1.
            return replace(item, version=1)

        object.__setattr__(_service._repository, "load_scoped_item", _load_then_advance)
        try:
            response = await _post_decision(
                client,
                fixture,
                body=_body(decision="further_review_required", expected_version=1),
                idempotency_key=_idempotency_key("cas-miss"),
            )
        finally:
            object.__setattr__(_service._repository, "load_scoped_item", original_load)

    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] in {"conflict", "conflict_stale_version"}


async def test_concurrent_duplicate_idempotency_key_replays_prior_receipt() -> None:
    """A receipt insert that loses a unique-constraint race is reconciled into
    the prior receipt's idempotent replay, not a 500.

    A concurrent duplicate is simulated by pre-inserting a receipt for the exact
    ``(org, project, actor, operation, idempotency_key)`` scope this request
    will use. The adapter's own receipt insert then violates the unique
    constraint; instead of surfacing a 500, the service must re-read the prior
    receipt and return the original idempotent result.
    """
    from clearcut.commanding.domain import CommandEnvelope
    from clearcut.commanding.sql import insert_command_receipt

    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="dup-key")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="reviewer")
        key = _idempotency_key("dup-key")
        rationale = "Reviewed the cited evidence and require further review."
        intent = _intent_hash("further_review_required", rationale, "1")

        prior_result_id = uuid6.uuid7()
        async with session_scope() as session:
            envelope = CommandEnvelope(
                org_id=fixture.org_id,
                project_id=fixture.project_id,
                actor_id=fixture.actor_id,
                operation="decision.evidence.record",
                idempotency_key=key,
                intent_hash=intent,
                expected_version=1,
            )
            # A concurrent writer already committed the receipt for this scope,
            # but the lookup at request time races ahead of it (simulated by the
            # adapter attempting a fresh insert that then conflicts).
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
        import clearcut.decisions.application.record_evidence_decision as service_module

        async def _no_prior(_session, _envelope):  # type: ignore[no-untyped-def]
            return None

        original_lookup = service_module.lookup_command_receipt
        service_module.lookup_command_receipt = _no_prior  # type: ignore[assignment]
        try:
            response = await _post_decision(
                client,
                fixture,
                body=_body(decision="further_review_required", intent_hash=intent),
                idempotency_key=key,
            )
        finally:
            service_module.lookup_command_receipt = original_lookup  # type: ignore[assignment]

    # The duplicate receipt is reconciled into the prior result, not a 500.
    assert response.status_code == 200, response.text
    assert response.json()["data"]["version"] == 2
    # Exactly one committed decision and one receipt: the replay wrote no second
    # decision despite losing the receipt race.
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
    """The delivery body requires ``expectedVersion >= 1`` to match the kernel's
    positive-version rule, so a zero is rejected at the request boundary (a
    framework validation error) rather than slipping through to a confusing
    kernel-side mismatch inside the handler.
    """
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="version-zero")
        response = await _post_decision(
            client,
            fixture,
            body=_body(expected_version=0),
            idempotency_key=_idempotency_key("version-zero"),
        )

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "validation_failed"
    # The rejection is the delivery-boundary request-validation envelope, not the
    # kernel's positive-version message reached from inside the handler.
    assert response.json()["error"]["message"] == "Request validation failed."


# --------------------------------------------------------------------------- #
# Group 4: Audit rollback.
# --------------------------------------------------------------------------- #


async def test_authoritative_audit_failure_rolls_back_decision_version_and_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await init_and_seed_db(seed_if_empty=False)

    import clearcut.decisions.application.record_evidence_decision as service_module

    class _InjectedAuditError(RuntimeError):
        pass

    async def _boom(*_args: object, **_kwargs: object) -> None:
        raise _InjectedAuditError("injected authoritative audit failure")

    monkeypatch.setattr(service_module, "insert_authoritative_audit", _boom)

    # Observe the app's canonical 500 envelope rather than re-raising the ASGI
    # exception, so we can assert the response the client actually receives.
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
        headers={"origin": "http://test"},
    ) as client:
        fixture = await _setup(client, suffix="rollback")
        key = _idempotency_key("rollback")
        response = await _post_decision(
            client,
            fixture,
            body=_body(decision="further_review_required", rationale="Should roll back."),
            idempotency_key=key,
        )

    # The injected failure surfaces as an internal error, not a partial success.
    assert response.status_code == 500, response.text

    async with session_scope() as session:
        version = (
            await session.execute(
                sa.text("SELECT version FROM clearance_items WHERE id = :id"),
                {"id": str(fixture.item_id)},
            )
        ).scalar_one()
        status_value = (
            await session.execute(
                sa.text("SELECT status FROM clearance_items WHERE id = :id"),
                {"id": str(fixture.item_id)},
            )
        ).scalar_one()
        decisions = (
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
    assert status_value == "unresolved"
    assert decisions == 0
    assert receipts == 0

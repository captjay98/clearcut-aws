"""Behavioral tests for the bounded learning-candidate lifecycle over HTTP.

These exercise the mounted FastAPI routes against the real migrated schema
(migration 0036), not an in-memory stub, so tenant scope, Owner-only capability,
the protected-scope boundary, the regression/canary gates, the stage machine, and
the same-transaction authoritative audit event are all covered end to end.

The router is included here if the application has not already mounted it, so the
slice is testable independently of when ``main.py`` picks it up.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
import uuid6
from clearcut.database import session_scope
from clearcut.evaluation.delivery.learning_http import router as learning_router
from clearcut.init_db import init_and_seed_db
from clearcut.main import app
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.asyncio

_PASSWORD = "Password123!"
_LIST_PATH = "/api/v1/organizations/{orgId}/learning-candidates"

if not any(getattr(route, "path", None) == _LIST_PATH for route in app.routes):
    app.include_router(learning_router)


@dataclass(frozen=True)
class Fixture:
    org_id: UUID
    actor_id: UUID


async def _client() -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"origin": "http://test"},
    )


async def _register_actor(client: AsyncClient, *, suffix: str) -> UUID:
    registration = await client.post(
        "/api/v1/users",
        json={
            "name": f"Learning Owner {suffix}",
            "email": f"learning-{suffix}-{uuid4().hex}@example.com",
            "password": _PASSWORD,
        },
    )
    assert registration.status_code == 201, registration.text
    return UUID(registration.json()["data"]["userId"])


async def _create_org(client: AsyncClient, *, suffix: str) -> UUID:
    slug_suffix = suffix.replace("_", "-")
    organization = await client.post(
        "/api/v1/organizations",
        json={
            "name": f"Learning Studio {suffix}",
            "slug": f"learning-{slug_suffix}-{uuid4().hex[:8]}",
        },
    )
    assert organization.status_code == 201, organization.text
    return UUID(organization.json()["data"]["orgId"])


async def _setup(client: AsyncClient, *, suffix: str) -> Fixture:
    actor_id = await _register_actor(client, suffix=suffix)
    org_id = await _create_org(client, suffix=suffix)
    return Fixture(org_id=org_id, actor_id=actor_id)


async def _insert_candidate(
    *,
    org_id: UUID,
    scope: str = "query_phrasing",
    stage: str = "canary",
    target_scope: str | None = "query_phrasing",
    canary_pass_rate: float = 0.99,
    regression_passed: int = 12,
    regression_total: int = 12,
    version: int = 1,
    title: str = "Tighten trademark status phrasing",
) -> UUID:
    candidate_id = uuid6.uuid7()
    proposed: dict[str, object] = {"diff": "add 'registered status' to the query"}
    if target_scope is not None:
        proposed["target_scope"] = target_scope
    now = datetime.now(UTC)
    async with session_scope() as session:
        await session.execute(
            sa.text(
                """
                INSERT INTO learning_candidates (
                    id, org_id, scope, proposed_changes, canary_pass_rate, is_promoted,
                    created_at, stage, title, summary, regression_cases_passed,
                    regression_cases_total, version
                ) VALUES (
                    :id, :org_id, :scope, :proposed_changes, :canary_pass_rate, :is_promoted,
                    :created_at, :stage, :title, :summary, :regression_passed,
                    :regression_total, :version
                )
                """
            ).bindparams(sa.bindparam("proposed_changes", type_=sa.JSON())),
            {
                "id": str(candidate_id),
                "org_id": str(org_id),
                "scope": scope,
                "proposed_changes": proposed,
                "canary_pass_rate": canary_pass_rate,
                "is_promoted": stage == "promoted",
                "created_at": now,
                "stage": stage,
                "title": title,
                "summary": "Observed in shadow, then canary.",
                "regression_passed": regression_passed,
                "regression_total": regression_total,
                "version": version,
            },
        )
    return candidate_id


async def _promote_to_stage(*, org_id: UUID, candidate_id: UUID, actor_id: UUID) -> None:
    """Move a candidate directly to ``promoted`` in storage, as a prior act would."""
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "UPDATE learning_candidates SET stage = 'promoted', is_promoted = :promoted, "
                "promoted_at = :promoted_at, promoted_by = :promoted_by "
                "WHERE id = :id AND org_id = :org_id"
            ),
            {
                "promoted": True,
                "promoted_at": datetime.now(UTC),
                "promoted_by": str(actor_id),
                "id": str(candidate_id),
                "org_id": str(org_id),
            },
        )


async def _set_membership_role(*, org_id: UUID, user_id: UUID, role: str) -> None:
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "UPDATE memberships SET role = :role WHERE org_id = :org_id AND user_id = :user_id"
            ),
            {"role": role, "org_id": str(org_id), "user_id": str(user_id)},
        )


async def _stage_of(*, org_id: UUID, candidate_id: UUID) -> sa.RowMapping:
    async with session_scope() as session:
        return (
            (
                await session.execute(
                    sa.text(
                        "SELECT stage, is_promoted, version, promoted_by, rolled_back_by, "
                        "rolled_back_at, rollback_reason FROM learning_candidates "
                        "WHERE id = :id AND org_id = :org_id"
                    ),
                    {"id": str(candidate_id), "org_id": str(org_id)},
                )
            )
            .mappings()
            .one()
        )


async def _audit_events(*, org_id: UUID, target_id: UUID) -> list[sa.RowMapping]:
    async with session_scope() as session:
        return list(
            (
                await session.execute(
                    sa.text(
                        "SELECT action, actor_id, project_id, target_type, payload_redacted "
                        "FROM authoritative_audit_events "
                        "WHERE org_id = :org_id AND target_id = :target_id "
                        "ORDER BY occurred_at"
                    ),
                    {"org_id": str(org_id), "target_id": str(target_id)},
                )
            )
            .mappings()
            .all()
        )


def _promote_path(org_id: UUID, candidate_id: UUID) -> str:
    return f"/api/v1/organizations/{org_id}/learning-candidates/{candidate_id}:promote"


def _rollback_path(org_id: UUID, candidate_id: UUID) -> str:
    return f"/api/v1/organizations/{org_id}/learning-candidates/{candidate_id}:rollback"


async def test_owner_promotes_a_gated_candidate_and_the_audit_event_commits() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="promote")
        candidate_id = await _insert_candidate(org_id=fixture.org_id)

        promoted = await client.post(_promote_path(fixture.org_id, candidate_id))
        assert promoted.status_code == 200, promoted.text
        assert promoted.json()["data"] == {
            "candidateId": str(candidate_id),
            "stage": "promoted",
        }

        listed = await client.get(f"/api/v1/organizations/{fixture.org_id}/learning-candidates")
        assert listed.status_code == 200, listed.text
        entry = listed.json()["data"][0]
        assert entry["candidateId"] == str(candidate_id)
        assert entry["orgId"] == str(fixture.org_id)
        assert entry["scope"] == "query_phrasing"
        assert entry["stage"] == "promoted"
        assert entry["canaryPassRate"] == pytest.approx(0.99)
        assert entry["regressionCasesPassed"] == 12
        assert entry["regressionCasesTotal"] == 12
        assert entry["version"] == 2
        assert entry["promotedAt"]
        assert entry["createdAt"]

    row = await _stage_of(org_id=fixture.org_id, candidate_id=candidate_id)
    assert row["stage"] == "promoted"
    # The legacy boolean is derived from the stage, so the two cannot disagree.
    assert bool(row["is_promoted"]) is True
    assert row["version"] == 2
    assert UUID(str(row["promoted_by"])) == fixture.actor_id

    events = await _audit_events(org_id=fixture.org_id, target_id=candidate_id)
    assert len(events) == 1
    assert events[0]["action"] == "learning.candidate.promoted"
    assert events[0]["target_type"] == "learning_candidate"
    assert UUID(str(events[0]["actor_id"])) == fixture.actor_id
    # A learning candidate is organization-owned, so the event names no project.
    assert events[0]["project_id"] is None


async def test_a_candidate_targeting_a_protected_scope_cannot_be_promoted() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="protected")
        candidate_id = await _insert_candidate(
            org_id=fixture.org_id,
            scope="prompt_refinement",
            target_scope="legal_boundary",
        )

        refused = await client.post(_promote_path(fixture.org_id, candidate_id))
        assert refused.status_code == 403, refused.text
        assert refused.json()["error"]["code"] == "permission_denied"
        assert "legal_boundary" in refused.json()["error"]["message"]

    row = await _stage_of(org_id=fixture.org_id, candidate_id=candidate_id)
    assert row["stage"] == "canary"
    assert row["version"] == 1
    assert await _audit_events(org_id=fixture.org_id, target_id=candidate_id) == []


async def test_a_candidate_naming_an_unknown_scope_cannot_be_promoted() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="unbounded")
        candidate_id = await _insert_candidate(
            org_id=fixture.org_id,
            target_scope="deterministic_blocking_rules",
        )

        refused = await client.post(_promote_path(fixture.org_id, candidate_id))
        assert refused.status_code == 403, refused.text
        assert refused.json()["error"]["code"] == "permission_denied"

    assert (await _stage_of(org_id=fixture.org_id, candidate_id=candidate_id))["stage"] == "canary"


async def test_a_non_owner_cannot_promote_or_roll_back() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="non-owner")
        candidate_id = await _insert_candidate(org_id=fixture.org_id)
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="admin")

        refused_promote = await client.post(_promote_path(fixture.org_id, candidate_id))
        assert refused_promote.status_code == 403, refused_promote.text
        assert refused_promote.json()["error"]["code"] == "permission_denied"

        refused_rollback = await client.post(_rollback_path(fixture.org_id, candidate_id))
        assert refused_rollback.status_code == 403, refused_rollback.text

        # A non-Owner member may still read the lifecycle.
        listed = await client.get(f"/api/v1/organizations/{fixture.org_id}/learning-candidates")
        assert listed.status_code == 200, listed.text
        assert listed.json()["data"][0]["stage"] == "canary"

    row = await _stage_of(org_id=fixture.org_id, candidate_id=candidate_id)
    assert row["stage"] == "canary"
    assert await _audit_events(org_id=fixture.org_id, target_id=candidate_id) == []


async def test_promotion_below_the_regression_and_canary_gates_is_refused() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="gates")
        failing_regression = await _insert_candidate(
            org_id=fixture.org_id,
            regression_passed=9,
            regression_total=12,
        )
        weak_canary = await _insert_candidate(
            org_id=fixture.org_id,
            canary_pass_rate=0.85,
        )
        no_regression_evidence = await _insert_candidate(
            org_id=fixture.org_id,
            regression_passed=0,
            regression_total=0,
        )

        refused_regression = await client.post(_promote_path(fixture.org_id, failing_regression))
        assert refused_regression.status_code == 422, refused_regression.text
        assert refused_regression.json()["error"]["code"] == "validation_failed"
        assert "regression" in refused_regression.json()["error"]["message"]

        refused_canary = await client.post(_promote_path(fixture.org_id, weak_canary))
        assert refused_canary.status_code == 422, refused_canary.text
        assert "canary" in refused_canary.json()["error"]["message"]

        refused_empty = await client.post(_promote_path(fixture.org_id, no_regression_evidence))
        assert refused_empty.status_code == 422, refused_empty.text

    for candidate_id in (failing_regression, weak_canary, no_regression_evidence):
        row = await _stage_of(org_id=fixture.org_id, candidate_id=candidate_id)
        assert row["stage"] == "canary"
        assert bool(row["is_promoted"]) is False
        assert await _audit_events(org_id=fixture.org_id, target_id=candidate_id) == []


async def test_the_stage_machine_rejects_an_illegal_transition() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="stage-machine")
        # A fresh candidate has not been observed in shadow or canary yet.
        unobserved = await _insert_candidate(org_id=fixture.org_id, stage="candidate")
        refused = await client.post(_promote_path(fixture.org_id, unobserved))
        assert refused.status_code == 422, refused.text
        assert refused.json()["error"]["code"] == "validation_failed"
        assert "candidate" in refused.json()["error"]["message"]

        # Rollback is not available before a change has been exposed.
        refused_rollback = await client.post(_rollback_path(fixture.org_id, unobserved))
        assert refused_rollback.status_code == 422, refused_rollback.text

        # A promoted candidate cannot be promoted again: a repeat is a refusal,
        # never a silent no-op that would write a second audit event.
        promoted = await _insert_candidate(org_id=fixture.org_id)
        first = await client.post(_promote_path(fixture.org_id, promoted))
        assert first.status_code == 200, first.text
        second = await client.post(_promote_path(fixture.org_id, promoted))
        assert second.status_code == 422, second.text

    assert (await _stage_of(org_id=fixture.org_id, candidate_id=unobserved))["stage"] == "candidate"
    assert len(await _audit_events(org_id=fixture.org_id, target_id=promoted)) == 1


async def test_rollback_from_promoted_records_who_did_it_and_why() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="rollback")
        candidate_id = await _insert_candidate(org_id=fixture.org_id)
        await _promote_to_stage(
            org_id=fixture.org_id,
            candidate_id=candidate_id,
            actor_id=fixture.actor_id,
        )

        rolled_back = await client.post(
            _rollback_path(fixture.org_id, candidate_id),
            json={"reason": "Reviewers saw weaker retrieval on period scripts."},
        )
        assert rolled_back.status_code == 200, rolled_back.text
        assert rolled_back.json()["data"] == {
            "candidateId": str(candidate_id),
            "stage": "rolled_back",
        }

        listed = await client.get(f"/api/v1/organizations/{fixture.org_id}/learning-candidates")
        entry = listed.json()["data"][0]
        assert entry["stage"] == "rolled_back"
        assert entry["rolledBackAt"]
        assert entry["rollbackReason"] == "Reviewers saw weaker retrieval on period scripts."

    row = await _stage_of(org_id=fixture.org_id, candidate_id=candidate_id)
    assert row["stage"] == "rolled_back"
    assert bool(row["is_promoted"]) is False
    assert UUID(str(row["rolled_back_by"])) == fixture.actor_id
    assert row["rolled_back_at"] is not None
    assert row["rollback_reason"] == "Reviewers saw weaker retrieval on period scripts."

    events = await _audit_events(org_id=fixture.org_id, target_id=candidate_id)
    assert [event["action"] for event in events] == ["learning.candidate.rolled_back"]
    assert UUID(str(events[0]["actor_id"])) == fixture.actor_id


async def test_rollback_from_canary_is_permitted_without_meeting_any_gate() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="rollback-canary")
        # Deliberately below every promotion gate: withdrawing a change must not
        # depend on the evidence that would have justified keeping it.
        candidate_id = await _insert_candidate(
            org_id=fixture.org_id,
            canary_pass_rate=0.10,
            regression_passed=0,
            regression_total=8,
        )

        rolled_back = await client.post(_rollback_path(fixture.org_id, candidate_id))
        assert rolled_back.status_code == 200, rolled_back.text
        assert rolled_back.json()["data"]["stage"] == "rolled_back"

    row = await _stage_of(org_id=fixture.org_id, candidate_id=candidate_id)
    assert row["stage"] == "rolled_back"
    assert row["rollback_reason"] is None
    assert UUID(str(row["rolled_back_by"])) == fixture.actor_id


async def test_a_stale_expected_version_is_a_conflict() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="stale")
        candidate_id = await _insert_candidate(org_id=fixture.org_id, version=3)

        conflict = await client.post(
            _promote_path(fixture.org_id, candidate_id),
            json={"expectedVersion": 2},
        )
        assert conflict.status_code == 409, conflict.text
        assert conflict.json()["error"]["code"] == "conflict_stale_version"

    row = await _stage_of(org_id=fixture.org_id, candidate_id=candidate_id)
    assert row["stage"] == "canary"
    assert row["version"] == 3
    assert await _audit_events(org_id=fixture.org_id, target_id=candidate_id) == []


async def test_candidates_are_organization_scoped_with_neutral_not_found() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as owner_client:
        owner = await _setup(owner_client, suffix="tenant-owner")
        candidate_id = await _insert_candidate(org_id=owner.org_id)

    async with await _client() as other_client:
        other = await _setup(other_client, suffix="tenant-other")

        denied = await other_client.post(_promote_path(other.org_id, candidate_id))
        assert denied.status_code == 404, denied.text
        assert denied.json()["error"]["code"] == "not_found"

        unparseable = await other_client.post(
            f"/api/v1/organizations/{other.org_id}/learning-candidates/not-a-uuid:promote"
        )
        assert unparseable.status_code == 404, unparseable.text
        assert unparseable.json()["error"]["code"] == "not_found"

        listed = await other_client.get(f"/api/v1/organizations/{other.org_id}/learning-candidates")
        assert listed.status_code == 200, listed.text
        assert listed.json()["data"] == []

    row = await _stage_of(org_id=owner.org_id, candidate_id=candidate_id)
    assert row["stage"] == "canary"


async def test_an_unknown_body_field_is_rejected() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="strict-body")
        candidate_id = await _insert_candidate(org_id=fixture.org_id)

        rejected = await client.post(
            _promote_path(fixture.org_id, candidate_id),
            json={"expectedVersion": 1, "force": True},
        )
        assert rejected.status_code == 422, rejected.text

    assert (await _stage_of(org_id=fixture.org_id, candidate_id=candidate_id))["stage"] == "canary"

"""Authoritative, tenant-scoped item detail projection tests for Task 9."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
import uuid6
from clearcut.database import engine, session_scope
from clearcut.items.adapters.sql_read_repository import SqlItemReadRepository
from clearcut.main import app
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event

pytestmark = pytest.mark.asyncio


@dataclass(frozen=True)
class DetailFixture:
    org_id: UUID
    project_id: UUID
    item_id: UUID
    version_id: UUID
    actor_id: UUID


async def _client() -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"origin": "http://test"},
    )


async def _fixture(client: AsyncClient, suffix: str) -> DetailFixture:
    registration = await client.post(
        "/api/v1/users",
        json={
            "name": f"Detail Owner {suffix}",
            "email": f"detail-{suffix}-{uuid4().hex}@example.com",
            "password": "Password123!",
        },
    )
    assert registration.status_code == 201, registration.text
    actor_id = UUID(registration.json()["data"]["userId"])
    organization = await client.post(
        "/api/v1/organizations",
        json={
            "name": f"Detail Studio {suffix}",
            "slug": f"detail-{suffix}-{uuid4().hex[:8]}",
        },
    )
    assert organization.status_code == 201, organization.text
    org_id = UUID(organization.json()["data"]["orgId"])
    project = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        json={"title": f"Detail Project {suffix}"},
    )
    assert project.status_code == 201, project.text
    project_id = UUID(project.json()["data"]["projectId"])

    script_id, version_id, element_id, item_id = (uuid6.uuid7() for _ in range(4))
    now = datetime.now(UTC)
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO scripts (id, org_id, project_id, title, created_at) "
                "VALUES (:id, :org, :project, 'Detail script', :created)"
            ),
            {"id": str(script_id), "org": str(org_id), "project": str(project_id), "created": now},
        )
        await session.execute(
            sa.text(
                "INSERT INTO script_versions "
                "(id, script_id, org_id, project_id, ordinal, source_hash, parser_version, created_at) "
                "VALUES (:id, :script, :org, :project, 1, :hash, 'test', :created)"
            ),
            {
                "id": str(version_id),
                "script": str(script_id),
                "org": str(org_id),
                "project": str(project_id),
                "hash": uuid4().hex,
                "created": now,
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO script_elements "
                "(id, version_id, ordinal, element_type, text, scene_number, page_number) "
                "VALUES (:id, :version, 1, 'action', 'A camera fills the frame.', 4, 12)"
            ),
            {"id": str(element_id), "version": str(version_id)},
        )
        await session.execute(
            sa.text(
                "INSERT INTO clearance_items "
                "(id, org_id, project_id, script_id, version_id, element_id, category, text, "
                "status, workflow_status, research_status, disposition_status, created_at, version) "
                "VALUES (:id, :org, :project, :script, :version_id, :element, "
                "'products_and_trademarks', 'Vega Camera', 'unresolved', 'detected', "
                "'not_started', 'undisposed', :created, 1)"
            ),
            {
                "id": str(item_id),
                "org": str(org_id),
                "project": str(project_id),
                "script": str(script_id),
                "version_id": str(version_id),
                "element": str(element_id),
                "created": now,
            },
        )
    return DetailFixture(org_id, project_id, item_id, version_id, actor_id)


def _path(fixture: DetailFixture) -> str:
    return (
        f"/api/v1/organizations/{fixture.org_id}/projects/{fixture.project_id}"
        f"/clearance-items/{fixture.item_id}"
    )


async def test_detail_exposes_zero_evidence_as_explicit_unresolved_state() -> None:
    async with await _client() as client:
        fixture = await _fixture(client, "zero")
        response = await client.get(_path(fixture))

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["itemId"] == str(fixture.item_id)
    assert data["projectId"] == str(fixture.project_id)
    assert data["versionId"] == str(fixture.version_id)
    assert data["version"] == 1
    assert data["evidenceState"] == {
        "status": "pending",
        "unresolved": True,
        "claimCount": 0,
        "reason": "Evidence research has not produced cited claims.",
    }
    assert data["claims"] == []
    assert data["snapshots"] == []
    assert data["conflicts"] == []
    assert data["decisions"] == []
    assert data["referrals"] == []
    assert data["comments"] == []
    assert all("explanation" in capability for capability in data["capabilities"])


async def test_detail_projects_persisted_collaboration_and_evidence_history() -> None:
    async with await _client() as client:
        fixture = await _fixture(client, "full")
        now = datetime.now(UTC)
        run_id = uuid6.uuid7()
        snapshot_id = uuid6.uuid7()
        claim_id = uuid6.uuid7()
        conflict_id = uuid6.uuid7()
        evidence_decision_id = uuid6.uuid7()
        disposition_id = uuid6.uuid7()
        referral_id = uuid6.uuid7()
        comment_id = uuid6.uuid7()
        first_revision_id = uuid6.uuid7()
        second_revision_id = uuid6.uuid7()
        mention_id = uuid6.uuid7()

        async with session_scope() as session:
            await session.execute(
                sa.text(
                    "UPDATE clearance_items SET research_status = 'completed', version = 7, "
                    "assigned_to_user_id = :actor WHERE id = :item"
                ),
                {"actor": str(fixture.actor_id), "item": str(fixture.item_id)},
            )
            await session.execute(
                sa.text(
                    "INSERT INTO research_runs (id, org_id, project_id, item_id, status, created_at) "
                    "VALUES (:id, :org, :project, :item, 'completed', :created)"
                ),
                {
                    "id": str(run_id),
                    "org": str(fixture.org_id),
                    "project": str(fixture.project_id),
                    "item": str(fixture.item_id),
                    "created": now,
                },
            )
            await session.execute(
                sa.text(
                    "INSERT INTO source_snapshots "
                    "(id, org_id, project_id, item_id, run_id, url, title, publisher, excerpt, "
                    "origin, sha256_hash, retrieved_at) VALUES "
                    "(:id, :org, :project, :item, :run, 'https://example.com/registry', "
                    "'Registry result', 'Example Registry', 'Registry excerpt', 'search', :hash, :created)"
                ),
                {
                    "id": str(snapshot_id),
                    "org": str(fixture.org_id),
                    "project": str(fixture.project_id),
                    "item": str(fixture.item_id),
                    "run": str(run_id),
                    "hash": "a" * 64,
                    "created": now,
                },
            )
            await session.execute(
                sa.text(
                    "INSERT INTO evidence_claims "
                    "(id, org_id, project_id, item_id, snapshot_id, stance, authority_tier, "
                    "claim_text, provenance_excerpt, created_at) VALUES "
                    "(:id, :org, :project, :item, :snapshot, 'supporting', 'primary', "
                    "'A registry record exists.', 'Registry excerpt', :created)"
                ),
                {
                    "id": str(claim_id),
                    "org": str(fixture.org_id),
                    "project": str(fixture.project_id),
                    "item": str(fixture.item_id),
                    "snapshot": str(snapshot_id),
                    "created": now,
                },
            )
            await session.execute(
                sa.text(
                    "INSERT INTO evidence_conflicts "
                    "(id, org_id, project_id, item_id, description, created_at) "
                    "VALUES (:id, :org, :project, :item, "
                    "'Sources disagree on current status.', :created)"
                ),
                {
                    "id": str(conflict_id),
                    "org": str(fixture.org_id),
                    "project": str(fixture.project_id),
                    "item": str(fixture.item_id),
                    "created": now,
                },
            )
            for record_id, kind, value, expected, resulting in (
                (evidence_decision_id, "evidence", "accepted", 1, 2),
                (disposition_id, "disposition", "deferred", 2, 3),
            ):
                await session.execute(
                    sa.text(
                        "INSERT INTO governed_decision_records "
                        "(id, org_id, project_id, item_id, actor_id, decision_kind, decision_value, "
                        "rationale, expected_version, resulting_version, created_at) VALUES "
                        "(:id, :org, :project, :item, :actor, :kind, :value, 'Human rationale', "
                        ":expected, :resulting, :created)"
                    ),
                    {
                        "id": str(record_id),
                        "org": str(fixture.org_id),
                        "project": str(fixture.project_id),
                        "item": str(fixture.item_id),
                        "actor": str(fixture.actor_id),
                        "kind": kind,
                        "value": value,
                        "expected": expected,
                        "resulting": resulting,
                        "created": now,
                    },
                )
            await session.execute(
                sa.text(
                    "INSERT INTO governed_referrals "
                    "(id, org_id, project_id, item_id, target_role, question, notes, "
                    "submitted_by_actor_id, status, submitted_at, idempotency_key) VALUES "
                    "(:id, :org, :project, :item, 'reviewer', 'Please review.', 'Specialist note', "
                    ":actor, 'submitted', :created, :key)"
                ),
                {
                    "id": str(referral_id),
                    "org": str(fixture.org_id),
                    "project": str(fixture.project_id),
                    "item": str(fixture.item_id),
                    "actor": str(fixture.actor_id),
                    "created": now,
                    "key": f"projection-{uuid4().hex}",
                },
            )
            await session.execute(
                sa.text(
                    "INSERT INTO governed_comments "
                    "(id, org_id, project_id, item_id, author_id, parent_comment_id, "
                    "parent_reply_depth, reply_depth, created_at) VALUES "
                    "(:id, :org, :project, :item, :actor, NULL, NULL, 0, :created)"
                ),
                {
                    "id": str(comment_id),
                    "org": str(fixture.org_id),
                    "project": str(fixture.project_id),
                    "item": str(fixture.item_id),
                    "actor": str(fixture.actor_id),
                    "created": now,
                },
            )
            for revision_id, ordinal, body in (
                (first_revision_id, 1, "Initial review note."),
                (second_revision_id, 2, "Revised review note."),
            ):
                await session.execute(
                    sa.text(
                        "INSERT INTO governed_comment_revisions "
                        "(id, org_id, project_id, comment_id, author_id, ordinal, body, created_at) "
                        "VALUES (:id, :org, :project, :comment, :actor, :ordinal, :body, :created)"
                    ),
                    {
                        "id": str(revision_id),
                        "org": str(fixture.org_id),
                        "project": str(fixture.project_id),
                        "comment": str(comment_id),
                        "actor": str(fixture.actor_id),
                        "ordinal": ordinal,
                        "body": body,
                        "created": now,
                    },
                )
            await session.execute(
                sa.text(
                    "INSERT INTO governed_comment_mentions "
                    "(id, org_id, project_id, comment_id, revision_id, recipient_user_id, created_at) "
                    "VALUES (:id, :org, :project, :comment, :revision, :recipient, :created)"
                ),
                {
                    "id": str(mention_id),
                    "org": str(fixture.org_id),
                    "project": str(fixture.project_id),
                    "comment": str(comment_id),
                    "revision": str(second_revision_id),
                    "recipient": str(fixture.actor_id),
                    "created": now,
                },
            )

        response = await client.get(_path(fixture))

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["version"] == 7
    assert data["assignedTo"] == str(fixture.actor_id)
    assert data["evidenceState"]["status"] == "cited"
    assert data["evidenceState"]["unresolved"] is True
    assert data["evidenceState"]["claimCount"] == 1
    assert data["claims"][0]["claimId"] == str(claim_id)
    assert data["claims"][0]["snapshotId"] == str(snapshot_id)
    assert data["snapshots"][0]["snapshotId"] == str(snapshot_id)
    assert data["conflicts"] == [
        {
            "conflictId": str(conflict_id),
            "description": "Sources disagree on current status.",
            "createdAt": data["conflicts"][0]["createdAt"],
        }
    ]
    assert [(row["kind"], row["value"]) for row in data["decisions"]] == [
        ("evidence", "accepted"),
        ("disposition", "deferred"),
    ]
    assert data["referrals"][0]["referralId"] == str(referral_id)
    assert data["referrals"][0]["status"] == "submitted"
    assert data["comments"][0]["commentId"] == str(comment_id)
    assert [revision["ordinal"] for revision in data["comments"][0]["revisions"]] == [1, 2]
    assert data["comments"][0]["revisions"][1]["mentionRecipientIds"] == [str(fixture.actor_id)]
    capability = {row["action"]: row for row in data["capabilities"]}
    assert capability["item:decide"]["allowed"] is True
    assert capability["item:decide"]["explanation"]


async def test_detail_denies_same_org_reviewer_without_project_grant() -> None:
    async with await _client() as owner, await _client() as reviewer:
        fixture = await _fixture(owner, "grant-denied")
        registration = await reviewer.post(
            "/api/v1/users",
            json={
                "name": "Ungraded Reviewer",
                "email": f"ungranted-{uuid4().hex}@example.com",
                "password": "Password123!",
            },
        )
        assert registration.status_code == 201, registration.text
        reviewer_id = UUID(registration.json()["data"]["userId"])
        membership_id = uuid6.uuid7()
        async with session_scope() as session:
            await session.execute(
                sa.text(
                    "INSERT INTO memberships "
                    "(id, org_id, user_id, role, status, created_at) "
                    "VALUES (:id, :org, :user, 'reviewer', 'active', :created)"
                ),
                {
                    "id": str(membership_id),
                    "org": str(fixture.org_id),
                    "user": str(reviewer_id),
                    "created": datetime.now(UTC),
                },
            )

        denied = await reviewer.get(_path(fixture))

        async with session_scope() as session:
            await session.execute(
                sa.text(
                    "INSERT INTO project_grants "
                    "(id, org_id, project_id, membership_id, granted_at) "
                    "VALUES (:id, :org, :project, :membership, :granted)"
                ),
                {
                    "id": str(uuid6.uuid7()),
                    "org": str(fixture.org_id),
                    "project": str(fixture.project_id),
                    "membership": str(membership_id),
                    "granted": datetime.now(UTC),
                },
            )
        granted = await reviewer.get(_path(fixture))

    assert denied.status_code == 403
    assert granted.status_code == 200, granted.text
    assert granted.json()["data"]["itemId"] == str(fixture.item_id)


async def test_detail_excludes_corrupt_cross_scope_children() -> None:
    if engine.dialect.name != "sqlite":
        pytest.skip("Corrupt ownership fixture requires SQLite foreign-key control.")

    async with await _client() as owner, await _client() as foreign_owner:
        owned = await _fixture(owner, "corrupt-owned")
        foreign = await _fixture(foreign_owner, "corrupt-foreign")
        now = datetime.now(UTC)
        run_id, snapshot_id, claim_id = (uuid6.uuid7() for _ in range(3))
        conflict_id, decision_id, referral_id = (uuid6.uuid7() for _ in range(3))
        comment_id, revision_id = (uuid6.uuid7() for _ in range(2))

        async with engine.connect() as connection:
            await connection.execute(sa.text("PRAGMA foreign_keys=OFF"))
            await connection.commit()
            try:
                await connection.execute(
                    sa.text(
                        "INSERT INTO research_runs "
                        "(id, org_id, project_id, item_id, status, created_at) "
                        "VALUES (:id, :org, :project, :item, 'completed', :created)"
                    ),
                    {
                        "id": str(run_id),
                        "org": str(foreign.org_id),
                        "project": str(foreign.project_id),
                        "item": str(owned.item_id),
                        "created": now,
                    },
                )
                await connection.execute(
                    sa.text(
                        "INSERT INTO source_snapshots "
                        "(id, org_id, project_id, item_id, run_id, url, title, publisher, "
                        "excerpt, origin, sha256_hash, retrieved_at) VALUES "
                        "(:id, :org, :project, :item, :run, 'https://foreign.example/source', "
                        "'Foreign source', 'Foreign publisher', 'Foreign excerpt', 'search', "
                        ":hash, :created)"
                    ),
                    {
                        "id": str(snapshot_id),
                        "org": str(foreign.org_id),
                        "project": str(foreign.project_id),
                        "item": str(owned.item_id),
                        "run": str(run_id),
                        "hash": "f" * 64,
                        "created": now,
                    },
                )
                await connection.execute(
                    sa.text(
                        "INSERT INTO evidence_claims "
                        "(id, org_id, project_id, item_id, snapshot_id, stance, authority_tier, "
                        "claim_text, provenance_excerpt, created_at) VALUES "
                        "(:id, :org, :project, :item, :snapshot, 'context', 'secondary', "
                        "'Foreign claim', 'Foreign excerpt', :created)"
                    ),
                    {
                        "id": str(claim_id),
                        "org": str(foreign.org_id),
                        "project": str(foreign.project_id),
                        "item": str(owned.item_id),
                        "snapshot": str(snapshot_id),
                        "created": now,
                    },
                )
                await connection.execute(
                    sa.text(
                        "INSERT INTO evidence_conflicts "
                        "(id, org_id, project_id, item_id, description, created_at) "
                        "VALUES (:id, :org, :project, :item, 'Foreign conflict', :created)"
                    ),
                    {
                        "id": str(conflict_id),
                        "org": str(foreign.org_id),
                        "project": str(foreign.project_id),
                        "item": str(owned.item_id),
                        "created": now,
                    },
                )
                await connection.execute(
                    sa.text(
                        "INSERT INTO governed_decision_records "
                        "(id, org_id, project_id, item_id, actor_id, decision_kind, "
                        "decision_value, rationale, expected_version, resulting_version, "
                        "created_at) VALUES (:id, :org, :project, :item, :actor, 'evidence', "
                        "'accepted', 'Foreign decision', 1, 2, :created)"
                    ),
                    {
                        "id": str(decision_id),
                        "org": str(foreign.org_id),
                        "project": str(foreign.project_id),
                        "item": str(owned.item_id),
                        "actor": str(foreign.actor_id),
                        "created": now,
                    },
                )
                await connection.execute(
                    sa.text(
                        "INSERT INTO governed_referrals "
                        "(id, org_id, project_id, item_id, target_role, question, notes, "
                        "submitted_by_actor_id, status, submitted_at, idempotency_key) VALUES "
                        "(:id, :org, :project, :item, 'reviewer', 'Foreign referral?', NULL, "
                        ":actor, 'submitted', :created, :key)"
                    ),
                    {
                        "id": str(referral_id),
                        "org": str(foreign.org_id),
                        "project": str(foreign.project_id),
                        "item": str(owned.item_id),
                        "actor": str(foreign.actor_id),
                        "created": now,
                        "key": f"foreign-{uuid4().hex}",
                    },
                )
                await connection.execute(
                    sa.text(
                        "INSERT INTO governed_comments "
                        "(id, org_id, project_id, item_id, author_id, parent_comment_id, "
                        "parent_reply_depth, reply_depth, created_at) VALUES "
                        "(:id, :org, :project, :item, :actor, NULL, NULL, 0, :created)"
                    ),
                    {
                        "id": str(comment_id),
                        "org": str(foreign.org_id),
                        "project": str(foreign.project_id),
                        "item": str(owned.item_id),
                        "actor": str(foreign.actor_id),
                        "created": now,
                    },
                )
                await connection.execute(
                    sa.text(
                        "INSERT INTO governed_comment_revisions "
                        "(id, org_id, project_id, comment_id, author_id, ordinal, body, "
                        "created_at) VALUES (:id, :org, :project, :comment, :actor, 1, "
                        "'Foreign comment', :created)"
                    ),
                    {
                        "id": str(revision_id),
                        "org": str(foreign.org_id),
                        "project": str(foreign.project_id),
                        "comment": str(comment_id),
                        "actor": str(foreign.actor_id),
                        "created": now,
                    },
                )
                await connection.commit()
            finally:
                await connection.execute(sa.text("PRAGMA foreign_keys=ON"))
                await connection.commit()

        response = await owner.get(_path(owned))

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["claims"] == []
    assert data["snapshots"] == []
    assert data["conflicts"] == []
    assert data["decisions"] == []
    assert data["referrals"] == []
    assert data["comments"] == []


async def _detail_statement_count(fixture: DetailFixture) -> int:
    statement_count = 0

    def count_statement(*_args: object) -> None:
        nonlocal statement_count
        statement_count += 1

    event.listen(engine.sync_engine, "before_cursor_execute", count_statement)
    try:
        async with session_scope() as session:
            await SqlItemReadRepository().load_detail(
                session,
                org_id=fixture.org_id,
                project_id=fixture.project_id,
                item_id=fixture.item_id,
                actor_id=fixture.actor_id,
                actor_role="owner",
            )
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", count_statement)
    return statement_count


async def test_detail_query_count_is_independent_of_child_cardinality() -> None:
    async with await _client() as client:
        fixture = await _fixture(client, "bounded-queries")
        empty_count = await _detail_statement_count(fixture)

        now = datetime.now(UTC)
        async with session_scope() as session:
            for index in range(25):
                await session.execute(
                    sa.text(
                        "INSERT INTO evidence_conflicts "
                        "(id, org_id, project_id, item_id, description, created_at) "
                        "VALUES (:id, :org, :project, :item, :description, :created)"
                    ),
                    {
                        "id": str(uuid6.uuid7()),
                        "org": str(fixture.org_id),
                        "project": str(fixture.project_id),
                        "item": str(fixture.item_id),
                        "description": f"Conflict {index}",
                        "created": now,
                    },
                )

        populated_count = await _detail_statement_count(fixture)

    assert empty_count == 7
    assert populated_count == empty_count

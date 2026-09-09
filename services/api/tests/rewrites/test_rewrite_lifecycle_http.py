"""Behavioral tests for the governed rewrite-proposal lifecycle over HTTP.

Defect this pins: the four contract-declared rewrite operations
(``proposeRewrite``, ``approveRewrite``, ``rejectRewrite``, ``withdrawRewrite``)
were called by the shipped UI while no route existed to serve them, and the
service behind them kept proposals in a process-local ``dict``. The core
regression here is therefore persistence and reachability: a proposal made
through the mounted route must be readable afterwards through a *fresh* client
and a *freshly constructed* service instance, which nothing in-memory can pass.

Everything else follows from the governance rules: provenance is read from
authorized server records, maker-checker blocks self-approval, illegal lifecycle
moves and stale source versions are visible conflicts, a replay under one
idempotency key produces no second audit event or second version advance, and an
audit failure rolls the proposal write back with it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
import uuid6
from clearcut.database import session_scope
from clearcut.decisions.adapters.sql_rewrite_repository import SqlRewriteRepository
from clearcut.decisions.application.rewrite_commands import RewriteCommandService
from clearcut.init_db import init_and_seed_db
from clearcut.main import app
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.asyncio

_PASSWORD = "Password123!"
_ORIGINAL_TEXT = "Acme Corporation"


async def _client(*, raise_app_exceptions: bool = True) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=raise_app_exceptions),
        base_url="http://test",
        headers={"origin": "http://test"},
    )


def _idempotency_key(label: str) -> str:
    return f"idem-{label}-{uuid4().hex}"


def _propose_path(org_id: UUID, project_id: UUID, item_id: UUID) -> str:
    return (
        f"/api/v1/organizations/{org_id}/projects/{project_id}"
        f"/clearance-items/{item_id}:proposeRewrite"
    )


def _list_path(org_id: UUID, project_id: UUID, item_id: UUID) -> str:
    return (
        f"/api/v1/organizations/{org_id}/projects/{project_id}"
        f"/clearance-items/{item_id}/rewrite-proposals"
    )


def _transition_path(org_id: UUID, project_id: UUID, proposal_id: UUID, action: str) -> str:
    return (
        f"/api/v1/organizations/{org_id}/projects/{project_id}"
        f"/rewrite-proposals/{proposal_id}:{action}"
    )


@dataclass(frozen=True)
class Fixture:
    org_id: UUID
    project_id: UUID
    script_id: UUID
    version_id: UUID
    element_id: UUID
    item_id: UUID
    actor_id: UUID


async def _register_actor(client: AsyncClient, *, suffix: str) -> UUID:
    registration = await client.post(
        "/api/v1/users",
        json={
            "name": f"Rewrite Actor {suffix}",
            "email": f"rewrite-{suffix}-{uuid4().hex}@example.com",
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
            "name": f"Rewrite Studio {suffix}",
            "slug": f"rewrite-{slug_suffix}-{uuid4().hex[:8]}",
        },
    )
    assert organization.status_code == 201, organization.text
    org_id = UUID(organization.json()["data"]["orgId"])
    project = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        json={"title": f"Rewrite Project {suffix}"},
    )
    assert project.status_code == 201, project.text
    return org_id, UUID(project.json()["data"]["projectId"])


async def _insert_item(*, org_id: UUID, project_id: UUID) -> tuple[UUID, UUID, UUID, UUID]:
    """Seed one script version, element, and clearance item; return their ids."""
    script_id = uuid6.uuid7()
    version_id = uuid6.uuid7()
    element_id = uuid6.uuid7()
    item_id = uuid6.uuid7()
    now = datetime.now(UTC)
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO scripts (id, org_id, project_id, title, created_at) "
                "VALUES (:id, :org_id, :project_id, 'Rewrite test', :created_at)"
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
                "VALUES (:id, :version_id, 1, 'action', :text)"
            ),
            {"id": str(element_id), "version_id": str(version_id), "text": _ORIGINAL_TEXT},
        )
        await session.execute(
            sa.text(
                "INSERT INTO clearance_items "
                "(id, org_id, project_id, script_id, version_id, element_id, category, text, "
                "status, research_status, workflow_status, disposition_status, created_at, "
                "version) VALUES "
                "(:id, :org_id, :project_id, :script_id, :version_id, :element_id, "
                "'products_and_trademarks', :text, 'unresolved', 'completed', "
                "'detected', 'undisposed', :created_at, 1)"
            ),
            {
                "id": str(item_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "script_id": str(script_id),
                "version_id": str(version_id),
                "element_id": str(element_id),
                "text": _ORIGINAL_TEXT,
                "created_at": now,
            },
        )
    return script_id, version_id, element_id, item_id


async def _setup(client: AsyncClient, *, suffix: str) -> Fixture:
    actor_id = await _register_actor(client, suffix=suffix)
    org_id, project_id = await _create_org_and_project(client, suffix=suffix)
    script_id, version_id, element_id, item_id = await _insert_item(
        org_id=org_id, project_id=project_id
    )
    return Fixture(
        org_id=org_id,
        project_id=project_id,
        script_id=script_id,
        version_id=version_id,
        element_id=element_id,
        item_id=item_id,
        actor_id=actor_id,
    )


async def _add_member(*, org_id: UUID, user_id: UUID, role: str) -> None:
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO memberships (id, org_id, user_id, role, status, created_at) "
                "VALUES (:id, :org_id, :user_id, :role, 'active', :created_at)"
            ),
            {
                "id": str(uuid6.uuid7()),
                "org_id": str(org_id),
                "user_id": str(user_id),
                "role": role,
                "created_at": datetime.now(UTC),
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


async def _insert_successor_version(fixture: Fixture, *, ordinal: int = 2) -> UUID:
    version_id = uuid6.uuid7()
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO script_versions "
                "(id, script_id, org_id, project_id, ordinal, source_hash, parser_version, "
                "created_at) VALUES "
                "(:id, :script_id, :org_id, :project_id, :ordinal, :source_hash, 'v1', "
                ":created_at)"
            ),
            {
                "id": str(version_id),
                "script_id": str(fixture.script_id),
                "org_id": str(fixture.org_id),
                "project_id": str(fixture.project_id),
                "ordinal": ordinal,
                "source_hash": "e" * 64,
                "created_at": datetime.now(UTC),
            },
        )
    return version_id


async def _propose(
    client: AsyncClient,
    fixture: Fixture,
    *,
    proposed_text: str = "Novus Corporation",
    rationale: str = "Replace the identifiable mark with a cleared substitute.",
    idempotency_key: str | None = None,
    org_id: UUID | None = None,
    project_id: UUID | None = None,
    item_id: UUID | None = None,
):
    headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
    return await client.post(
        _propose_path(
            org_id or fixture.org_id,
            project_id or fixture.project_id,
            item_id or fixture.item_id,
        ),
        json={"proposedText": proposed_text, "rationale": rationale},
        headers=headers,
    )


async def _transition(
    client: AsyncClient,
    fixture: Fixture,
    proposal_id: UUID,
    action: str,
    *,
    rationale: str | None = None,
    idempotency_key: str | None = None,
    org_id: UUID | None = None,
    project_id: UUID | None = None,
):
    headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
    payload = {"rationale": rationale} if rationale is not None else None
    return await client.post(
        _transition_path(
            org_id or fixture.org_id,
            project_id or fixture.project_id,
            proposal_id,
            action,
        ),
        json=payload,
        headers=headers,
    )


async def _count(query: str, params: dict) -> int:
    async with session_scope() as session:
        return int((await session.execute(sa.text(query), params)).scalar_one())


# --------------------------------------------------------------------------- #
# The core regression: the lifecycle is persisted and reachable.
# --------------------------------------------------------------------------- #


async def test_proposal_survives_a_fresh_client_and_a_fresh_service_instance() -> None:
    """The defect in one test: propose, then read the proposal back from storage.

    The old service kept proposals in ``self.proposals``, so a second client and a
    newly constructed service saw nothing. Both must see the proposal now.
    """
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="persistence")
        created = await _propose(client, fixture)
        assert created.status_code == 201, created.text
        proposal = created.json()["data"]
        token = client.cookies.get("clearcut_session")

    # A brand-new client with the same session reads the proposal back.
    async with await _client() as reloaded:
        reloaded.cookies.set("clearcut_session", token)
        listed = await reloaded.get(_list_path(fixture.org_id, fixture.project_id, fixture.item_id))
    assert listed.status_code == 200, listed.text
    assert [entry["proposalId"] for entry in listed.json()["data"]] == [proposal["proposalId"]]
    assert listed.json()["meta"]["totalCount"] == 1

    # A freshly constructed service instance reads the same row: no process state.
    fresh_service = RewriteCommandService(repository=SqlRewriteRepository())
    async with session_scope() as session:
        persisted = await fresh_service.list_proposals(
            session,
            org_id=fixture.org_id,
            project_id=fixture.project_id,
            item_id=fixture.item_id,
            actor_role="owner",
        )
    assert [str(entry.proposal_id) for entry in persisted] == [proposal["proposalId"]]
    assert persisted[0].proposed_text == "Novus Corporation"


async def test_proposal_provenance_comes_from_the_server_not_the_client() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="provenance")
        created = await _propose(client, fixture)
        # A client cannot smuggle provenance in: unknown fields are refused
        # outright rather than silently ignored.
        smuggled = await client.post(
            _propose_path(fixture.org_id, fixture.project_id, fixture.item_id),
            json={
                "proposedText": "Novus Corporation",
                "originalText": "Something the client made up",
                "sourceVersionId": str(uuid6.uuid7()),
            },
        )

    assert created.status_code == 201, created.text
    data = created.json()["data"]
    # The original text, element, and source version are the server's own record.
    assert data["originalText"] == _ORIGINAL_TEXT
    assert data["elementId"] == str(fixture.element_id)
    assert data["sourceVersionId"] == str(fixture.version_id)
    assert data["proposerId"] == str(fixture.actor_id)
    assert data["status"] == "proposed"
    # Approval has not happened, so nothing is bound to a successor version.
    assert "resultingVersionId" not in data

    assert smuggled.status_code == 422, smuggled.text
    assert smuggled.json()["error"]["code"] == "validation_failed"


async def test_a_proposal_identical_to_the_original_passage_is_refused() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="noop")
        response = await _propose(client, fixture, proposed_text=f"  {_ORIGINAL_TEXT}  ")

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "validation_failed"
    assert (
        await _count(
            "SELECT count(*) FROM rewrite_proposals WHERE item_id = :item_id",
            {"item_id": str(fixture.item_id)},
        )
        == 0
    )


# --------------------------------------------------------------------------- #
# The four transitions and their illegal counterparts.
# --------------------------------------------------------------------------- #


async def test_approve_by_a_second_actor_commits_the_transition_and_one_audit_event() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as proposer, await _client() as approver:
        fixture = await _setup(proposer, suffix="approve")
        approver_id = await _register_actor(approver, suffix="approve-checker")
        await _add_member(org_id=fixture.org_id, user_id=approver_id, role="reviewer")

        created = await _propose(proposer, fixture)
        assert created.status_code == 201, created.text
        proposal_id = UUID(created.json()["data"]["proposalId"])

        approved = await _transition(approver, fixture, proposal_id, "approve")

    assert approved.status_code == 200, approved.text
    data = approved.json()["data"]
    assert data["status"] == "approved"
    assert data["approverId"] == str(approver_id)
    assert data["proposalId"] == str(proposal_id)
    # The item's optimistic version advanced once per governed command.
    assert data["itemVersion"] == 3
    # Approval alone binds no successor version.
    assert "resultingVersionId" not in data

    async with session_scope() as session:
        row = (
            (
                await session.execute(
                    sa.text(
                        "SELECT status, approver_id, resulting_version_id "
                        "FROM rewrite_proposals WHERE id = :id"
                    ),
                    {"id": str(proposal_id)},
                )
            )
            .mappings()
            .one()
        )
    assert str(row["status"]) == "approved"
    assert UUID(str(row["approver_id"])) == approver_id
    assert row["resulting_version_id"] is None

    assert (
        await _count(
            "SELECT count(*) FROM authoritative_audit_events "
            "WHERE target_id = :target AND action = 'rewrite.approved'",
            {"target": str(proposal_id)},
        )
        == 1
    )


async def test_reject_records_the_supplied_reason() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as proposer, await _client() as reviewer:
        fixture = await _setup(proposer, suffix="reject")
        reviewer_id = await _register_actor(reviewer, suffix="reject-checker")
        await _add_member(org_id=fixture.org_id, user_id=reviewer_id, role="reviewer")
        proposal_id = UUID((await _propose(proposer, fixture)).json()["data"]["proposalId"])

        rejected = await _transition(
            reviewer,
            fixture,
            proposal_id,
            "reject",
            rationale="The substitute reads as a different brand.",
        )

    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["data"]["status"] == "rejected"
    assert (
        rejected.json()["data"]["rejectionReason"] == "The substitute reads as a different brand."
    )


async def test_withdraw_is_available_to_the_proposer_and_denied_to_others() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as proposer, await _client() as other:
        fixture = await _setup(proposer, suffix="withdraw")
        other_id = await _register_actor(other, suffix="withdraw-other")
        await _add_member(org_id=fixture.org_id, user_id=other_id, role="admin")
        proposal_id = UUID((await _propose(proposer, fixture)).json()["data"]["proposalId"])

        # Withdrawal is the maker retracting their own suggestion, so another
        # member -- even an admin -- cannot withdraw it for them.
        by_other = await _transition(other, fixture, proposal_id, "withdraw")
        by_proposer = await _transition(proposer, fixture, proposal_id, "withdraw")

    assert by_other.status_code == 403, by_other.text
    assert by_other.json()["error"]["code"] == "permission_denied"
    assert by_proposer.status_code == 200, by_proposer.text
    assert by_proposer.json()["data"]["status"] == "withdrawn"
    assert "approverId" not in by_proposer.json()["data"]


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("approve", "approve"),
        ("reject", "approve"),
        ("approve", "reject"),
        ("withdraw", "approve"),
    ],
)
async def test_a_second_lifecycle_move_is_a_visible_conflict(first: str, second: str) -> None:
    """A repeated or post-decision move is refused, never silently reapplied."""
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as proposer, await _client() as reviewer:
        fixture = await _setup(proposer, suffix=f"conflict-{first}-{second}")
        reviewer_id = await _register_actor(reviewer, suffix=f"checker-{first}-{second}")
        await _add_member(org_id=fixture.org_id, user_id=reviewer_id, role="reviewer")
        proposal_id = UUID((await _propose(proposer, fixture)).json()["data"]["proposalId"])

        # Withdrawal must come from the proposer; every other move from a checker.
        first_client = proposer if first == "withdraw" else reviewer
        first_response = await _transition(first_client, fixture, proposal_id, first)
        assert first_response.status_code == 200, first_response.text
        second_response = await _transition(reviewer, fixture, proposal_id, second)

    assert second_response.status_code == 409, second_response.text
    assert second_response.json()["error"]["code"] == "conflict"
    # Exactly one lifecycle audit event was committed for this proposal.
    assert (
        await _count(
            "SELECT count(*) FROM authoritative_audit_events "
            "WHERE target_id = :target AND action <> 'rewrite.proposed'",
            {"target": str(proposal_id)},
        )
        == 1
    )


async def test_withdraw_after_materialization_is_refused() -> None:
    """A materialized proposal is bound to a shipped version and cannot be undone.

    Materializing an approved rewrite into the successor version is a separate
    accountable step, so the state is seeded here directly; the database's own
    check constraint requires the version binding to exist for that status.
    """
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as proposer, await _client() as reviewer:
        fixture = await _setup(proposer, suffix="materialized")
        reviewer_id = await _register_actor(reviewer, suffix="materialized-checker")
        await _add_member(org_id=fixture.org_id, user_id=reviewer_id, role="reviewer")
        proposal_id = UUID((await _propose(proposer, fixture)).json()["data"]["proposalId"])
        approved = await _transition(reviewer, fixture, proposal_id, "approve")
        assert approved.status_code == 200, approved.text

        successor = await _insert_successor_version(fixture)
        async with session_scope() as session:
            await session.execute(
                sa.text(
                    "UPDATE rewrite_proposals "
                    "SET status = 'materialized', resulting_version_id = :version "
                    "WHERE id = :id"
                ),
                {"version": str(successor), "id": str(proposal_id)},
            )

        withdrawn = await _transition(proposer, fixture, proposal_id, "withdraw")
        listed = await _client()
        async with listed:
            listed.cookies.set("clearcut_session", proposer.cookies.get("clearcut_session"))
            visible = await listed.get(
                _list_path(fixture.org_id, fixture.project_id, fixture.item_id)
            )

    assert withdrawn.status_code == 409, withdrawn.text
    assert withdrawn.json()["error"]["code"] == "conflict"
    # The resulting-version identity is reported once it exists.
    assert visible.status_code == 200, visible.text
    entry = visible.json()["data"][0]
    assert entry["status"] == "materialized"
    assert entry["resultingVersionId"] == str(successor)


async def test_approving_a_proposal_whose_source_version_moved_is_a_conflict() -> None:
    """A stale proposal is surfaced, never silently rebased onto new text."""
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as proposer, await _client() as reviewer:
        fixture = await _setup(proposer, suffix="stale-source")
        reviewer_id = await _register_actor(reviewer, suffix="stale-checker")
        await _add_member(org_id=fixture.org_id, user_id=reviewer_id, role="reviewer")
        proposal_id = UUID((await _propose(proposer, fixture)).json()["data"]["proposalId"])

        # The project commits a newer version of the same script after the rewrite
        # was written, so the passage was reviewed against surroundings the script
        # has moved past.
        await _insert_successor_version(fixture)

        approved = await _transition(reviewer, fixture, proposal_id, "approve")

    assert approved.status_code == 409, approved.text
    assert approved.json()["error"]["code"] == "conflict_stale_version"
    async with session_scope() as session:
        status_value = (
            await session.execute(
                sa.text("SELECT status FROM rewrite_proposals WHERE id = :id"),
                {"id": str(proposal_id)},
            )
        ).scalar_one()
    assert str(status_value) == "proposed"


# --------------------------------------------------------------------------- #
# Maker-checker, capability, and tenant scope.
# --------------------------------------------------------------------------- #


async def test_the_proposer_cannot_approve_their_own_proposal() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        # An owner holds both rewrite:propose and rewrite:approve, so only
        # maker-checker can stop this.
        fixture = await _setup(client, suffix="self-approve")
        proposal_id = UUID((await _propose(client, fixture)).json()["data"]["proposalId"])
        response = await _transition(client, fixture, proposal_id, "approve")

    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "permission_denied"
    async with session_scope() as session:
        status_value = (
            await session.execute(
                sa.text("SELECT status FROM rewrite_proposals WHERE id = :id"),
                {"id": str(proposal_id)},
            )
        ).scalar_one()
    assert str(status_value) == "proposed"
    assert (
        await _count(
            "SELECT count(*) FROM authoritative_audit_events "
            "WHERE target_id = :target AND action = 'rewrite.approved'",
            {"target": str(proposal_id)},
        )
        == 0
    )


async def test_capability_policy_is_the_existing_one() -> None:
    """An editor may propose but not approve; a reviewer may approve but not propose."""
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as editor, await _client() as reviewer:
        fixture = await _setup(editor, suffix="capability")
        await _set_membership_role(org_id=fixture.org_id, user_id=fixture.actor_id, role="editor")
        reviewer_id = await _register_actor(reviewer, suffix="capability-reviewer")
        await _add_member(org_id=fixture.org_id, user_id=reviewer_id, role="reviewer")

        proposed_by_editor = await _propose(editor, fixture)
        assert proposed_by_editor.status_code == 201, proposed_by_editor.text
        proposal_id = UUID(proposed_by_editor.json()["data"]["proposalId"])

        editor_approval = await _transition(editor, fixture, proposal_id, "approve")
        reviewer_proposal = await _propose(reviewer, fixture, proposed_text="Third Wave Corp")
        reviewer_approval = await _transition(reviewer, fixture, proposal_id, "approve")

    assert editor_approval.status_code == 403, editor_approval.text
    assert reviewer_proposal.status_code == 403, reviewer_proposal.text
    assert reviewer_approval.status_code == 200, reviewer_approval.text


async def test_foreign_project_and_foreign_organization_are_neutral_not_found() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client, await _client() as stranger:
        fixture = await _setup(client, suffix="scope-owned")
        proposal_id = UUID((await _propose(client, fixture)).json()["data"]["proposalId"])

        # A second project in the same organization: the actor is fully authorized
        # there, so the only thing hiding the proposal is project scope.
        other_project = await client.post(
            f"/api/v1/organizations/{fixture.org_id}/projects",
            json={"title": "Rewrite Project Elsewhere"},
        )
        assert other_project.status_code == 201, other_project.text
        foreign_project_id = UUID(other_project.json()["data"]["projectId"])

        # A second organization the same actor owns: authorized there too, and the
        # proposal still must not be visible.
        foreign_org_id, foreign_org_project_id = await _create_org_and_project(
            client, suffix="scope-foreign-org"
        )

        through_foreign_project = await _transition(
            client, fixture, proposal_id, "approve", project_id=foreign_project_id
        )
        through_foreign_org = await _transition(
            client,
            fixture,
            proposal_id,
            "approve",
            org_id=foreign_org_id,
            project_id=foreign_org_project_id,
        )
        listed_through_foreign_project = await client.get(
            _list_path(fixture.org_id, foreign_project_id, fixture.item_id)
        )

        # A non-member is stopped at the organization boundary instead, which is
        # the same neutral outcome from the caller's point of view: no signal
        # about whether the proposal exists.
        await _register_actor(stranger, suffix="scope-stranger")
        through_non_member = await _transition(stranger, fixture, proposal_id, "approve")

    for response in (
        through_foreign_project,
        through_foreign_org,
        listed_through_foreign_project,
    ):
        assert response.status_code == 404, response.text
        assert response.json()["error"]["code"] == "not_found"
    assert through_non_member.status_code == 403, through_non_member.text
    assert through_non_member.json()["error"]["code"] == "permission_denied"


async def test_an_unparseable_proposal_id_is_a_neutral_not_found() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="unparseable")
        response = await client.post(
            f"/api/v1/organizations/{fixture.org_id}/projects/{fixture.project_id}"
            f"/rewrite-proposals/not-a-uuid:approve",
        )

    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "not_found"


# --------------------------------------------------------------------------- #
# Idempotency and transactional integrity.
# --------------------------------------------------------------------------- #


async def test_duplicate_approval_under_one_idempotency_key_replays_one_result() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as proposer, await _client() as reviewer:
        fixture = await _setup(proposer, suffix="replay")
        reviewer_id = await _register_actor(reviewer, suffix="replay-checker")
        await _add_member(org_id=fixture.org_id, user_id=reviewer_id, role="reviewer")
        proposal_id = UUID((await _propose(proposer, fixture)).json()["data"]["proposalId"])

        key = _idempotency_key("replay")
        first = await _transition(reviewer, fixture, proposal_id, "approve", idempotency_key=key)
        second = await _transition(reviewer, fixture, proposal_id, "approve", idempotency_key=key)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    # The replay reproduces the original identity and resulting version rather
    # than advancing the item a second time.
    assert second.json()["data"]["proposalId"] == first.json()["data"]["proposalId"]
    assert second.json()["data"]["itemVersion"] == first.json()["data"]["itemVersion"]
    assert first.json()["data"]["itemVersion"] == 3

    assert (
        await _count(
            "SELECT count(*) FROM authoritative_audit_events "
            "WHERE target_id = :target AND action = 'rewrite.approved'",
            {"target": str(proposal_id)},
        )
        == 1
    )
    assert (
        await _count(
            "SELECT version FROM clearance_items WHERE id = :id",
            {"id": str(fixture.item_id)},
        )
        == 3
    )


async def test_replayed_proposal_creates_one_proposal_only() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="propose-replay")
        key = _idempotency_key("propose-replay")
        first = await _propose(client, fixture, idempotency_key=key)
        second = await _propose(client, fixture, idempotency_key=key)

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert second.json()["data"]["proposalId"] == first.json()["data"]["proposalId"]
    assert (
        await _count(
            "SELECT count(*) FROM rewrite_proposals WHERE item_id = :item_id",
            {"item_id": str(fixture.item_id)},
        )
        == 1
    )


async def test_reused_key_with_a_different_intent_is_an_idempotency_conflict() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="intent")
        key = _idempotency_key("intent")
        first = await _propose(
            client, fixture, proposed_text="Novus Corporation", idempotency_key=key
        )
        second = await _propose(
            client, fixture, proposed_text="Third Wave Corp", idempotency_key=key
        )

    assert first.status_code == 201, first.text
    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] == "conflict_idempotency_mismatch"


async def test_audit_failure_rolls_back_the_proposal_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The proposal and its authoritative audit event commit together or not at all."""
    await init_and_seed_db(seed_if_empty=False)

    import clearcut.decisions.application.rewrite_commands as service_module

    class _InjectedAuditError(RuntimeError):
        pass

    async def _boom(*_args: object, **_kwargs: object) -> None:
        raise _InjectedAuditError("injected authoritative audit failure")

    monkeypatch.setattr(service_module, "insert_authoritative_audit", _boom)

    async with await _client(raise_app_exceptions=False) as client:
        fixture = await _setup(client, suffix="audit-rollback")
        response = await _propose(client, fixture)

    assert response.status_code == 500, response.text
    # Nothing partial survived: no proposal, no receipt, and no version advance.
    assert (
        await _count(
            "SELECT count(*) FROM rewrite_proposals WHERE item_id = :item_id",
            {"item_id": str(fixture.item_id)},
        )
        == 0
    )
    assert (
        await _count(
            "SELECT count(*) FROM governed_command_receipts WHERE item_id = :item_id",
            {"item_id": str(fixture.item_id)},
        )
        == 0
    )
    assert (
        await _count(
            "SELECT version FROM clearance_items WHERE id = :id",
            {"id": str(fixture.item_id)},
        )
        == 1
    )


async def test_approval_starts_no_research_and_creates_no_version() -> None:
    """Approval must never spend a paid provider call or fork the script.

    Materializing the rewrite and re-checking the passages it changed stay behind
    the separate explicit ``startSelectiveRescan`` action.
    """
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as proposer, await _client() as reviewer:
        fixture = await _setup(proposer, suffix="no-side-effects")
        reviewer_id = await _register_actor(reviewer, suffix="no-side-effects-checker")
        await _add_member(org_id=fixture.org_id, user_id=reviewer_id, role="reviewer")
        proposal_id = UUID((await _propose(proposer, fixture)).json()["data"]["proposalId"])
        approved = await _transition(reviewer, fixture, proposal_id, "approve")

    assert approved.status_code == 200, approved.text
    assert (
        await _count(
            "SELECT count(*) FROM research_runs WHERE project_id = :project_id",
            {"project_id": str(fixture.project_id)},
        )
        == 0
    )
    assert (
        await _count(
            "SELECT count(*) FROM script_versions WHERE project_id = :project_id",
            {"project_id": str(fixture.project_id)},
        )
        == 1
    )
    assert (
        await _count(
            "SELECT count(*) FROM jobs WHERE project_id = :project_id",
            {"project_id": str(fixture.project_id)},
        )
        == 0
    )

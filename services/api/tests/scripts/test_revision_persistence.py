"""Task 3 — persist full-file uploads as immutable next script versions with diffs.

Proven exclusively through the public import/parse/accept/commit endpoints plus the
scoped adjacent-diff read handler. These tests exercise ordinal allocation, predecessor
and committing-actor provenance, v1 immutability, same-parse-run replay idempotency,
concurrent distinct commits, whole-transaction rollback on injected persistence failure,
neutral cross-scope 404s, and the classified adjacent-diff read.
"""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from clearcut.database import session_scope
from clearcut.init_db import init_and_seed_db
from clearcut.main import app
from httpx import ASGITransport, AsyncClient

V1_TEXT = """Title: Signal Fires

INT. EDIT SUITE - NIGHT

A clean waveform crosses the monitor.

MARA
The source is ours.

EXT. ROOFTOP - DAWN

The city wakes below.
"""

# A full-file revision: one scene heading kept verbatim (unchanged/moved), one action
# line minimally edited (a single trailing character, so the similarity matcher keeps
# lineage as "modified"), one dialogue line unchanged, and a brand-new closing scene.
V2_TEXT = """Title: Signal Fires

INT. EDIT SUITE - NIGHT

A clean waveform crosses the monitors.

MARA
The source is ours.

EXT. ROOFTOP - DAWN

The city wakes below.

INT. ARCHIVE - LATER

Dust settles over the reels.
"""


async def _client() -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"origin": "http://test"},
    )


async def _create_project(client: AsyncClient, suffix: str) -> tuple[str, str, str]:
    registration = await client.post(
        "/api/v1/users",
        json={
            "name": f"Revision User {suffix}",
            "email": f"revision-{suffix}@example.com",
            "password": "Password123!",
        },
    )
    assert registration.status_code == 201, registration.text
    token = client.cookies.get("clearcut_session")
    assert token

    slug = f"revision-{suffix}-{uuid4().hex[:8]}"
    organization = await client.post(
        "/api/v1/organizations",
        json={"name": f"Revision Studio {suffix}", "slug": slug},
    )
    assert organization.status_code == 201, organization.text
    org_id = organization.json()["data"]["orgId"]

    project = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        json={"title": "Signal Fires", "description": "Task 3 revision test"},
    )
    assert project.status_code == 201, project.text
    return org_id, project.json()["data"]["projectId"], token


async def _commit_full_file(
    client: AsyncClient,
    org_id: str,
    project_id: str,
    raw_text: str,
) -> dict:
    """Paste import → parse → accept warnings (if any) → commit; returns the version data."""
    created = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/paste-imports",
        json={"rawText": raw_text, "format": "fountain"},
    )
    assert created.status_code == 201, created.text
    artifact_id = created.json()["data"]["artifactId"]

    parsed = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/import-artifacts/{artifact_id}:parse"
    )
    assert parsed.status_code == 202, parsed.text
    run = parsed.json()["data"]
    run_id = run["runId"]

    if run["warnings"]:
        accepted = await client.post(
            f"/api/v1/organizations/{org_id}/projects/{project_id}/"
            f"parse-runs/{run_id}:acceptWarnings"
        )
        assert accepted.status_code == 200, accepted.text

    committed = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/parse-runs/{run_id}:commitVersion"
    )
    assert committed.status_code == 201, committed.text
    data = committed.json()["data"]
    data["_runId"] = run_id
    return data


@pytest.mark.asyncio
async def test_full_file_v2_is_immutable_next_version_with_predecessor_and_actor() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        org_id, project_id, _token = await _create_project(client, "v2")
        context = await client.get("/api/v1/session-context")
        actor_id = context.json()["data"]["userId"]

        v1 = await _commit_full_file(client, org_id, project_id, V1_TEXT)
        assert v1["ordinal"] == 1
        assert v1["versionNumber"] == 1
        assert v1["predecessorVersionId"] is None
        assert v1["committedByUserId"] == actor_id

        # v1 has no adjacent diff.
        v1_diff = await client.get(
            f"/api/v1/organizations/{org_id}/projects/{project_id}/"
            f"script-versions/{v1['versionId']}/diff"
        )
        assert v1_diff.status_code == 404
        assert v1_diff.json()["error"]["code"] == "not_found"

        v2 = await _commit_full_file(client, org_id, project_id, V2_TEXT)
        assert v2["ordinal"] == 2
        assert v2["versionNumber"] == 2
        assert v2["predecessorVersionId"] == v1["versionId"]
        assert v2["committedByUserId"] == actor_id
        assert v2["scriptId"] == v1["scriptId"]

    # v1 rows are untouched by the v2 commit.
    async with session_scope() as session:
        v1_version = (
            (
                await session.execute(
                    sa.text(
                        "SELECT ordinal, predecessor_version_id, committed_by_actor_id "
                        "FROM script_versions WHERE id = :id"
                    ),
                    {"id": v1["versionId"]},
                )
            )
            .mappings()
            .one()
        )
        assert v1_version["ordinal"] == 1
        assert v1_version["predecessor_version_id"] is None

        v1_elements = (
            await session.execute(
                sa.text("SELECT count(*) FROM script_elements WHERE version_id = :id"),
                {"id": v1["versionId"]},
            )
        ).scalar_one()
        assert v1_elements == v1["elementCount"]

        v2_version = (
            (
                await session.execute(
                    sa.text(
                        "SELECT ordinal, predecessor_version_id, predecessor_ordinal, "
                        "committed_by_actor_id, script_id "
                        "FROM script_versions WHERE id = :id"
                    ),
                    {"id": v2["versionId"]},
                )
            )
            .mappings()
            .one()
        )
        assert v2_version["ordinal"] == 2
        assert str(v2_version["predecessor_version_id"]) == v1["versionId"]
        assert v2_version["predecessor_ordinal"] == 1
        assert str(v2_version["committed_by_actor_id"]) == actor_id
        assert str(v2_version["script_id"]) == v1["scriptId"]

        diff_rows = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM script_diffs "
                    "WHERE org_id = :org_id AND project_id = :project_id "
                    "AND after_version_id = :after"
                ),
                {"org_id": org_id, "project_id": project_id, "after": v2["versionId"]},
            )
        ).scalar_one()
        assert diff_rows == 1

        lineage_rows = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM script_element_lineage "
                    "WHERE org_id = :org_id AND project_id = :project_id "
                    "AND after_version_id = :after"
                ),
                {"org_id": org_id, "project_id": project_id, "after": v2["versionId"]},
            )
        ).scalar_one()
        assert lineage_rows > 0


@pytest.mark.asyncio
async def test_same_parse_run_replay_returns_same_v2_and_one_adjacent_diff() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        org_id, project_id, _token = await _create_project(client, "replay")
        await _commit_full_file(client, org_id, project_id, V1_TEXT)

        created = await client.post(
            f"/api/v1/organizations/{org_id}/projects/{project_id}/paste-imports",
            json={"rawText": V2_TEXT, "format": "fountain"},
        )
        artifact_id = created.json()["data"]["artifactId"]
        parsed = await client.post(
            f"/api/v1/organizations/{org_id}/projects/{project_id}/"
            f"import-artifacts/{artifact_id}:parse"
        )
        run_id = parsed.json()["data"]["runId"]

        first, second = await asyncio.gather(
            client.post(
                f"/api/v1/organizations/{org_id}/projects/{project_id}/"
                f"parse-runs/{run_id}:commitVersion"
            ),
            client.post(
                f"/api/v1/organizations/{org_id}/projects/{project_id}/"
                f"parse-runs/{run_id}:commitVersion"
            ),
        )
        assert first.status_code == 201, first.text
        assert second.status_code == 201, second.text
        assert first.json()["data"]["versionId"] == second.json()["data"]["versionId"]
        assert first.json()["data"]["ordinal"] == 2

    async with session_scope() as session:
        version_count = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM script_versions "
                    "WHERE org_id = :org_id AND project_id = :project_id"
                ),
                {"org_id": org_id, "project_id": project_id},
            )
        ).scalar_one()
        diff_count = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM script_diffs "
                    "WHERE org_id = :org_id AND project_id = :project_id"
                ),
                {"org_id": org_id, "project_id": project_id},
            )
        ).scalar_one()
    assert version_count == 2
    assert diff_count == 1


@pytest.mark.asyncio
async def test_concurrent_distinct_v2_commits_yield_one_winner_and_typed_conflict() -> None:
    await init_and_seed_db(seed_if_empty=False)
    first_revision = V2_TEXT
    second_revision = V2_TEXT.replace("Dust settles over the reels.", "Rain taps the skylight.")
    async with await _client() as client:
        org_id, project_id, _token = await _create_project(client, "concurrent")
        await _commit_full_file(client, org_id, project_id, V1_TEXT)

        first_artifact, second_artifact = await asyncio.gather(
            client.post(
                f"/api/v1/organizations/{org_id}/projects/{project_id}/paste-imports",
                json={"rawText": first_revision, "format": "fountain"},
            ),
            client.post(
                f"/api/v1/organizations/{org_id}/projects/{project_id}/paste-imports",
                json={"rawText": second_revision, "format": "fountain"},
            ),
        )
        first_parse, second_parse = await asyncio.gather(
            client.post(
                f"/api/v1/organizations/{org_id}/projects/{project_id}/"
                f"import-artifacts/{first_artifact.json()['data']['artifactId']}:parse"
            ),
            client.post(
                f"/api/v1/organizations/{org_id}/projects/{project_id}/"
                f"import-artifacts/{second_artifact.json()['data']['artifactId']}:parse"
            ),
        )
        first_run_id = first_parse.json()["data"]["runId"]
        second_run_id = second_parse.json()["data"]["runId"]
        assert first_run_id != second_run_id

        first_commit, second_commit = await asyncio.gather(
            client.post(
                f"/api/v1/organizations/{org_id}/projects/{project_id}/"
                f"parse-runs/{first_run_id}:commitVersion"
            ),
            client.post(
                f"/api/v1/organizations/{org_id}/projects/{project_id}/"
                f"parse-runs/{second_run_id}:commitVersion"
            ),
        )

    responses = (first_commit, second_commit)
    assert sorted(response.status_code for response in responses) == [201, 409]
    loser = next(response for response in responses if response.status_code == 409)
    assert loser.json()["error"]["code"] == "conflict"
    winner = next(response for response in responses if response.status_code == 201)
    assert winner.json()["data"]["ordinal"] == 2

    async with session_scope() as session:
        version_count = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM script_versions "
                    "WHERE org_id = :org_id AND project_id = :project_id"
                ),
                {"org_id": org_id, "project_id": project_id},
            )
        ).scalar_one()
        ordinal_two_count = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM script_versions "
                    "WHERE org_id = :org_id AND project_id = :project_id AND ordinal = 2"
                ),
                {"org_id": org_id, "project_id": project_id},
            )
        ).scalar_one()
    assert version_count == 2
    assert ordinal_two_count == 1


@pytest.mark.asyncio
async def test_injected_diff_lineage_failure_rolls_back_v2_entirely() -> None:
    await init_and_seed_db(seed_if_empty=False)
    from clearcut.scripts.adapters import sql_import_repository as repo_module

    async with await _client() as client:
        org_id, project_id, _token = await _create_project(client, "rollback")
        v1 = await _commit_full_file(client, org_id, project_id, V1_TEXT)

        created = await client.post(
            f"/api/v1/organizations/{org_id}/projects/{project_id}/paste-imports",
            json={"rawText": V2_TEXT, "format": "fountain"},
        )
        artifact_id = created.json()["data"]["artifactId"]
        parsed = await client.post(
            f"/api/v1/organizations/{org_id}/projects/{project_id}/"
            f"import-artifacts/{artifact_id}:parse"
        )
        run_id = parsed.json()["data"]["runId"]

        original = repo_module.SqlImportRepository._insert_diff_and_lineage

        async def boom(*args: object, **kwargs: object) -> None:
            raise RuntimeError("injected diff/lineage persistence failure")

        repo_module.SqlImportRepository._insert_diff_and_lineage = boom  # type: ignore[assignment]
        try:
            with pytest.raises(RuntimeError, match="injected diff/lineage"):
                await client.post(
                    f"/api/v1/organizations/{org_id}/projects/{project_id}/"
                    f"parse-runs/{run_id}:commitVersion"
                )
        finally:
            repo_module.SqlImportRepository._insert_diff_and_lineage = original  # type: ignore[assignment]

    async with session_scope() as session:
        version_count = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM script_versions "
                    "WHERE org_id = :org_id AND project_id = :project_id"
                ),
                {"org_id": org_id, "project_id": project_id},
            )
        ).scalar_one()
        diff_count = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM script_diffs "
                    "WHERE org_id = :org_id AND project_id = :project_id"
                ),
                {"org_id": org_id, "project_id": project_id},
            )
        ).scalar_one()
    # Only v1 survives; no orphaned v2 version and no diff exist after rollback.
    assert version_count == 1
    assert diff_count == 0
    assert v1["ordinal"] == 1


@pytest.mark.asyncio
async def test_adjacent_diff_read_returns_classified_sets() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        org_id, project_id, _token = await _create_project(client, "diff-read")
        await _commit_full_file(client, org_id, project_id, V1_TEXT)
        v2 = await _commit_full_file(client, org_id, project_id, V2_TEXT)

        response = await client.get(
            f"/api/v1/organizations/{org_id}/projects/{project_id}/"
            f"script-versions/{v2['versionId']}/diff"
        )
        assert response.status_code == 200, response.text
        diff = response.json()["data"]

        assert diff["afterVersionId"] == v2["versionId"]
        assert diff["algorithmVersion"] == "element-lineage-v1"

        kinds = {change["changeKind"] for change in diff["changes"]}
        assert kinds <= {"unchanged", "moved", "modified", "added", "removed"}
        # The revision modified an action line and added a new closing scene.
        assert "modified" in kinds
        assert "added" in kinds

        counts = diff["impactCounts"]
        assert counts["modified"] >= 1
        assert counts["added"] >= 2
        assert sum(counts.values()) == len(diff["changes"])

        for change in diff["changes"]:
            assert change["changeKind"] in {
                "unchanged",
                "moved",
                "modified",
                "added",
                "removed",
            }
            if change["changeKind"] in {"added", "removed"}:
                assert change["confidence"] == "unmatched"
            else:
                assert change["confidence"] in {"exact", "contextual", "similar"}


@pytest.mark.asyncio
async def test_adjacent_diff_read_is_project_scoped_and_returns_neutral_404() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as owner_client:
        owner_org_id, owner_project_id, _token = await _create_project(owner_client, "owner")
        await _commit_full_file(owner_client, owner_org_id, owner_project_id, V1_TEXT)
        v2 = await _commit_full_file(owner_client, owner_org_id, owner_project_id, V2_TEXT)

    async with await _client() as other_client:
        other_org_id, other_project_id, _other = await _create_project(other_client, "other")
        denied = await other_client.get(
            f"/api/v1/organizations/{other_org_id}/projects/{other_project_id}/"
            f"script-versions/{v2['versionId']}/diff"
        )
        assert denied.status_code == 404
        assert denied.json()["error"]["code"] == "not_found"

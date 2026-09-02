import asyncio
import hashlib
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from clearcut.database import session_scope
from clearcut.init_db import init_and_seed_db
from clearcut.main import app
from httpx import ASGITransport, AsyncClient

DEMO_SCRIPT = (
    Path(__file__).resolve().parents[4]
    / "demo"
    / "original-screenplay"
    / "clearcut_test.fountain"
)
MAX_SCRIPT_SIZE_BYTES = 25 * 1024 * 1024


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
            "name": f"Import User {suffix}",
            "email": f"import-{suffix}@example.com",
            "password": "Password123!",
        },
    )
    assert registration.status_code == 201, registration.text
    token = client.cookies.get("clearcut_session")
    assert token

    slug = f"import-{suffix}-{uuid4().hex[:8]}"
    organization = await client.post(
        "/api/v1/organizations",
        json={"name": f"Import Studio {suffix}", "slug": slug},
    )
    assert organization.status_code == 201, organization.text
    org_id = organization.json()["data"]["orgId"]

    project = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        json={"title": "Signal Fires Import", "description": "Task 4 import test"},
    )
    assert project.status_code == 201, project.text
    return org_id, project.json()["data"]["projectId"], token


async def _create_capability(
    client: AsyncClient,
    org_id: str,
    project_id: str,
    *,
    filename: str,
    content_type: str,
) -> dict:
    response = await client.post(
        f"/api/v1/organizations/{org_id}/projects/{project_id}/upload-capabilities",
        json={"filename": filename, "contentType": content_type},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


@pytest.mark.asyncio
async def test_multipart_import_persists_accepts_warnings_and_commits_idempotent_v1() -> None:
    await init_and_seed_db(seed_if_empty=False)
    screenplay = DEMO_SCRIPT.read_bytes()
    malformed_line = next(
        line_number
        for line_number, line in enumerate(screenplay.decode().splitlines(), start=1)
        if line.startswith("INT ABANDONED")
    )

    async with await _client() as client:
        org_id, project_id, token = await _create_project(client, "multipart")
        capability = await _create_capability(
            client,
            org_id,
            project_id,
            filename="clearcut_test.fountain",
            content_type="text/plain",
        )

        finalized = await client.post(
            f"/api/v1/organizations/{org_id}/projects/{project_id}/"
            f"import-artifacts/{capability['capabilityId']}:finalize",
            headers={"X-Upload-Nonce": capability["nonce"]},
            files={"file": ("clearcut_test.fountain", screenplay, "text/plain")},
        )
        assert finalized.status_code == 200, finalized.text
        artifact = finalized.json()["data"]
        assert artifact == {
            "artifactId": capability["capabilityId"],
            "projectId": project_id,
            "filename": "clearcut_test.fountain",
            "contentType": "text/plain",
            "sizeBytes": len(screenplay),
            "sha256": hashlib.sha256(screenplay).hexdigest(),
            "status": "ready_to_parse",
            "createdAt": artifact["createdAt"],
        }

        parsed = await client.post(
            f"/api/v1/organizations/{org_id}/projects/{project_id}/"
            f"import-artifacts/{artifact['artifactId']}:parse"
        )
        assert parsed.status_code == 202, parsed.text
        parse_run = parsed.json()["data"]
        assert parse_run["status"] == "succeeded"
        assert parse_run["sceneCount"] == 7
        assert parse_run["elementCount"] > 20
        assert parse_run["warningsAccepted"] is False
        assert parse_run["warnings"] == [
            {
                "code": "possible_scene_heading",
                "line": malformed_line,
                "message": "Possible scene heading is missing a period after INT or EXT.",
            }
        ]

        blocked_commit = await client.post(
            f"/api/v1/organizations/{org_id}/projects/{project_id}/"
            f"parse-runs/{parse_run['runId']}:commitVersion"
        )
        assert blocked_commit.status_code == 409
        assert blocked_commit.json()["error"]["code"] == "conflict"

        accepted, duplicate_acceptance = await asyncio.gather(
            client.post(
                f"/api/v1/organizations/{org_id}/projects/{project_id}/"
                f"parse-runs/{parse_run['runId']}:acceptWarnings"
            ),
            client.post(
                f"/api/v1/organizations/{org_id}/projects/{project_id}/"
                f"parse-runs/{parse_run['runId']}:acceptWarnings"
            ),
        )
        assert accepted.status_code == 200, accepted.text
        assert duplicate_acceptance.status_code == 200, duplicate_acceptance.text
        assert accepted.json()["data"]["warningsAccepted"] is True
        assert accepted.json()["data"]["acceptedAt"]
        assert (
            duplicate_acceptance.json()["data"]["acceptedAt"]
            == accepted.json()["data"]["acceptedAt"]
        )

        committed, duplicate_commit = await asyncio.gather(
            client.post(
                f"/api/v1/organizations/{org_id}/projects/{project_id}/"
                f"parse-runs/{parse_run['runId']}:commitVersion"
            ),
            client.post(
                f"/api/v1/organizations/{org_id}/projects/{project_id}/"
                f"parse-runs/{parse_run['runId']}:commitVersion"
            ),
        )
        assert committed.status_code == 201, committed.text
        assert duplicate_commit.status_code == 201, duplicate_commit.text
        version = committed.json()["data"]
        assert version["versionNumber"] == 1
        assert version["revisionLabel"] == "v1"
        assert version["sceneCount"] == 7
        assert version["elementCount"] == parse_run["elementCount"]
        assert version["sourceArtifactId"] == artifact["artifactId"]
        assert version["parseRunId"] == parse_run["runId"]
        assert duplicate_commit.json()["data"]["versionId"] == version["versionId"]

        script = await client.get(
            f"/api/v1/organizations/{org_id}/projects/{project_id}/script"
        )
        assert script.status_code == 200, script.text
        projection = script.json()["data"]
        assert projection["title"] == "Signal Fires"
        assert projection["version"] == "v1"
        assert projection["versionId"] == version["versionId"]
        assert len(projection["scenes"]) == 7
        assert projection["scenes"][0]["slug"] == "EXT. GRIFFITH OBSERVATORY - PRE-DAWN"
        assert projection["scenes"][0]["page"] is None
        assert projection["scenes"][-1]["slug"] == "EXT. ROOFTOP - DAWN"

        version_detail = await client.get(
            f"/api/v1/organizations/{org_id}/projects/{project_id}/"
            f"script-versions/{version['versionId']}"
        )
        assert version_detail.status_code == 200
        assert version_detail.json()["data"] == version

    async with session_scope() as session:
        artifact_row = (
            await session.execute(
                sa.text(
                    "SELECT storage_path FROM import_artifacts "
                    "WHERE id = :artifact_id AND org_id = :org_id AND project_id = :project_id"
                ),
                {
                    "artifact_id": artifact["artifactId"],
                    "org_id": org_id,
                    "project_id": project_id,
                },
            )
        ).mappings().one()
        version_count = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM script_versions "
                    "WHERE org_id = :org_id AND project_id = :project_id"
                ),
                {"org_id": org_id, "project_id": project_id},
            )
        ).scalar_one()
        element_count = (
            await session.execute(
                sa.text("SELECT count(*) FROM script_elements WHERE version_id = :version_id"),
                {"version_id": version["versionId"]},
            )
        ).scalar_one()
        acceptance_count = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM parse_warning_acceptances WHERE run_id = :run_id"
                ),
                {"run_id": parse_run["runId"]},
            )
        ).scalar_one()

    assert version_count == 1
    assert element_count == parse_run["elementCount"]
    assert acceptance_count == 1
    storage = app.state.storage
    reloaded_storage = type(storage)(storage.root)
    assert await reloaded_storage.get_object(artifact_row["storage_path"]) == screenplay

    async with await _client() as reloaded_client:
        reloaded_client.cookies.set("clearcut_session", token)
        persisted = await reloaded_client.get(
            f"/api/v1/organizations/{org_id}/projects/{project_id}/script"
        )
    assert persisted.status_code == 200
    assert persisted.json()["data"]["scenes"] == projection["scenes"]


@pytest.mark.asyncio
async def test_paste_import_persists_and_commits_without_warning_acceptance() -> None:
    await init_and_seed_db(seed_if_empty=False)
    raw_text = """Title: Quiet Signal

INT. EDIT SUITE - NIGHT

A clean waveform crosses the monitor.

MARA
The source is ours.
"""
    async with await _client() as client:
        org_id, project_id, _token = await _create_project(client, "paste")
        created = await client.post(
            f"/api/v1/organizations/{org_id}/projects/{project_id}/paste-imports",
            json={"rawText": raw_text, "format": "fountain"},
        )
        assert created.status_code == 201, created.text
        artifact = created.json()["data"]
        assert artifact["sizeBytes"] == len(raw_text.encode())
        assert artifact["sha256"] == hashlib.sha256(raw_text.encode()).hexdigest()

        first_parse, second_parse = await asyncio.gather(
            client.post(
                f"/api/v1/organizations/{org_id}/projects/{project_id}/"
                f"import-artifacts/{artifact['artifactId']}:parse"
            ),
            client.post(
                f"/api/v1/organizations/{org_id}/projects/{project_id}/"
                f"import-artifacts/{artifact['artifactId']}:parse"
            ),
        )
        assert first_parse.status_code == 202
        assert second_parse.status_code == 202
        assert first_parse.json()["data"]["runId"] == second_parse.json()["data"]["runId"]
        assert first_parse.json()["data"]["warnings"] == []

        committed = await client.post(
            f"/api/v1/organizations/{org_id}/projects/{project_id}/"
            f"parse-runs/{first_parse.json()['data']['runId']}:commitVersion"
        )
        assert committed.status_code == 201, committed.text

        script = await client.get(
            f"/api/v1/organizations/{org_id}/projects/{project_id}/script"
        )
        assert script.status_code == 200
        assert script.json()["data"]["title"] == "Quiet Signal"
        assert script.json()["data"]["scenes"][0]["slug"] == "INT. EDIT SUITE - NIGHT"


@pytest.mark.asyncio
async def test_upload_rejects_spoofed_oversized_and_mismatched_content() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        org_id, project_id, _token = await _create_project(client, "validation")

        pdf_capability = await _create_capability(
            client,
            org_id,
            project_id,
            filename="screenplay.pdf",
            content_type="application/pdf",
        )
        spoofed = await client.post(
            f"/api/v1/organizations/{org_id}/projects/{project_id}/"
            f"import-artifacts/{pdf_capability['capabilityId']}:finalize",
            headers={"X-Upload-Nonce": pdf_capability["nonce"]},
            files={"file": ("screenplay.pdf", b"not a pdf", "application/pdf")},
        )
        assert spoofed.status_code == 415
        assert spoofed.json()["error"]["code"] == "validation_failed"

        unsupported_pdf = await client.post(
            f"/api/v1/organizations/{org_id}/projects/{project_id}/"
            f"import-artifacts/{pdf_capability['capabilityId']}:finalize",
            headers={"X-Upload-Nonce": pdf_capability["nonce"]},
            files={"file": ("screenplay.pdf", b"%PDF-1.7 screenplay", "application/pdf")},
        )
        assert unsupported_pdf.status_code == 415
        assert unsupported_pdf.json()["error"]["code"] == "validation_failed"

        text_capability = await _create_capability(
            client,
            org_id,
            project_id,
            filename="latin-1.fountain",
            content_type="text/plain",
        )
        non_utf8 = await client.post(
            f"/api/v1/organizations/{org_id}/projects/{project_id}/"
            f"import-artifacts/{text_capability['capabilityId']}:finalize",
            headers={"X-Upload-Nonce": text_capability["nonce"]},
            files={"file": ("latin-1.fountain", b"EXT. CAF\xc9 - DAY", "text/plain")},
        )
        assert non_utf8.status_code == 415
        assert non_utf8.json()["error"]["code"] == "validation_failed"

        fountain_capability = await _create_capability(
            client,
            org_id,
            project_id,
            filename="large.fountain",
            content_type="text/plain",
        )
        oversized = await client.post(
            f"/api/v1/organizations/{org_id}/projects/{project_id}/"
            f"import-artifacts/{fountain_capability['capabilityId']}:finalize",
            headers={"X-Upload-Nonce": fountain_capability["nonce"]},
            files={
                "file": (
                    "large.fountain",
                    b"A" * (MAX_SCRIPT_SIZE_BYTES + 1),
                    "text/plain",
                )
            },
        )
        assert oversized.status_code == 413
        assert oversized.json()["error"]["code"] == "validation_failed"

        headingless = await client.post(
            f"/api/v1/organizations/{org_id}/projects/{project_id}/paste-imports",
            json={"rawText": "A paragraph without a scene heading.", "format": "fountain"},
        )
        assert headingless.status_code == 201
        headingless_parse = await client.post(
            f"/api/v1/organizations/{org_id}/projects/{project_id}/"
            f"import-artifacts/{headingless.json()['data']['artifactId']}:parse"
        )
        assert headingless_parse.status_code == 422
        assert headingless_parse.json()["error"]["code"] == "validation_failed"

        empty_paste = await client.post(
            f"/api/v1/organizations/{org_id}/projects/{project_id}/paste-imports",
            json={"rawText": "", "format": "fountain"},
        )
        assert empty_paste.status_code == 422
        assert empty_paste.json()["error"]["code"] == "validation_failed"


@pytest.mark.asyncio
async def test_import_artifacts_and_parse_runs_are_project_scoped() -> None:
    await init_and_seed_db(seed_if_empty=False)
    screenplay = DEMO_SCRIPT.read_bytes()
    async with await _client() as owner_client:
        owner_org_id, owner_project_id, _owner_token = await _create_project(
            owner_client, "owner"
        )
        capability = await _create_capability(
            owner_client,
            owner_org_id,
            owner_project_id,
            filename="clearcut_test.fountain",
            content_type="text/plain",
        )
        finalized = await owner_client.post(
            f"/api/v1/organizations/{owner_org_id}/projects/{owner_project_id}/"
            f"import-artifacts/{capability['capabilityId']}:finalize",
            headers={"X-Upload-Nonce": capability["nonce"]},
            files={"file": ("clearcut_test.fountain", screenplay, "text/plain")},
        )
        assert finalized.status_code == 200
        artifact_id = finalized.json()["data"]["artifactId"]

    async with await _client() as other_client:
        other_org_id, other_project_id, _other_token = await _create_project(
            other_client, "other"
        )
        denied = await other_client.post(
            f"/api/v1/organizations/{other_org_id}/projects/{other_project_id}/"
            f"import-artifacts/{artifact_id}:parse"
        )
        assert denied.status_code == 404
        assert denied.json()["error"]["code"] == "not_found"



@pytest.mark.asyncio
async def test_concurrent_finalize_preserves_the_winning_object_when_cleanup_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import clearcut.scripts.application.import_script as import_script_module
    from clearcut.scripts.adapters.filesystem_storage import FilesystemObjectStorage
    from clearcut.scripts.adapters.sql_import_repository import SqlImportRepository
    from clearcut.scripts.application.import_script import (
        ImportConflictError,
        ImportScriptService,
    )

    recorded_warnings: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def record_warning(*args: object, **kwargs: object) -> None:
        recorded_warnings.append((args, kwargs))

    monkeypatch.setattr(import_script_module.logger, "warning", record_warning)

    class BarrierStorage(FilesystemObjectStorage):
        def __init__(self, root: Path) -> None:
            super().__init__(root)
            self._arrivals = 0
            self._lock = asyncio.Lock()
            self._both_written = asyncio.Event()
            self.cleanup_attempts = 0

        async def put_object(self, path: str, data: bytes, content_type: str) -> None:
            await super().put_object(path, data, content_type)
            async with self._lock:
                self._arrivals += 1
                if self._arrivals == 2:
                    self._both_written.set()
            await self._both_written.wait()

        async def delete_object(self, path: str) -> None:
            self.cleanup_attempts += 1
            raise OSError("simulated staged-object cleanup failure")

    screenplay = DEMO_SCRIPT.read_bytes()
    async with await _client() as client:
        org_id_text, project_id_text, _token = await _create_project(client, "race")
        context = await client.get("/api/v1/session-context")
        actor_id = context.json()["data"]["userId"]

    org_id = UUID(org_id_text)
    project_id = UUID(project_id_text)
    storage = BarrierStorage(tmp_path / "race-storage")
    repository = SqlImportRepository()
    service = ImportScriptService(repository=repository, storage=storage)
    capability = await service.create_upload_capability(
        org_id=org_id,
        project_id=project_id,
        actor_id=UUID(actor_id),
        filename="clearcut_test.fountain",
        content_type="text/plain",
    )

    async def finalize():
        return await service.finalize_upload(
            org_id=org_id,
            project_id=project_id,
            actor_id=UUID(actor_id),
            capability_id=capability.capability_id,
            nonce=capability.nonce,
            filename="clearcut_test.fountain",
            content_type="text/plain",
            data=screenplay,
        )

    results = await asyncio.gather(finalize(), finalize(), return_exceptions=True)
    assert sum(not isinstance(result, Exception) for result in results) == 1
    assert sum(isinstance(result, ImportConflictError) for result in results) == 1
    assert storage.cleanup_attempts == 1
    assert len(recorded_warnings) == 1
    warning_args, warning_kwargs = recorded_warnings[0]
    assert "Failed to delete staged import object" in str(warning_args[0])
    assert capability.capability_id in warning_args
    assert warning_kwargs == {"exc_info": True}

    artifact = await repository.get_artifact(
        org_id, project_id, capability.capability_id
    )
    assert artifact is not None
    assert await storage.get_object(artifact.storage_path) == screenplay


@pytest.mark.asyncio
async def test_capability_expiry_is_enforced_at_atomic_consume(tmp_path: Path) -> None:
    from datetime import UTC, datetime, timedelta

    from clearcut.scripts.adapters.filesystem_storage import FilesystemObjectStorage
    from clearcut.scripts.adapters.sql_import_repository import SqlImportRepository
    from clearcut.scripts.application.import_script import (
        ImportConflictError,
        ImportScriptService,
    )

    class ExpiringStorage(FilesystemObjectStorage):
        def __init__(self, root: Path, capability_id: UUID) -> None:
            super().__init__(root)
            self._capability_id = capability_id

        async def put_object(self, path: str, data: bytes, content_type: str) -> None:
            await super().put_object(path, data, content_type)
            async with session_scope() as session:
                await session.execute(
                    sa.text(
                        "UPDATE import_upload_capabilities SET expires_at = :expired "
                        "WHERE id = :capability_id"
                    ),
                    {
                        "expired": datetime.now(UTC) - timedelta(seconds=1),
                        "capability_id": str(self._capability_id),
                    },
                )

    screenplay = DEMO_SCRIPT.read_bytes()
    async with await _client() as client:
        org_id_text, project_id_text, _token = await _create_project(client, "expiry")
        context = await client.get("/api/v1/session-context")
        actor_id = UUID(context.json()["data"]["userId"])

    org_id = UUID(org_id_text)
    project_id = UUID(project_id_text)
    repository = SqlImportRepository()
    bootstrap_storage = FilesystemObjectStorage(tmp_path / "expiry-storage")
    bootstrap_service = ImportScriptService(
        repository=repository,
        storage=bootstrap_storage,
    )
    capability = await bootstrap_service.create_upload_capability(
        org_id=org_id,
        project_id=project_id,
        actor_id=actor_id,
        filename="clearcut_test.fountain",
        content_type="text/plain",
    )
    storage = ExpiringStorage(bootstrap_storage.root, capability.capability_id)
    service = ImportScriptService(repository=repository, storage=storage)

    with pytest.raises(ImportConflictError, match="expired"):
        await service.finalize_upload(
            org_id=org_id,
            project_id=project_id,
            actor_id=actor_id,
            capability_id=capability.capability_id,
            nonce=capability.nonce,
            filename="clearcut_test.fountain",
            content_type="text/plain",
            data=screenplay,
        )

    assert await repository.get_artifact(
        org_id, project_id, capability.capability_id
    ) is None



@pytest.mark.asyncio
async def test_distinct_parse_runs_compete_for_one_version_one() -> None:
    await init_and_seed_db(seed_if_empty=False)
    first_text = """Title: First Candidate

INT. EDIT SUITE - NIGHT

The first candidate waits.
"""
    second_text = """Title: Second Candidate

EXT. STUDIO LOT - DAWN

The second candidate waits.
"""

    async with await _client() as client:
        org_id, project_id, _token = await _create_project(client, "competing-runs")

        first_artifact, second_artifact = await asyncio.gather(
            client.post(
                f"/api/v1/organizations/{org_id}/projects/{project_id}/paste-imports",
                json={"rawText": first_text, "format": "fountain"},
            ),
            client.post(
                f"/api/v1/organizations/{org_id}/projects/{project_id}/paste-imports",
                json={"rawText": second_text, "format": "fountain"},
            ),
        )
        assert first_artifact.status_code == 201, first_artifact.text
        assert second_artifact.status_code == 201, second_artifact.text

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
        assert first_parse.status_code == 202, first_parse.text
        assert second_parse.status_code == 202, second_parse.text
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
    winner = next(response for response in responses if response.status_code == 201)
    loser = next(response for response in responses if response.status_code == 409)
    assert loser.json()["error"]["code"] == "conflict"
    winner_version = winner.json()["data"]
    winner_run_id = winner_version["parseRunId"]
    assert winner_run_id in {first_run_id, second_run_id}

    async with session_scope() as session:
        persisted_versions = (
            await session.execute(
                sa.text(
                    "SELECT id, parse_run_id FROM script_versions "
                    "WHERE org_id = :org_id AND project_id = :project_id"
                ),
                {"org_id": org_id, "project_id": project_id},
            )
        ).mappings().all()
        current_scripts = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM scripts "
                    "WHERE org_id = :org_id AND project_id = :project_id "
                    "AND current_slot = 'current'"
                ),
                {"org_id": org_id, "project_id": project_id},
            )
        ).scalar_one()

    assert persisted_versions == [
        {"id": winner_version["versionId"], "parse_run_id": winner_run_id}
    ]
    assert current_scripts == 1



@pytest.mark.asyncio
async def test_parse_rejects_stored_bytes_that_no_longer_match_artifact_hash() -> None:
    await init_and_seed_db(seed_if_empty=False)
    screenplay = DEMO_SCRIPT.read_bytes()

    async with await _client() as client:
        org_id, project_id, _token = await _create_project(client, "integrity")
        capability = await _create_capability(
            client,
            org_id,
            project_id,
            filename="clearcut_test.fountain",
            content_type="text/plain",
        )
        finalized = await client.post(
            f"/api/v1/organizations/{org_id}/projects/{project_id}/"
            f"import-artifacts/{capability['capabilityId']}:finalize",
            headers={"X-Upload-Nonce": capability["nonce"]},
            files={"file": ("clearcut_test.fountain", screenplay, "text/plain")},
        )
        assert finalized.status_code == 200, finalized.text

        async with session_scope() as session:
            storage_path = (
                await session.execute(
                    sa.text(
                        "SELECT storage_path FROM import_artifacts "
                        "WHERE id = :artifact_id AND org_id = :org_id "
                        "AND project_id = :project_id"
                    ),
                    {
                        "artifact_id": capability["capabilityId"],
                        "org_id": org_id,
                        "project_id": project_id,
                    },
                )
            ).scalar_one()

        corrupted = screenplay.replace(b"Signal Fires", b"Signal Fakes", 1)
        assert corrupted != screenplay
        assert len(corrupted) == len(screenplay)
        await app.state.storage.put_object(storage_path, corrupted, "text/plain")

        parsed = await client.post(
            f"/api/v1/organizations/{org_id}/projects/{project_id}/"
            f"import-artifacts/{capability['capabilityId']}:parse"
        )

    assert parsed.status_code == 503, parsed.text
    assert parsed.json()["error"]["code"] == "capability_unavailable"
    assert parsed.json()["error"]["retryable"] is True
    assert "integrity verification" in parsed.json()["error"]["message"]

    async with session_scope() as session:
        parse_run_count = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM parse_runs "
                    "WHERE artifact_id = :artifact_id AND org_id = :org_id "
                    "AND project_id = :project_id"
                ),
                {
                    "artifact_id": capability["capabilityId"],
                    "org_id": org_id,
                    "project_id": project_id,
                },
            )
        ).scalar_one()
        version_count = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM script_versions "
                    "WHERE org_id = :org_id AND project_id = :project_id"
                ),
                {"org_id": org_id, "project_id": project_id},
            )
        ).scalar_one()

    assert parse_run_count == 0
    assert version_count == 0

import json
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
import uuid6
from clearcut.database import is_sqlite, session_scope
from clearcut.detection.adapters.hermetic_runtime import HermeticDetectionRuntime
from clearcut.detection.runtime_provider import get_detection_runtime
from clearcut.init_db import init_and_seed_db
from clearcut.main import app
from clearcut.operations.application.local_dispatcher import LocalJobDispatcher
from httpx import ASGITransport, AsyncClient


async def _auth_org_project(client: AsyncClient) -> tuple[str, str]:
    reg = await client.post(
        "/api/v1/users",
        json={"name": "Detector", "email": "detect@studio.com", "password": "Password123!"},
    )
    assert reg.status_code == 201
    session_cookie = reg.cookies.get("__Host-clearcut_session")
    if session_cookie is not None:
        client.cookies.set("__Host-clearcut_session", session_cookie)
    org = await client.post("/api/v1/organizations", json={"name": "Det Studio", "slug": "det-studio"})
    org_id = org.json()["data"]["orgId"]
    proj = await client.post(f"/api/v1/organizations/{org_id}/projects", json={"title": "Det Project"})
    return org_id, proj.json()["data"]["projectId"]


async def _insert_version(org_id: str, proj_id: str) -> str:
    now = datetime.now(UTC)
    script_id = uuid6.uuid7()
    version_id = uuid6.uuid7()
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO scripts "
                "(id, org_id, project_id, title, current_slot, created_at) "
                "VALUES (:id, :org, :proj, 'Detection test', 'current', :created)"
            ),
            {"id": str(script_id), "org": org_id, "proj": proj_id, "created": now},
        )
        await session.execute(
            sa.text(
                "INSERT INTO script_versions "
                "(id, org_id, project_id, script_id, ordinal, source_hash, parser_version, created_at) "
                "VALUES (:id, :org, :proj, :sid, 1, 'h', '1', :created)"
            ),
            {
                "id": str(version_id),
                "org": org_id,
                "proj": proj_id,
                "sid": str(script_id),
                "created": now,
            },
        )
    return str(version_id)


@pytest.mark.asyncio
async def test_start_detection_persists_canonical_job_and_authoritative_audit():
    await init_and_seed_db()
    original_dispatcher = app.state.job_dispatcher
    app.state.job_dispatcher = LocalJobDispatcher(
        runner=app.state.job_runner,
        mode="disabled",
        worker_count=None,
    )
    app.dependency_overrides[get_detection_runtime] = lambda: HermeticDetectionRuntime()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers={"origin": "http://test"}
        ) as client:
            org_id, proj_id = await _auth_org_project(client)
            version_id = await _insert_version(org_id, proj_id)

            versions = await client.get(
                f"/api/v1/organizations/{org_id}/projects/{proj_id}/script-versions"
            )
            assert versions.status_code == 200, versions.text
            listed_version = versions.json()["data"][0]
            assert {
                "versionId",
                "projectId",
                "versionNumber",
                "revisionLabel",
                "createdAt",
            } <= set(listed_version)
            assert listed_version["versionId"] == version_id
            assert listed_version["projectId"] == proj_id
            assert listed_version["versionNumber"] == 1
            assert listed_version["revisionLabel"] == "v1"
            assert versions.json()["meta"]["requestId"]
            assert versions.json()["meta"]["totalCount"] == 1

            first = await client.post(
                f"/api/v1/organizations/{org_id}/projects/{proj_id}/script-versions/{version_id}:detect"
            )
            second = await client.post(
                f"/api/v1/organizations/{org_id}/projects/{proj_id}/script-versions/{version_id}:detect"
            )
            assert first.status_code == 202, first.text
            assert second.status_code == 202, second.text
            data = first.json()["data"]
            assert first.json()["meta"]["requestId"]
            assert second.json()["meta"]["requestId"]
            assert second.json()["data"]["jobId"] == data["jobId"]

            async with session_scope() as session:
                job = (
                    await session.execute(
                        sa.text("SELECT * FROM jobs WHERE id = :id"), {"id": data["jobId"]}
                    )
                ).mappings().one()
                payload = job["payload"]
                if isinstance(payload, str):
                    payload = json.loads(payload)
                assert job["job_type"] == "detection"
                assert job["status"] == job["stage"] == "queued"
                assert job["idempotency_key"] == f"detection:{version_id}"
                assert payload == {
                    "schemaVersion": 1,
                    "target": {"type": "script_version", "id": version_id},
                }
                assert job["progress"] == 0
                assert job["attempt_count"] == 0
                assert job["actor_id"] and job["correlation_id"]
                assert job["available_at"] and job["updated_at"]
                assert job["lease_owner"] is None and job["lease_expires_at"] is None

                audit = (
                    await session.execute(
                        sa.text(
                            "SELECT actor_id, correlation_id, payload_redacted "
                            "FROM authoritative_audit_events "
                            "WHERE org_id = :org AND project_id = :proj "
                            "AND action = 'detection.started' AND target_id = :target"
                        ),
                        {"org": org_id, "proj": proj_id, "target": version_id},
                    )
                ).mappings().one()
                audit_payload = audit["payload_redacted"]
                if isinstance(audit_payload, str):
                    audit_payload = json.loads(audit_payload)
                assert str(audit["actor_id"]) == str(job["actor_id"])
                assert str(audit["correlation_id"]) == str(job["correlation_id"])
                assert audit_payload["jobId"] == str(job["id"])
                assert audit_payload["correlationId"] == str(job["correlation_id"])
    finally:
        app.dependency_overrides.pop(get_detection_runtime, None)
        app.state.job_dispatcher = original_dispatcher


@pytest.mark.asyncio
async def test_start_detection_returns_503_when_runtime_not_configured():
    await init_and_seed_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"origin": "http://test"}
    ) as client:
        org_id, proj_id = await _auth_org_project(client)
        version_id = await _insert_version(org_id, proj_id)
        res = await client.post(
            f"/api/v1/organizations/{org_id}/projects/{proj_id}/script-versions/{version_id}:detect"
        )
        assert res.status_code == 503
        assert res.json()["error"]["code"] == "capability_unavailable"
        assert res.headers["x-request-id"]


@pytest.mark.asyncio
async def test_start_detection_rejects_cross_tenant_version():
    await init_and_seed_db()
    app.dependency_overrides[get_detection_runtime] = lambda: HermeticDetectionRuntime()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers={"origin": "http://test"}
        ) as client:
            org_id, proj_id = await _auth_org_project(client)
            foreign_version = uuid6.uuid7()
            res = await client.post(
                f"/api/v1/organizations/{org_id}/projects/{proj_id}/script-versions/{foreign_version}:detect"
            )
            assert res.status_code == 404
            assert res.json()["error"]["code"] == "not_found"
            assert res.headers["x-request-id"]
    finally:
        app.dependency_overrides.pop(get_detection_runtime, None)



@pytest.mark.asyncio
@pytest.mark.skipif(not is_sqlite, reason="SQLite trigger simulates authoritative audit failure")
async def test_start_detection_rolls_back_job_when_authoritative_audit_fails():
    await init_and_seed_db()
    app.dependency_overrides[get_detection_runtime] = lambda: HermeticDetectionRuntime()
    trigger_name = "fail_detection_audit_insert"
    try:
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers={"origin": "http://test"}
        ) as client:
            org_id, proj_id = await _auth_org_project(client)
            version_id = await _insert_version(org_id, proj_id)
            async with session_scope() as session:
                await session.execute(
                    sa.text(
                        f"CREATE TRIGGER {trigger_name} BEFORE INSERT ON authoritative_audit_events "
                        "BEGIN SELECT RAISE(ABORT, 'simulated audit failure'); END"
                    )
                )

            response = await client.post(
                f"/api/v1/organizations/{org_id}/projects/{proj_id}/"
                f"script-versions/{version_id}:detect"
            )
            assert response.status_code == 500
            assert response.headers["content-type"] == "application/json"
            request_id = response.headers["x-request-id"]
            assert response.json() == {
                "error": {
                    "code": "internal_error",
                    "message": "An internal error prevented the request from completing.",
                    "requestId": request_id,
                    "retryable": True,
                }
            }

            async with session_scope() as session:
                job_count = (
                    await session.execute(
                        sa.text(
                            "SELECT count(*) FROM jobs WHERE org_id = :org AND project_id = :proj "
                            "AND idempotency_key = :key"
                        ),
                        {
                            "org": org_id,
                            "proj": proj_id,
                            "key": f"detection:{version_id}",
                        },
                    )
                ).scalar_one()
                assert job_count == 0
    finally:
        async with session_scope() as session:
            await session.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger_name}"))
        app.dependency_overrides.pop(get_detection_runtime, None)

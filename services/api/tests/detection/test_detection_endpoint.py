from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
import uuid6
from httpx import ASGITransport, AsyncClient

from clearcut.database import session_scope
from clearcut.detection.adapters.hermetic_runtime import HermeticDetectionRuntime
from clearcut.detection.runtime_provider import get_detection_runtime
from clearcut.init_db import init_and_seed_db
from clearcut.main import app


async def _auth_org_project(client: AsyncClient) -> tuple[str, str]:
    reg = await client.post(
        "/api/v1/users",
        json={"name": "Detector", "email": "detect@studio.com", "password": "Password123!"},
    )
    assert reg.status_code == 201
    client.cookies.set("__Host-clearcut_session", reg.cookies.get("__Host-clearcut_session"))
    org = await client.post("/api/v1/organizations", json={"name": "Det Studio", "slug": "det-studio"})
    org_id = org.json()["data"]["orgId"]
    proj = await client.post(f"/api/v1/organizations/{org_id}/projects", json={"title": "Det Project"})
    return org_id, proj.json()["data"]["projectId"]


@pytest.mark.asyncio
async def test_start_detection_persists_job_and_audit_when_runtime_injected():
    await init_and_seed_db()
    # Hermetic runtime is injected ONLY in tests — never selectable in production.
    app.dependency_overrides[get_detection_runtime] = lambda: HermeticDetectionRuntime()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers={"origin": "http://test"}
        ) as client:
            org_id, proj_id = await _auth_org_project(client)

            version_id = uuid6.uuid7()
            async with session_scope() as session:
                await session.execute(
                    sa.text(
                        "INSERT INTO script_versions (id, org_id, project_id, script_id, ordinal, source_hash, parser_version, created_at) "
                        "VALUES (:id, :org, :proj, :sid, 1, 'h', '1', :created)"
                    ),
                    {
                        "id": str(version_id),
                        "org": org_id,
                        "proj": proj_id,
                        "sid": str(uuid6.uuid7()),
                        "created": datetime.now(UTC),
                    },
                )

            res = await client.post(
                f"/api/v1/organizations/{org_id}/projects/{proj_id}/script-versions/{version_id}:detect"
            )
            assert res.status_code == 202, res.text
            data = res.json()["data"]
            assert data["jobType"] == "detection"
            assert data["status"] == "queued"

            # Real job row + audit event persisted.
            async with session_scope() as session:
                job = (await session.execute(sa.text("SELECT job_type, status FROM jobs WHERE id = :id"), {"id": data["jobId"]})).mappings().first()
                assert job and job["job_type"] == "detection"
                audit = (await session.execute(sa.text("SELECT count(*) c FROM audit_events WHERE action = 'detection.started'"))).mappings().first()
                assert audit["c"] == 1
    finally:
        app.dependency_overrides.pop(get_detection_runtime, None)


@pytest.mark.asyncio
async def test_start_detection_returns_503_when_runtime_not_configured():
    await init_and_seed_db()
    # No dependency override and no GEMINI_API_KEY => honest typed failure, no hermetic fallback.
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"origin": "http://test"}
    ) as client:
        org_id, proj_id = await _auth_org_project(client)
        version_id = uuid6.uuid7()
        async with session_scope() as session:
            await session.execute(
                sa.text(
                    "INSERT INTO script_versions (id, org_id, project_id, script_id, ordinal, source_hash, parser_version, created_at) "
                    "VALUES (:id, :org, :proj, :sid, 1, 'h', '1', :created)"
                ),
                {"id": str(version_id), "org": org_id, "proj": proj_id, "sid": str(uuid6.uuid7()), "created": datetime.now(UTC)},
            )
        res = await client.post(
            f"/api/v1/organizations/{org_id}/projects/{proj_id}/script-versions/{version_id}:detect"
        )
        assert res.status_code == 503


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
            # A version that does not belong to this project must 404, not detect.
            foreign_version = uuid6.uuid7()
            res = await client.post(
                f"/api/v1/organizations/{org_id}/projects/{proj_id}/script-versions/{foreign_version}:detect"
            )
            assert res.status_code == 404
    finally:
        app.dependency_overrides.pop(get_detection_runtime, None)

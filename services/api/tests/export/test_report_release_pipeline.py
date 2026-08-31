from datetime import UTC, datetime
from uuid import UUID
import pytest
import uuid6
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient
from clearcut.database import session_scope
from clearcut.init_db import init_and_seed_db
from clearcut.main import app


@pytest.mark.asyncio
async def test_report_snapshot_and_release_flow():
    await init_and_seed_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Register user
        reg_res = await client.post(
            "/api/v1/users",
            json={"name": "Report Manager", "email": "reports@studio.com", "password": "Password123!"},
        )
        assert reg_res.status_code == 201
        cookie = reg_res.cookies.get("__Host-clearcut_session")
        client.cookies.set("__Host-clearcut_session", cookie)

        # Create org & project
        org_res = await client.post(
            "/api/v1/organizations",
            json={"name": "Report Studio", "slug": "report-studio"},
        )
        org_id = org_res.json()["data"]["orgId"]

        proj_res = await client.post(
            f"/api/v1/organizations/{org_id}/projects",
            json={"title": "Report Project"},
        )
        proj_id = proj_res.json()["data"]["projectId"]

        # Insert script & version
        script_id = uuid6.uuid7()
        version_id = uuid6.uuid7()
        now = datetime.now(UTC)

        async with session_scope() as session:
            await session.execute(
                sa.text("""
                    INSERT INTO scripts (id, org_id, project_id, title, created_at)
                    VALUES (:id, :org_id, :project_id, 'Draft Screenplay', :created_at)
                """),
                {"id": str(script_id), "org_id": org_id, "project_id": proj_id, "created_at": now},
            )
            await session.execute(
                sa.text("""
                    INSERT INTO script_versions (id, script_id, org_id, project_id, ordinal, source_hash, parser_version, created_at)
                    VALUES (:id, :script_id, :org_id, :project_id, 1, 'hash123', 'v1.0.0', :created_at)
                """),
                {
                    "id": str(version_id),
                    "script_id": str(script_id),
                    "org_id": org_id,
                    "project_id": proj_id,
                    "created_at": now,
                },
            )

        # Create report snapshot
        snap_res = await client.post(
            f"/api/v1/organizations/{org_id}/projects/{proj_id}/report-snapshots",
            json={"scriptVersionId": str(version_id)},
        )
        assert snap_res.status_code == 201
        snap_data = snap_res.json()["data"]
        snapshot_id = snap_data["snapshotId"]
        assert snap_data["status"] == "draft"
        assert len(snap_data["contentHash"]) == 64

        # Release report with human attestation
        rel_res = await client.post(
            f"/api/v1/organizations/{org_id}/projects/{proj_id}/report-releases",
            json={"snapshotId": snapshot_id, "attestation": "I attest that all clearance items have been reviewed by legal counsel."},
        )
        assert rel_res.status_code == 201
        rel_data = rel_res.json()["data"]
        assert rel_data["status"] == "released"

        # Check status
        status_res = await client.get(f"/api/v1/organizations/{org_id}/projects/{proj_id}/report")
        assert status_res.status_code == 200
        assert status_res.json()["data"]["isReleased"] is True

        # Check audit event
        audit_res = await client.get(f"/api/v1/organizations/{org_id}/audit-events")
        assert audit_res.status_code == 200
        release_events = [e for e in audit_res.json()["data"] if e["action"] == "report.released"]
        assert len(release_events) == 1
        assert release_events[0]["targetId"] == snapshot_id

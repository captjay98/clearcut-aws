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
async def test_transactional_decision_and_audit_event_commit():
    await init_and_seed_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Register user
        reg_res = await client.post(
            "/api/v1/users",
            json={"name": "Decision Maker", "email": "decisions@studio.com", "password": "Password123!"},
        )
        assert reg_res.status_code == 201
        cookie = reg_res.cookies.get("__Host-clearcut_session")
        client.cookies.set("__Host-clearcut_session", cookie)

        # Create org & project
        org_res = await client.post(
            "/api/v1/organizations",
            json={"name": "Decision Studio", "slug": "decision-studio"},
        )
        org_id = org_res.json()["data"]["orgId"]

        proj_res = await client.post(
            f"/api/v1/organizations/{org_id}/projects",
            json={"title": "Decision Project"},
        )
        proj_id = proj_res.json()["data"]["projectId"]

        # Insert a clearance item into database
        item_id = uuid6.uuid7()
        script_id = uuid6.uuid7()
        ver_id = uuid6.uuid7()
        now = datetime.now(UTC)

        async with session_scope() as session:
            await session.execute(
                sa.text("""
                    INSERT INTO clearance_items (id, org_id, project_id, script_id, version_id, category, text, status, research_status, workflow_status, created_at)
                    VALUES (:id, :org_id, :project_id, :script_id, :version_id, 'Trademarks', 'Acme Corporation', 'open', 'completed', 'open', :created_at)
                """),
                {
                    "id": str(item_id),
                    "org_id": org_id,
                    "project_id": proj_id,
                    "script_id": str(script_id),
                    "version_id": str(ver_id),
                    "created_at": now,
                },
            )

        # Record decision
        dec_res = await client.post(
            f"/api/v1/organizations/{org_id}/projects/{proj_id}/items/{item_id}/decisions",
            json={"decision": "cleared", "rationale": "Verified trademark register has no active conflicting marks"},
        )
        assert dec_res.status_code == 201
        dec_data = dec_res.json()["data"]
        assert dec_data["decision"] == "cleared"
        assert dec_data["status"] == "committed"

        # Verify audit event was committed
        audit_res = await client.get(f"/api/v1/organizations/{org_id}/audit-events")
        assert audit_res.status_code == 200
        events = audit_res.json()["data"]
        assert len(events) >= 1
        decision_events = [e for e in events if e["action"] == "evidence.decision_recorded"]
        assert len(decision_events) == 1
        assert decision_events[0]["targetId"] == str(item_id)

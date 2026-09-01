from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
import uuid6
from httpx import ASGITransport, AsyncClient

from clearcut.database import session_scope
from clearcut.init_db import init_and_seed_db
from clearcut.main import app
from clearcut.research.runtime_provider import ResearchRuntime, get_research_runtime


async def _auth_org_project(client: AsyncClient) -> tuple[str, str]:
    reg = await client.post(
        "/api/v1/users",
        json={"name": "Researcher", "email": "research@studio.com", "password": "Password123!"},
    )
    assert reg.status_code == 201
    client.cookies.set("__Host-clearcut_session", reg.cookies.get("__Host-clearcut_session"))
    org = await client.post("/api/v1/organizations", json={"name": "Res Studio", "slug": "res-studio"})
    org_id = org.json()["data"]["orgId"]
    proj = await client.post(f"/api/v1/organizations/{org_id}/projects", json={"title": "Res Project"})
    return org_id, proj.json()["data"]["projectId"]


async def _insert_item(org_id: str, proj_id: str) -> str:
    item_id = uuid6.uuid7()
    async with session_scope() as session:
        await session.execute(
            sa.text("""
                INSERT INTO clearance_items (id, org_id, project_id, script_id, version_id, category, text, status, research_status, workflow_status, created_at)
                VALUES (:id, :org, :proj, :sid, :vid, 'Trademarks', 'Acme Corporation', 'open', 'pending', 'open', :created)
            """),
            {
                "id": str(item_id),
                "org": org_id,
                "proj": proj_id,
                "sid": str(uuid6.uuid7()),
                "vid": str(uuid6.uuid7()),
                "created": datetime.now(UTC),
            },
        )
    return str(item_id)


class _FakeResearchRuntime(ResearchRuntime):
    def __init__(self) -> None:  # no real providers; test double only
        super().__init__(search=None, extract=None)


@pytest.mark.asyncio
async def test_start_research_persists_job_and_audit_when_runtime_injected():
    await init_and_seed_db()
    app.dependency_overrides[get_research_runtime] = lambda: _FakeResearchRuntime()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers={"origin": "http://test"}
        ) as client:
            org_id, proj_id = await _auth_org_project(client)
            item_id = await _insert_item(org_id, proj_id)

            res = await client.post(
                f"/api/v1/organizations/{org_id}/projects/{proj_id}/clearance-items/{item_id}:research"
            )
            assert res.status_code == 202, res.text
            data = res.json()["data"]
            assert data["jobType"] == "research"

            async with session_scope() as session:
                job = (await session.execute(sa.text("SELECT job_type FROM jobs WHERE id = :id"), {"id": data["jobId"]})).mappings().first()
                assert job and job["job_type"] == "research"
                audit = (await session.execute(sa.text("SELECT count(*) c FROM audit_events WHERE action = 'research.started'"))).mappings().first()
                assert audit["c"] == 1
    finally:
        app.dependency_overrides.pop(get_research_runtime, None)


@pytest.mark.asyncio
async def test_start_research_returns_503_when_runtime_not_configured():
    await init_and_seed_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"origin": "http://test"}
    ) as client:
        org_id, proj_id = await _auth_org_project(client)
        item_id = await _insert_item(org_id, proj_id)
        res = await client.post(
            f"/api/v1/organizations/{org_id}/projects/{proj_id}/clearance-items/{item_id}:research"
        )
        assert res.status_code == 503


@pytest.mark.asyncio
async def test_start_research_rejects_cross_tenant_item():
    await init_and_seed_db()
    app.dependency_overrides[get_research_runtime] = lambda: _FakeResearchRuntime()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers={"origin": "http://test"}
        ) as client:
            org_id, proj_id = await _auth_org_project(client)
            foreign_item = uuid6.uuid7()
            res = await client.post(
                f"/api/v1/organizations/{org_id}/projects/{proj_id}/clearance-items/{foreign_item}:research"
            )
            assert res.status_code == 404
    finally:
        app.dependency_overrides.pop(get_research_runtime, None)

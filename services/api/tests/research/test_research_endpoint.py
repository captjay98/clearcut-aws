import json
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
import uuid6
from clearcut.database import is_sqlite, session_scope
from clearcut.init_db import init_and_seed_db
from clearcut.main import app
from clearcut.research.runtime_provider import ResearchRuntime, get_research_runtime
from httpx import ASGITransport, AsyncClient


async def _auth_org_project(client: AsyncClient) -> tuple[str, str]:
    reg = await client.post(
        "/api/v1/users",
        json={"name": "Researcher", "email": "research@studio.com", "password": "Password123!"},
    )
    assert reg.status_code == 201
    org = await client.post("/api/v1/organizations", json={"name": "Res Studio", "slug": "res-studio"})
    org_id = org.json()["data"]["orgId"]
    proj = await client.post(f"/api/v1/organizations/{org_id}/projects", json={"title": "Res Project"})
    return org_id, proj.json()["data"]["projectId"]


async def _insert_item(org_id: str, proj_id: str) -> str:
    now = datetime.now(UTC)
    script_id = uuid6.uuid7()
    version_id = uuid6.uuid7()
    element_id = uuid6.uuid7()
    item_id = uuid6.uuid7()
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO scripts (id, org_id, project_id, title, created_at) "
                "VALUES (:id, :org, :proj, 'Research test', :created)"
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
        await session.execute(
            sa.text(
                "INSERT INTO script_elements (id, version_id, ordinal, element_type, text) "
                "VALUES (:id, :version, 1, 'action', 'Acme Corporation')"
            ),
            {"id": str(element_id), "version": str(version_id)},
        )
        await session.execute(
            sa.text(
                """
                INSERT INTO clearance_items (
                    id, org_id, project_id, script_id, version_id, element_id,
                    category, text, status, research_status, workflow_status, created_at
                ) VALUES (
                    :id, :org, :proj, :sid, :vid, :element,
                    'Trademarks', 'Acme Corporation', 'open', 'pending', 'open', :created
                )
                """
            ),
            {
                "id": str(item_id),
                "org": org_id,
                "proj": proj_id,
                "sid": str(script_id),
                "vid": str(version_id),
                "element": str(element_id),
                "created": now,
            },
        )
    return str(item_id)


class _FakeResearchRuntime(ResearchRuntime):
    def __init__(self) -> None:
        super().__init__(search=None, extract=None)


@pytest.mark.asyncio
async def test_start_research_persists_canonical_job_and_authoritative_audit():
    await init_and_seed_db()
    app.dependency_overrides[get_research_runtime] = lambda: _FakeResearchRuntime()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers={"origin": "http://test"}
        ) as client:
            org_id, proj_id = await _auth_org_project(client)
            item_id = await _insert_item(org_id, proj_id)

            first = await client.post(
                f"/api/v1/organizations/{org_id}/projects/{proj_id}/clearance-items/{item_id}:research"
            )
            second = await client.post(
                f"/api/v1/organizations/{org_id}/projects/{proj_id}/clearance-items/{item_id}:research"
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
                assert job["job_type"] == "research"
                assert job["status"] == job["stage"] == "queued"
                assert job["idempotency_key"] == f"research:{item_id}"
                assert payload == {
                    "schemaVersion": 1,
                    "target": {"type": "clearance_item", "id": item_id},
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
                            "AND action = 'research.started' AND target_id = :target"
                        ),
                        {"org": org_id, "proj": proj_id, "target": item_id},
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
        assert res.json()["error"]["code"] == "capability_unavailable"
        assert res.headers["x-request-id"]


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
            assert res.json()["error"]["code"] == "not_found"
            assert res.headers["x-request-id"]
    finally:
        app.dependency_overrides.pop(get_research_runtime, None)



@pytest.mark.asyncio
@pytest.mark.skipif(not is_sqlite, reason="SQLite trigger simulates authoritative audit failure")
async def test_start_research_rolls_back_job_when_authoritative_audit_fails():
    await init_and_seed_db()
    app.dependency_overrides[get_research_runtime] = lambda: _FakeResearchRuntime()
    trigger_name = "fail_research_audit_insert"
    try:
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers={"origin": "http://test"}
        ) as client:
            org_id, proj_id = await _auth_org_project(client)
            item_id = await _insert_item(org_id, proj_id)
            async with session_scope() as session:
                await session.execute(
                    sa.text(
                        f"CREATE TRIGGER {trigger_name} BEFORE INSERT ON authoritative_audit_events "
                        "BEGIN SELECT RAISE(ABORT, 'simulated audit failure'); END"
                    )
                )

            response = await client.post(
                f"/api/v1/organizations/{org_id}/projects/{proj_id}/"
                f"clearance-items/{item_id}:research"
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
                            "key": f"research:{item_id}",
                        },
                    )
                ).scalar_one()
                assert job_count == 0
    finally:
        async with session_scope() as session:
            await session.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger_name}"))
        app.dependency_overrides.pop(get_research_runtime, None)

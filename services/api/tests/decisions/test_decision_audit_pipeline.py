import hashlib
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
import uuid6
from clearcut.database import session_scope
from clearcut.init_db import init_and_seed_db
from clearcut.main import app
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_transactional_decision_and_authoritative_audit_commit():
    """The canonical :recordEvidenceDecision operation commits the governed
    decision, advances the item version, and writes the authoritative audit
    event in the same transaction. The retired /items/{item}/decisions route
    that wrote the legacy audit_events table is gone."""
    await init_and_seed_db(seed_if_empty=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"origin": "http://test"}
    ) as client:
        # Register user (auto session cookie)
        reg_res = await client.post(
            "/api/v1/users",
            json={
                "name": "Decision Maker",
                "email": f"decisions-{uuid4().hex}@studio.com",
                "password": "Password123!",
            },
        )
        assert reg_res.status_code == 201

        # Create org & project
        org_res = await client.post(
            "/api/v1/organizations",
            json={"name": "Decision Studio", "slug": f"decision-studio-{uuid4().hex[:8]}"},
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
        element_id = uuid6.uuid7()
        now = datetime.now(UTC)

        async with session_scope() as session:
            await session.execute(
                sa.text(
                    "INSERT INTO scripts (id, org_id, project_id, title, created_at) "
                    "VALUES (:id, :org_id, :project_id, 'Decision test', :created_at)"
                ),
                {
                    "id": str(script_id),
                    "org_id": org_id,
                    "project_id": proj_id,
                    "created_at": now,
                },
            )
            await session.execute(
                sa.text(
                    "INSERT INTO script_versions "
                    "(id, script_id, org_id, project_id, ordinal, source_hash, parser_version, created_at) "
                    "VALUES (:id, :script_id, :org_id, :project_id, 1, 'h', '1', :created_at)"
                ),
                {
                    "id": str(ver_id),
                    "script_id": str(script_id),
                    "org_id": org_id,
                    "project_id": proj_id,
                    "created_at": now,
                },
            )
            await session.execute(
                sa.text(
                    "INSERT INTO script_elements (id, version_id, ordinal, element_type, text) "
                    "VALUES (:id, :version_id, 1, 'action', 'Acme Corporation')"
                ),
                {"id": str(element_id), "version_id": str(ver_id)},
            )
            await session.execute(
                sa.text("""
                    INSERT INTO clearance_items (id, org_id, project_id, script_id, version_id, element_id, category, text, status, research_status, workflow_status, created_at, version)
                    VALUES (:id, :org_id, :project_id, :script_id, :version_id, :element_id, 'products_and_trademarks', 'Acme Corporation', 'unresolved', 'completed', 'detected', :created_at, 1)
                """),
                {
                    "id": str(item_id),
                    "org_id": org_id,
                    "project_id": proj_id,
                    "script_id": str(script_id),
                    "version_id": str(ver_id),
                    "element_id": str(element_id),
                    "created_at": now,
                },
            )

        # Record an evidence decision on the canonical operation. An escalation
        # outcome is allowed even with zero cited claims and does not assert a
        # legal conclusion.
        intent_hash = hashlib.sha256(b"further_review_required|Requires review|1").hexdigest()
        dec_res = await client.post(
            f"/api/v1/organizations/{org_id}/projects/{proj_id}"
            f"/clearance-items/{item_id}:recordEvidenceDecision",
            json={
                "decision": "further_review_required",
                "rationale": "Requires further review before any clearance treatment.",
                "expectedVersion": 1,
                "intentHash": intent_hash,
            },
            headers={"Idempotency-Key": f"idem-pipeline-{uuid4().hex}"},
        )
        assert dec_res.status_code == 200, dec_res.text
        dec_data = dec_res.json()["data"]
        assert dec_data["itemId"] == str(item_id)
        assert dec_data["version"] == 2

    # Verify the governed decision and the authoritative audit event were both
    # committed in the same transaction, and that the item version advanced.
    async with session_scope() as verify:
        decision_count = (
            await verify.execute(
                sa.text(
                    "SELECT count(*) FROM governed_decision_records "
                    "WHERE item_id = :item_id AND org_id = :org_id AND project_id = :project_id"
                ),
                {"item_id": str(item_id), "org_id": org_id, "project_id": proj_id},
            )
        ).scalar_one()
        audit_row = (
            (
                await verify.execute(
                    sa.text(
                        "SELECT action, target_type, target_id, actor_id "
                        "FROM authoritative_audit_events "
                        "WHERE target_id = :item_id AND action = 'decision.evidence.recorded'"
                    ),
                    {"item_id": str(item_id)},
                )
            )
            .mappings()
            .all()
        )
        item_version = (
            await verify.execute(
                sa.text("SELECT version FROM clearance_items WHERE id = :id"),
                {"id": str(item_id)},
            )
        ).scalar_one()

    assert decision_count == 1
    assert len(audit_row) == 1
    assert audit_row[0]["target_type"] == "clearance_item"
    assert UUID(str(audit_row[0]["target_id"])) == item_id
    assert item_version == 2

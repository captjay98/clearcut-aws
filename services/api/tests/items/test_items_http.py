from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from clearcut.database import engine, session_scope
from clearcut.items.delivery import http as items_http
from clearcut.main import app
from httpx import ASGITransport, AsyncClient


@dataclass(frozen=True)
class TenantItemFixture:
    org_id: UUID
    project_id: UUID
    version_id: UUID
    item_id: UUID
    entity_name: str
    context_text: str


async def _client() -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"origin": "http://test"},
    )


async def _create_tenant_item_fixture(
    client: AsyncClient,
    *,
    suffix: str,
    entity_name: str,
    context_text: str,
) -> TenantItemFixture:
    registration = await client.post(
        "/api/v1/users",
        json={
            "name": f"Item Owner {suffix}",
            "email": f"item-owner-{suffix}-{uuid4().hex}@example.com",
            "password": "Password123!",
        },
    )
    assert registration.status_code == 201, registration.text
    organization = await client.post(
        "/api/v1/organizations",
        json={
            "name": f"Item Studio {suffix}",
            "slug": f"item-studio-{suffix}-{uuid4().hex[:8]}",
        },
    )
    assert organization.status_code == 201, organization.text
    org_id = UUID(organization.json()["data"]["orgId"])
    project = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        json={"title": f"Persisted Items {suffix}"},
    )
    assert project.status_code == 201, project.text
    project_id = UUID(project.json()["data"]["projectId"])

    script_id, version_id, element_id, item_id = uuid4(), uuid4(), uuid4(), uuid4()
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO scripts "
                "(id, org_id, project_id, title, current_slot, created_at) "
                "VALUES (:id, :org, :project, :title, 'current', CURRENT_TIMESTAMP)"
            ),
            {
                "id": str(script_id),
                "org": str(org_id),
                "project": str(project_id),
                "title": f"Items {suffix}",
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO script_versions "
                "(id, script_id, org_id, project_id, ordinal, source_hash, "
                "parser_version, created_at) VALUES "
                "(:id, :script, :org, :project, 1, :source_hash, 'test', "
                "CURRENT_TIMESTAMP)"
            ),
            {
                "id": str(version_id),
                "script": str(script_id),
                "org": str(org_id),
                "project": str(project_id),
                "source_hash": f"items-{suffix}-{version_id}",
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO script_elements "
                "(id, version_id, ordinal, element_type, text) "
                "VALUES (:id, :version, 1, 'action', :context_text)"
            ),
            {
                "id": str(element_id),
                "version": str(version_id),
                "context_text": context_text,
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO clearance_items "
                "(id, org_id, project_id, script_id, version_id, element_id, "
                "category, text, status, workflow_status, research_status, "
                "disposition_status, created_at) VALUES "
                "(:id, :org, :project, :script, :version, :element, "
                "'products_and_trademarks', :entity_name, 'unresolved', "
                "'detected', 'not_started', 'undisposed', CURRENT_TIMESTAMP)"
            ),
            {
                "id": str(item_id),
                "org": str(org_id),
                "project": str(project_id),
                "script": str(script_id),
                "version": str(version_id),
                "element": str(element_id),
                "entity_name": entity_name,
            },
        )

    return TenantItemFixture(
        org_id=org_id,
        project_id=project_id,
        version_id=version_id,
        item_id=item_id,
        entity_name=entity_name,
        context_text=context_text,
    )


@pytest.mark.asyncio
async def test_list_and_get_clearance_items_enforce_tenant_and_project_scope() -> None:
    async with await _client() as owner, await _client() as foreign_owner:
        owned = await _create_tenant_item_fixture(
            owner,
            suffix="owned",
            entity_name="Apple iPhone",
            context_text="Mara sees an Apple iPhone.",
        )
        foreign = await _create_tenant_item_fixture(
            foreign_owner,
            suffix="foreign",
            entity_name="Foreign Tenant Product",
            context_text="A foreign tenant sees a private product.",
        )

        listed = await owner.get(
            f"/api/v1/organizations/{owned.org_id}/projects/{owned.project_id}/clearance-items"
        )
        foreign_item_through_owned_scope = await owner.get(
            f"/api/v1/organizations/{owned.org_id}/projects/{owned.project_id}/"
            f"clearance-items/{foreign.item_id}"
        )
        foreign_tenant_through_owner_session = await owner.get(
            f"/api/v1/organizations/{foreign.org_id}/projects/{foreign.project_id}/"
            f"clearance-items/{foreign.item_id}"
        )
        foreign_item_through_foreign_scope = await foreign_owner.get(
            f"/api/v1/organizations/{foreign.org_id}/projects/{foreign.project_id}/"
            f"clearance-items/{foreign.item_id}"
        )

    assert listed.status_code == 200, listed.text
    assert listed.json()["data"] == [
        {
            "itemId": str(owned.item_id),
            "projectId": str(owned.project_id),
            "versionId": str(owned.version_id),
            "version": 1,
            "category": "products_and_trademarks",
            "entityName": owned.entity_name,
            "contextText": owned.context_text,
            "status": "unresolved",
            "disposition": "undisposed",
            "claimCount": 0,
            "severity": "Medium",
            "confidence": 70,
            "sourcesDisagree": False,
            "displayStatus": "Needs research",
        }
    ]
    assert listed.json()["meta"]["totalCount"] == 1
    assert foreign.item_id not in {UUID(item["itemId"]) for item in listed.json()["data"]}

    assert foreign_item_through_owned_scope.status_code == 404
    assert foreign_tenant_through_owner_session.status_code == 403
    assert foreign_item_through_foreign_scope.status_code == 200
    assert foreign_item_through_foreign_scope.json()["data"]["itemId"] == str(foreign.item_id)


@pytest.mark.asyncio
async def test_list_clearance_items_excludes_cross_scope_claims_from_count() -> None:
    if engine.dialect.name != "sqlite":
        pytest.skip("Corrupt-row fixture requires SQLite PRAGMA foreign key control.")
    async with await _client() as owner, await _client() as foreign_owner:
        owned = await _create_tenant_item_fixture(
            owner,
            suffix="claim-count-owned",
            entity_name="Owned Product",
            context_text="The owned screenplay shows a product.",
        )
        foreign = await _create_tenant_item_fixture(
            foreign_owner,
            suffix="claim-count-foreign",
            entity_name="Foreign Product",
            context_text="The foreign screenplay shows another product.",
        )

        run_id, snapshot_id, claim_id = uuid4(), uuid4(), uuid4()
        async with session_scope() as session:
            await session.execute(
                sa.text(
                    "INSERT INTO research_runs "
                    "(id, org_id, project_id, item_id, status, created_at) "
                    "VALUES (:id, :org, :project, :item, 'completed', CURRENT_TIMESTAMP)"
                ),
                {
                    "id": str(run_id),
                    "org": str(foreign.org_id),
                    "project": str(foreign.project_id),
                    "item": str(foreign.item_id),
                },
            )
            await session.execute(
                sa.text(
                    "INSERT INTO source_snapshots "
                    "(id, org_id, project_id, item_id, run_id, url, title, publisher, "
                    "excerpt, origin, sha256_hash, retrieved_at) VALUES "
                    "(:id, :org, :project, :item, :run, :url, :title, :publisher, "
                    ":excerpt, 'search', :sha256_hash, CURRENT_TIMESTAMP)"
                ),
                {
                    "id": str(snapshot_id),
                    "org": str(foreign.org_id),
                    "project": str(foreign.project_id),
                    "item": str(foreign.item_id),
                    "run": str(run_id),
                    "url": "https://foreign.example/evidence",
                    "title": "Foreign evidence",
                    "publisher": "Foreign publisher",
                    "excerpt": "Evidence from another tenant scope.",
                    "sha256_hash": "f" * 64,
                },
            )

        assert engine.dialect.name == "sqlite"
        async with engine.connect() as connection:
            await connection.execute(sa.text("PRAGMA foreign_keys=OFF"))
            await connection.commit()
            try:
                await connection.execute(
                    sa.text(
                        "INSERT INTO evidence_claims "
                        "(id, org_id, project_id, item_id, snapshot_id, stance, "
                        "authority_tier, claim_text, provenance_excerpt, created_at) VALUES "
                        "(:id, :org, :project, :item, :snapshot, 'context', 'secondary', "
                        ":claim_text, :excerpt, CURRENT_TIMESTAMP)"
                    ),
                    {
                        "id": str(claim_id),
                        "org": str(foreign.org_id),
                        "project": str(foreign.project_id),
                        "item": str(owned.item_id),
                        "snapshot": str(snapshot_id),
                        "claim_text": "A foreign-scoped claim must not affect the owned count.",
                        "excerpt": "Cross-scope fixture.",
                    },
                )
                await connection.commit()
            finally:
                await connection.execute(sa.text("PRAGMA foreign_keys=ON"))
                await connection.commit()

        listed = await owner.get(
            f"/api/v1/organizations/{owned.org_id}/projects/{owned.project_id}/clearance-items"
        )

    assert listed.status_code == 200, listed.text
    items_by_id = {item["itemId"]: item for item in listed.json()["data"]}
    assert items_by_id[str(owned.item_id)]["claimCount"] == 0


def test_claim_count_query_is_dialect_neutrally_tenant_scoped() -> None:
    query = str(items_http.LIST_ITEMS_QUERY)
    assert "c.item_id = i.id" in query
    assert "c.org_id = i.org_id" in query
    assert "c.project_id = i.project_id" in query

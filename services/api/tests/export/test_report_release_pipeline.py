from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from clearcut.database import session_scope
from clearcut.init_db import init_and_seed_db
from httpx import ASGITransport, AsyncClient

ROOT = Path(__file__).resolve().parents[4]
SUPPORT_DIR = ROOT / "apps" / "web" / "tests" / "support"
if str(SUPPORT_DIR) not in sys.path:
    sys.path.insert(0, str(SUPPORT_DIR))

from e2e_api import app  # noqa: E402


async def _create_workspace(client: AsyncClient, label: str) -> dict[str, str]:
    registration = await client.post(
        "/api/v1/users",
        json={
            "name": f"Report Manager {label}",
            "email": f"reports-{label}-{uuid4().hex}@studio.example",
            "password": "Password123!",
        },
    )
    assert registration.status_code == 201, registration.text

    organization = await client.post(
        "/api/v1/organizations",
        json={
            "name": f"Report Studio {label}",
            "slug": f"report-{label}-{uuid4().hex[:8]}",
        },
    )
    assert organization.status_code == 201, organization.text
    org_id = organization.json()["data"]["orgId"]

    project = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        json={"title": f"Report Project {label}"},
    )
    assert project.status_code == 201, project.text
    project_id = project.json()["data"]["projectId"]

    fixture = await client.post(
        f"/e2e/organizations/{org_id}/projects/{project_id}/evidence-fixture"
    )
    assert fixture.status_code == 201, fixture.text
    return fixture.json()["data"]


@pytest.mark.asyncio
async def test_report_snapshot_release_and_html_remain_frozen_after_live_drift() -> None:
    await init_and_seed_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"origin": "http://test"},
    ) as client:
        fixture = await _create_workspace(client, "frozen")
        org_id = fixture["orgId"]
        project_id = fixture["projectId"]

        preview = await client.get(
            f"/api/v1/organizations/{org_id}/projects/{project_id}/report-preview"
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["data"] == {
            "projectId": project_id,
            "totalItems": 2,
            "clearedItems": 0,
            "flaggedItems": 2,
            "unresolvedRisk": 2,
            "categories": [{"category": "products_and_trademarks", "count": 2}],
        }

        generated = await client.post(
            f"/api/v1/organizations/{org_id}/projects/{project_id}/report-snapshots",
            json={"scriptVersionId": fixture["versionId"]},
        )
        assert generated.status_code == 201, generated.text
        snapshot = generated.json()["data"]
        assert snapshot["versionId"] == fixture["versionId"]
        assert snapshot["status"] == "generated"
        assert len(snapshot["contentHash"]) == 64
        assert snapshot["bindingManifest"]["openItemCount"] == 2
        assert snapshot["bindingManifest"]["legalBoundary"] == (
            "ClearCut provides sourced findings for qualified human review. "
            "It does not provide legal advice or final legal clearance."
        )
        claim_counts = {
            item["entityName"]: item["claimCount"] for item in snapshot["bindingManifest"]["items"]
        }
        assert claim_counts == {"Vega Camera": 1, "Northstar Drone": 0}

        fetched = await client.get(
            f"/api/v1/organizations/{org_id}/projects/{project_id}"
            f"/report-snapshots/{snapshot['snapshotId']}"
        )
        assert fetched.status_code == 200, fetched.text
        assert fetched.json()["data"] == snapshot

        invalid_release = await client.post(
            f"/api/v1/organizations/{org_id}/projects/{project_id}"
            f"/report-snapshots/{snapshot['snapshotId']}:release",
            json={
                "attestation": (
                    "I reviewed this snapshot carefully for the production team, "
                    "but this statement omits the required legal boundary."
                )
            },
        )
        assert invalid_release.status_code == 422, invalid_release.text

        attestation = (
            "I attest this frozen snapshot is accurate for human review and is not "
            "legal advice or final legal clearance."
        )
        release = await client.post(
            f"/api/v1/organizations/{org_id}/projects/{project_id}"
            f"/report-snapshots/{snapshot['snapshotId']}:release",
            json={"attestation": attestation},
        )
        assert release.status_code == 200, release.text
        released = release.json()["data"]
        assert released["snapshotId"] == snapshot["snapshotId"]
        assert released["contentHash"] == snapshot["contentHash"]
        assert released["attestation"].startswith("I attest this frozen snapshot")

        repeated_release = await client.post(
            f"/api/v1/organizations/{org_id}/projects/{project_id}"
            f"/report-snapshots/{snapshot['snapshotId']}:release",
            json={"attestation": attestation},
        )
        assert repeated_release.status_code == 200, repeated_release.text
        assert repeated_release.json()["data"] == released

        changed_attestation = await client.post(
            f"/api/v1/organizations/{org_id}/projects/{project_id}"
            f"/report-snapshots/{snapshot['snapshotId']}:release",
            json={
                "attestation": (
                    "I separately attest this frozen snapshot is accurate and is not legal "
                    "advice or final legal clearance."
                )
            },
        )
        assert changed_attestation.status_code == 409, changed_attestation.text

        metadata = await client.get(
            f"/api/v1/organizations/{org_id}/projects/{project_id}"
            f"/report-releases/{released['releaseId']}/artifact-metadata"
        )
        assert metadata.status_code == 200, metadata.text
        assert metadata.json()["data"]["contentHash"] == snapshot["contentHash"]
        download_url = metadata.json()["data"]["downloadUrl"]

        downloaded = await client.get(download_url)
        assert downloaded.status_code == 200, downloaded.text
        assert downloaded.headers["content-type"].startswith("text/html")
        original_html = downloaded.text
        assert "Vega Camera" in original_html
        assert "Northstar Drone" in original_html
        assert "Zero cited evidence remains unresolved" in original_html
        assert "https://example.com/e2e-fixtures/vega-camera" in original_html
        assert "does not provide legal advice or final legal clearance" in original_html

        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as anonymous_client:
            anonymous_download = await anonymous_client.get(download_url)
        assert anonymous_download.status_code == 401, anonymous_download.text

        async with session_scope() as session:
            await session.execute(
                sa.text(
                    "UPDATE clearance_items SET text = 'MUTATED LIVE ITEM' "
                    "WHERE id = :item_id AND org_id = :org_id AND project_id = :project_id"
                ),
                {
                    "item_id": fixture["citedItemId"],
                    "org_id": org_id,
                    "project_id": project_id,
                },
            )

        downloaded_after_drift = await client.get(download_url)
        assert downloaded_after_drift.status_code == 200
        assert downloaded_after_drift.text == original_html
        assert "MUTATED LIVE ITEM" not in downloaded_after_drift.text

        history = await client.get(
            f"/api/v1/organizations/{org_id}/projects/{project_id}/report-history"
        )
        assert history.status_code == 200, history.text
        assert history.json()["data"][0]["releaseId"] == released["releaseId"]

    async with session_scope() as session:
        release_count = await session.scalar(
            sa.text(
                "SELECT COUNT(*) FROM report_releases "
                "WHERE org_id = :org_id AND project_id = :project_id"
            ),
            {"org_id": org_id, "project_id": project_id},
        )
        release_audit_count = await session.scalar(
            sa.text(
                "SELECT COUNT(*) FROM authoritative_audit_events "
                "WHERE org_id = :org_id AND project_id = :project_id "
                "AND action = 'report.released'"
            ),
            {"org_id": org_id, "project_id": project_id},
        )
    assert release_count == 1
    assert release_audit_count == 1


@pytest.mark.asyncio
async def test_report_release_rejects_cross_project_snapshot_without_audit() -> None:
    await init_and_seed_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"origin": "http://test"},
    ) as client:
        first = await _create_workspace(client, "first")
        second_org = await client.post(
            "/api/v1/organizations",
            json={"name": "Second Report Studio", "slug": f"second-{uuid4().hex[:8]}"},
        )
        second_org_id = second_org.json()["data"]["orgId"]
        second_project = await client.post(
            f"/api/v1/organizations/{second_org_id}/projects",
            json={"title": "Second Report Project"},
        )
        second_project_id = second_project.json()["data"]["projectId"]

        generated = await client.post(
            f"/api/v1/organizations/{first['orgId']}/projects/{first['projectId']}"
            "/report-snapshots",
            json={"scriptVersionId": first["versionId"]},
        )
        assert generated.status_code == 201, generated.text
        snapshot_id = generated.json()["data"]["snapshotId"]

        cross_scope = await client.post(
            f"/api/v1/organizations/{second_org_id}/projects/{second_project_id}"
            f"/report-snapshots/{snapshot_id}:release",
            json={
                "attestation": (
                    "I attest this frozen snapshot is accurate for human review and is not "
                    "legal advice or final legal clearance."
                )
            },
        )

    assert cross_scope.status_code == 404
    async with session_scope() as session:
        audit_count = await session.scalar(
            sa.text(
                "SELECT COUNT(*) FROM authoritative_audit_events "
                "WHERE org_id = :org_id AND project_id = :project_id "
                "AND action = 'report.released'"
            ),
            {"org_id": second_org_id, "project_id": second_project_id},
        )
    assert audit_count == 0


@pytest.mark.asyncio
async def test_report_generation_rejects_missing_immutable_version_binding_without_audit() -> None:
    await init_and_seed_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"origin": "http://test"},
    ) as client:
        fixture = await _create_workspace(client, "missing-binding")
        async with session_scope() as session:
            await session.execute(
                sa.text(
                    "UPDATE script_versions SET source_hash = '' "
                    "WHERE id = :version_id AND org_id = :org_id AND project_id = :project_id"
                ),
                {
                    "version_id": fixture["versionId"],
                    "org_id": fixture["orgId"],
                    "project_id": fixture["projectId"],
                },
            )

        generated = await client.post(
            f"/api/v1/organizations/{fixture['orgId']}/projects/{fixture['projectId']}"
            "/report-snapshots",
            json={"scriptVersionId": fixture["versionId"]},
        )

    assert generated.status_code == 409, generated.text
    async with session_scope() as session:
        snapshot_count = await session.scalar(
            sa.text(
                "SELECT COUNT(*) FROM report_snapshots "
                "WHERE org_id = :org_id AND project_id = :project_id"
            ),
            {"org_id": fixture["orgId"], "project_id": fixture["projectId"]},
        )
        audit_count = await session.scalar(
            sa.text(
                "SELECT COUNT(*) FROM authoritative_audit_events "
                "WHERE org_id = :org_id AND project_id = :project_id "
                "AND action = 'report.generated'"
            ),
            {"org_id": fixture["orgId"], "project_id": fixture["projectId"]},
        )
    assert snapshot_count == 0
    assert audit_count == 0

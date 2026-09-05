from __future__ import annotations

import sys
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

ROOT = Path(__file__).resolve().parents[4]
SUPPORT_DIR = ROOT / "apps" / "web" / "tests" / "support"
if str(SUPPORT_DIR) not in sys.path:
    sys.path.insert(0, str(SUPPORT_DIR))

from e2e_api import app  # noqa: E402

pytestmark = pytest.mark.asyncio


async def _client() -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"origin": "http://test"},
    )


async def test_owner_bootstrap_creates_cited_and_zero_evidence_items() -> None:
    async with await _client() as client:
        registration = await client.post(
            "/api/v1/users",
            json={
                "name": "Evidence Fixture Owner",
                "email": f"evidence-fixture-{uuid4().hex}@example.com",
                "password": "Password123!",
            },
        )
        assert registration.status_code == 201, registration.text

        organization = await client.post(
            "/api/v1/organizations",
            json={
                "name": "Evidence Fixture Studio",
                "slug": f"evidence-fixture-{uuid4().hex[:8]}",
            },
        )
        assert organization.status_code == 201, organization.text
        org_id = UUID(organization.json()["data"]["orgId"])

        project = await client.post(
            f"/api/v1/organizations/{org_id}/projects",
            json={"title": "Evidence Fixture Project"},
        )
        assert project.status_code == 201, project.text
        project_id = UUID(project.json()["data"]["projectId"])

        created = await client.post(
            f"/e2e/organizations/{org_id}/projects/{project_id}/evidence-fixture"
        )

        assert created.status_code == 201, created.text
        fixture = created.json()["data"]
        assert fixture["orgId"] == str(org_id)
        assert fixture["projectId"] == str(project_id)
        cited_item_id = fixture["citedItemId"]
        zero_evidence_item_id = fixture["zeroEvidenceItemId"]

        listed = await client.get(
            f"/api/v1/organizations/{org_id}/projects/{project_id}/clearance-items"
        )
        cited = await client.get(
            f"/api/v1/organizations/{org_id}/projects/{project_id}/clearance-items/{cited_item_id}"
        )
        zero_evidence = await client.get(
            f"/api/v1/organizations/{org_id}/projects/{project_id}/"
            f"clearance-items/{zero_evidence_item_id}"
        )

    assert listed.status_code == 200, listed.text
    items = {item["itemId"]: item for item in listed.json()["data"]}
    assert set(items) == {cited_item_id, zero_evidence_item_id}
    assert items[cited_item_id]["claimCount"] == 1
    assert items[zero_evidence_item_id]["claimCount"] == 0

    assert cited.status_code == 200, cited.text
    cited_data = cited.json()["data"]
    assert cited_data["evidenceState"]["status"] == "cited"
    assert cited_data["evidenceState"]["unresolved"] is True
    assert cited_data["evidenceState"]["claimCount"] == 1
    assert len(cited_data["claims"]) == 1
    assert len(cited_data["snapshots"]) == 1

    assert zero_evidence.status_code == 200, zero_evidence.text
    zero_data = zero_evidence.json()["data"]
    assert zero_data["status"] == "unresolved"
    assert zero_data["evidenceState"] == {
        "status": "pending",
        "unresolved": True,
        "claimCount": 0,
        "reason": "Evidence research has not produced cited claims.",
    }
    assert zero_data["claims"] == []
    assert zero_data["snapshots"] == []


async def test_evidence_fixture_requires_an_authenticated_session() -> None:
    async with await _client() as client:
        response = await client.post(
            f"/e2e/organizations/{uuid4()}/projects/{uuid4()}/evidence-fixture"
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"


async def test_evidence_fixture_rejects_cross_organization_project_scope() -> None:
    async with await _client() as client:
        registration = await client.post(
            "/api/v1/users",
            json={
                "name": "Scoped Fixture Owner",
                "email": f"scoped-fixture-{uuid4().hex}@example.com",
                "password": "Password123!",
            },
        )
        assert registration.status_code == 201, registration.text

        organization_ids: list[UUID] = []
        project_ids: list[UUID] = []
        for ordinal in (1, 2):
            organization = await client.post(
                "/api/v1/organizations",
                json={
                    "name": f"Scoped Fixture Studio {ordinal}",
                    "slug": f"scoped-fixture-{ordinal}-{uuid4().hex[:8]}",
                },
            )
            assert organization.status_code == 201, organization.text
            org_id = UUID(organization.json()["data"]["orgId"])
            project = await client.post(
                f"/api/v1/organizations/{org_id}/projects",
                json={"title": f"Scoped Fixture Project {ordinal}"},
            )
            assert project.status_code == 201, project.text
            organization_ids.append(org_id)
            project_ids.append(UUID(project.json()["data"]["projectId"]))

        response = await client.post(
            f"/e2e/organizations/{organization_ids[0]}/projects/{project_ids[1]}/evidence-fixture"
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_evidence_fixture_rejects_repeat_bootstrap_without_duplicate_rows() -> None:
    async with await _client() as client:
        registration = await client.post(
            "/api/v1/users",
            json={
                "name": "Repeat Fixture Owner",
                "email": f"repeat-fixture-{uuid4().hex}@example.com",
                "password": "Password123!",
            },
        )
        assert registration.status_code == 201, registration.text
        organization = await client.post(
            "/api/v1/organizations",
            json={
                "name": "Repeat Fixture Studio",
                "slug": f"repeat-fixture-{uuid4().hex[:8]}",
            },
        )
        assert organization.status_code == 201, organization.text
        org_id = UUID(organization.json()["data"]["orgId"])
        project = await client.post(
            f"/api/v1/organizations/{org_id}/projects",
            json={"title": "Repeat Fixture Project"},
        )
        assert project.status_code == 201, project.text
        project_id = UUID(project.json()["data"]["projectId"])
        path = f"/e2e/organizations/{org_id}/projects/{project_id}/evidence-fixture"

        first = await client.post(path)
        repeated = await client.post(path)
        listed = await client.get(
            f"/api/v1/organizations/{org_id}/projects/{project_id}/clearance-items"
        )

    assert first.status_code == 201, first.text
    assert repeated.status_code == 409
    assert repeated.json()["error"]["code"] == "conflict"
    assert listed.status_code == 200, listed.text
    assert len(listed.json()["data"]) == 2



async def test_importing_e2e_support_preserves_disabled_app_composition() -> None:
    import os
    import subprocess

    script = """
from clearcut.main import app

assert app.state.job_dispatcher.mode == "disabled"
before = (
    app.state.job_dispatcher,
    app.state.job_runner,
    app.state.run_detection_job,
    app.state.candidate_repository,
    dict(app.dependency_overrides),
)
import e2e_api  # noqa: F401

after = (
    app.state.job_dispatcher,
    app.state.job_runner,
    app.state.run_detection_job,
    app.state.candidate_repository,
    dict(app.dependency_overrides),
)
assert after == before, "importing E2E support mutated the disabled production app"
"""
    environment = os.environ.copy()
    environment["CLEARCUT_JOB_DISPATCH_MODE"] = "disabled"
    python_path = [
        str(ROOT / "services" / "api" / "src"),
        str(SUPPORT_DIR),
    ]
    if environment.get("PYTHONPATH"):
        python_path.append(environment["PYTHONPATH"])
    environment["PYTHONPATH"] = os.pathsep.join(python_path)

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr

import pytest
from clearcut.init_db import init_and_seed_db
from clearcut.main import app
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_script_upload_and_pipeline_flow():
    await init_and_seed_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Register user
        reg_res = await client.post(
            "/api/v1/users",
            json={"name": "Script Writer", "email": "writer@studio.com", "password": "Password123!"},
        )
        assert reg_res.status_code == 201

        # Create org & project
        org_res = await client.post(
            "/api/v1/organizations",
            json={"name": "Writer Studio", "slug": "writer-studio"},
        )
        org_id = org_res.json()["data"]["orgId"]

        proj_res = await client.post(
            f"/api/v1/organizations/{org_id}/projects",
            json={"title": "Script Project", "description": "Testing scripts"},
        )
        proj_id = proj_res.json()["data"]["projectId"]

        # Create upload capability
        cap_res = await client.post(
            f"/api/v1/organizations/{org_id}/projects/{proj_id}/upload-capabilities",
            json={"filename": "screenplay.fountain", "contentType": "text/plain"},
        )
        assert cap_res.status_code == 201
        cap_data = cap_res.json()["data"]
        cap_id = cap_data["capabilityId"]

        # Finalize upload
        files = {
            "file": (
                "screenplay.fountain",
                b"Title: Pipeline\n\nEXT. STREET - DAY\n\nA test scene.",
                "text/plain",
            )
        }
        fin_res = await client.post(
            f"/api/v1/organizations/{org_id}/projects/{proj_id}/"
            f"import-artifacts/{cap_id}:finalize",
            headers={"X-Upload-Nonce": cap_data["nonce"]},
            files=files,
        )
        assert fin_res.status_code == 200
        assert fin_res.json()["data"]["status"] == "ready_to_parse"

        # Create paste import through the canonical persistent boundary.
        paste_res = await client.post(
            f"/api/v1/organizations/{org_id}/projects/{proj_id}/paste-imports",
            json={
                "rawText": "EXT. STREET - DAY\nJohn walks down the street.",
                "format": "fountain",
            },
        )
        assert paste_res.status_code == 201
        assert paste_res.json()["data"]["status"] == "ready_to_parse"

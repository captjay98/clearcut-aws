import pytest
from httpx import ASGITransport, AsyncClient
from clearcut.init_db import init_and_seed_db
from clearcut.main import app


@pytest.mark.asyncio
async def test_tenant_isolation_and_cross_organization_denial():
    await init_and_seed_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Register User A
        res_a = await client.post(
            "/api/v1/users",
            json={"name": "Alice User", "email": "alice@studio-a.com", "password": "Password123!"},
        )
        assert res_a.status_code == 201
        cookie_a = res_a.cookies.get("__Host-clearcut_session")

        # Register User B
        res_b = await client.post(
            "/api/v1/users",
            json={"name": "Bob User", "email": "bob@studio-b.com", "password": "Password123!"},
        )
        assert res_b.status_code == 201
        cookie_b = res_b.cookies.get("__Host-clearcut_session")

        # User A creates Org A
        client.cookies.set("__Host-clearcut_session", cookie_a)
        org_a_res = await client.post(
            "/api/v1/organizations",
            json={"name": "Studio Alpha", "slug": "studio-alpha"},
        )
        assert org_a_res.status_code == 201
        org_a_id = org_a_res.json()["data"]["orgId"]

        # User A creates a project in Org A
        proj_res = await client.post(
            f"/api/v1/organizations/{org_a_id}/projects",
            json={"title": "Alpha Secret Project", "description": "Top secret"},
        )
        assert proj_res.status_code == 201
        proj_id = proj_res.json()["data"]["projectId"]

        # User B creates Org B
        client.cookies.set("__Host-clearcut_session", cookie_b)
        org_b_res = await client.post(
            "/api/v1/organizations",
            json={"name": "Studio Beta", "slug": "studio-beta"},
        )
        assert org_b_res.status_code == 201

        # User B attempts to access Org A projects -> MUST BE FORBIDDEN (403 or 404)
        denied_projects = await client.get(f"/api/v1/organizations/{org_a_id}/projects")
        assert denied_projects.status_code in [403, 404]

        # User B attempts to access Org A specific project -> MUST BE FORBIDDEN (403 or 404)
        denied_proj = await client.get(f"/api/v1/organizations/{org_a_id}/projects/{proj_id}")
        assert denied_proj.status_code in [403, 404]


@pytest.mark.asyncio
async def test_last_owner_protection():
    await init_and_seed_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Register User
        res = await client.post(
            "/api/v1/users",
            json={"name": "Sole Owner", "email": "sole_owner@studio.com", "password": "Password123!"},
        )
        assert res.status_code == 201
        cookie = res.cookies.get("__Host-clearcut_session")
        client.cookies.set("__Host-clearcut_session", cookie)

        # Create Org
        org_res = await client.post(
            "/api/v1/organizations",
            json={"name": "Single Owner Studio", "slug": "single-owner-studio"},
        )
        assert org_res.status_code == 201
        org_id = org_res.json()["data"]["orgId"]

        # Get memberships
        memberships_res = await client.get(f"/api/v1/organizations/{org_id}/memberships")
        assert memberships_res.status_code == 200
        membership_id = memberships_res.json()["data"][0]["membershipId"]

        # Try to demote the last active owner -> MUST FAIL 400
        demote_res = await client.post(
            f"/api/v1/organizations/{org_id}/memberships/{membership_id}:changeRole",
            json={"role": "reviewer"},
        )
        assert demote_res.status_code == 400
        assert "last active owner" in demote_res.json()["detail"].lower()

        # Try to deactivate the last active owner -> MUST FAIL 400
        deact_res = await client.post(
            f"/api/v1/organizations/{org_id}/memberships/{membership_id}:deactivate",
        )
        assert deact_res.status_code == 400
        assert "last active owner" in deact_res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_invitation_lifecycle():
    await init_and_seed_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # User 1 registers and creates org
        res1 = await client.post(
            "/api/v1/users",
            json={"name": "Inviter User", "email": "inviter@studio.com", "password": "Password123!"},
        )
        cookie1 = res1.cookies.get("__Host-clearcut_session")
        client.cookies.set("__Host-clearcut_session", cookie1)

        org_res = await client.post(
            "/api/v1/organizations",
            json={"name": "Invite Studio", "slug": "invite-studio"},
        )
        org_id = org_res.json()["data"]["orgId"]

        # Invite user 2
        invite_res = await client.post(
            f"/api/v1/organizations/{org_id}/invitations",
            json={"email": "invitee@studio.com", "role": "reviewer"},
        )
        assert invite_res.status_code == 201
        token = invite_res.json()["data"]["token"]

        # User 2 registers
        res2 = await client.post(
            "/api/v1/users",
            json={"name": "Invitee User", "email": "invitee@studio.com", "password": "Password123!"},
        )
        cookie2 = res2.cookies.get("__Host-clearcut_session")
        client.cookies.set("__Host-clearcut_session", cookie2)

        # User 2 accepts invitation
        accept_res = await client.post(f"/api/v1/invitations/{token}:accept")
        assert accept_res.status_code == 200
        assert accept_res.json()["data"]["role"] == "reviewer"

        # User 2 can now access organization projects
        projects_res = await client.get(f"/api/v1/organizations/{org_id}/projects")
        assert projects_res.status_code == 200

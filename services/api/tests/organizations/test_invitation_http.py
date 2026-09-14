"""HTTP-level invitation acceptance security.

The domain model rejects a wrong-email actor, but the HTTP route previously
granted membership straight from the authenticated session. These tests pin
the route to the same rule the domain enforces.
"""

import pytest
from clearcut.init_db import init_and_seed_db
from clearcut.main import app
from httpx import ASGITransport, AsyncClient


async def _register_and_create_org(client: AsyncClient, email: str) -> tuple[str, str]:
    registration = await client.post(
        "/api/v1/users",
        json={"name": "Owner", "email": email, "password": "Password123!"},
    )
    assert registration.status_code == 201
    cookie = registration.cookies.get("clearcut_session")
    assert cookie is not None
    client.cookies.set("clearcut_session", cookie)
    org = await client.post(
        "/api/v1/organizations",
        json={"name": "Invitation Studio", "slug": "invitation-studio"},
    )
    assert org.status_code == 201
    return cookie, org.json()["data"]["orgId"]


@pytest.mark.asyncio
async def test_acceptance_rejects_mismatched_email_without_writes():
    await init_and_seed_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        owner_cookie, org_id = await _register_and_create_org(client, "owner@studio.com")

        invitation = await client.post(
            f"/api/v1/organizations/{org_id}/invitations",
            json={"email": "intended@studio.com", "role": "admin"},
        )
        assert invitation.status_code == 201
        token = invitation.json()["data"]["token"]

        attacker = await client.post(
            "/api/v1/users",
            json={
                "name": "Other Account",
                "email": "different@studio.com",
                "password": "Password123!",
            },
        )
        assert attacker.status_code == 201
        client.cookies.set(
            "clearcut_session", attacker.cookies.get("clearcut_session")
        )

        acceptance = await client.post(f"/api/v1/invitations/{token}:accept")
        assert acceptance.status_code in (400, 403)

        # The wrong actor gains no access to the organization.
        denied = await client.get(f"/api/v1/organizations/{org_id}/projects")
        assert denied.status_code in (403, 404)

        # The invitation survives for its intended recipient.
        client.cookies.set("clearcut_session", owner_cookie)
        intended = await client.post(
            "/api/v1/users",
            json={
                "name": "Intended Member",
                "email": "intended@studio.com",
                "password": "Password123!",
            },
        )
        assert intended.status_code == 201
        client.cookies.set(
            "clearcut_session", intended.cookies.get("clearcut_session")
        )
        retry = await client.post(f"/api/v1/invitations/{token}:accept")
        assert retry.status_code == 200
        assert retry.json()["data"]["role"] == "admin"


@pytest.mark.asyncio
async def test_acceptance_consumes_token_once():
    await init_and_seed_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await _register_and_create_org(client, "owner-once@studio.com")
        org_id = (
            await client.get("/api/v1/organizations")
        ).json()["data"][0]["orgId"]

        invitation = await client.post(
            f"/api/v1/organizations/{org_id}/invitations",
            json={"email": "member-once@studio.com", "role": "reviewer"},
        )
        assert invitation.status_code == 201
        token = invitation.json()["data"]["token"]

        member = await client.post(
            "/api/v1/users",
            json={
                "name": "Member",
                "email": "member-once@studio.com",
                "password": "Password123!",
            },
        )
        client.cookies.set("clearcut_session", member.cookies.get("clearcut_session"))

        first = await client.post(f"/api/v1/invitations/{token}:accept")
        assert first.status_code == 200

        second = await client.post(f"/api/v1/invitations/{token}:accept")
        assert second.status_code == 404

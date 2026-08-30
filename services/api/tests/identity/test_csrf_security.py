import pytest
from clearcut.main import app
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_cross_origin_state_mutating_requests_rejected():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Request with untrusted origin
        response = await client.post(
            "/api/v1/sessions",
            headers={"Origin": "https://malicious-site.com"},
            json={"email": "attacker@evil.com", "password": "password"}
        )
        assert response.status_code in {400, 403}

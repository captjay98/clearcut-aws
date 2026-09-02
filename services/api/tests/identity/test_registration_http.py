import pytest
import sqlalchemy as sa
from clearcut.database import session_scope
from clearcut.identity.adapters.local_identity import Argon2idIdentityProvider
from clearcut.init_db import init_and_seed_db
from clearcut.main import app
from httpx import ASGITransport, AsyncClient


def _client(base_url: str = "http://test") -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url=base_url,
        headers={"origin": base_url},
    )


@pytest.mark.asyncio
async def test_local_registration_persists_credentials_and_uses_local_cookie() -> None:
    await init_and_seed_db(seed_if_empty=False)
    password = "CorrectHorse123!"

    async with _client() as client:
        response = await client.post(
            "/api/v1/users",
            json={
                "name": "Local Producer",
                "email": "LOCAL.PRODUCER@example.com",
                "password": password,
            },
        )

        assert response.status_code == 201, response.text
        cookie_header = response.headers["set-cookie"]
        assert cookie_header.startswith("clearcut_session=")
        assert "HttpOnly" in cookie_header
        assert "SameSite=lax" in cookie_header
        assert "Path=/" in cookie_header
        assert "Secure" not in cookie_header
        assert "__Host-clearcut_session" not in cookie_header

        context = await client.get("/api/v1/session-context")
        assert context.status_code == 200
        assert context.json()["data"]["authenticated"] is True
        assert context.json()["data"]["email"] == "local.producer@example.com"

        token = client.cookies.get("clearcut_session")
        assert token

    async with session_scope() as session:
        row = (
            (
                await session.execute(
                    sa.text(
                        "SELECT u.email, c.password_hash "
                        "FROM users u JOIN local_credentials c ON c.user_id = u.id "
                        "WHERE u.email = :email"
                    ),
                    {"email": "local.producer@example.com"},
                )
            )
            .mappings()
            .one()
        )
    assert row["password_hash"] != password
    assert Argon2idIdentityProvider().verify_password(row["password_hash"], password)

    async with _client() as reloaded_client:
        reloaded_client.cookies.set("clearcut_session", token)
        persisted_context = await reloaded_client.get("/api/v1/session-context")
        assert persisted_context.status_code == 200
        assert persisted_context.json()["data"]["authenticated"] is True

    async with _client() as bearer_client:
        bearer_context = await bearer_client.get(
            "/api/v1/session-context",
            headers={"authorization": f"Bearer {token}"},
        )
        assert bearer_context.status_code == 200
        assert bearer_context.json()["data"]["authenticated"] is True


@pytest.mark.asyncio
async def test_registration_rejects_duplicate_and_short_password_with_typed_errors() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with _client() as client:
        created = await client.post(
            "/api/v1/users",
            json={
                "name": "Duplicate User",
                "email": "duplicate@example.com",
                "password": "Password123!",
            },
        )
        assert created.status_code == 201

        duplicate = await client.post(
            "/api/v1/users",
            json={
                "name": "Duplicate User",
                "email": " DUPLICATE@example.com ",
                "password": "Password123!",
            },
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["error"]["code"] == "conflict"
        assert duplicate.headers["x-request-id"]

        short_password = await client.post(
            "/api/v1/users",
            json={
                "name": "Short Password",
                "email": "short@example.com",
                "password": "short",
            },
        )
        assert short_password.status_code == 422
        assert short_password.json()["error"]["code"] == "validation_failed"
        assert short_password.headers["x-request-id"]


@pytest.mark.asyncio
async def test_local_logout_revokes_and_clears_the_active_session() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with _client() as client:
        created = await client.post(
            "/api/v1/users",
            json={
                "name": "Logout User",
                "email": "logout@example.com",
                "password": "Password123!",
            },
        )
        token = client.cookies.get("clearcut_session")
        assert created.status_code == 201
        assert token

        logout = await client.delete("/api/v1/sessions/current")
        assert logout.status_code == 204
        assert any(
            header.startswith("clearcut_session=") and "Max-Age=0" in header
            for header in logout.headers.get_list("set-cookie")
        )

        context = await client.get("/api/v1/session-context")
        assert context.status_code == 200
        assert context.json()["data"] == {
            "authenticated": False,
            "userId": None,
            "email": None,
            "activeOrgId": None,
            "role": None,
        }

    async with _client() as replay_client:
        replay_client.cookies.set("clearcut_session", token)
        replay = await replay_client.get("/api/v1/session-context")
        assert replay.status_code == 200
        assert replay.json()["data"]["authenticated"] is False


@pytest.mark.asyncio
async def test_https_registration_uses_secure_host_cookie_and_logout_clears_it() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with _client("https://test") as client:
        created = await client.post(
            "/api/v1/users",
            json={
                "name": "Secure Producer",
                "email": "secure@example.com",
                "password": "Password123!",
            },
        )

        assert created.status_code == 201, created.text
        cookie_header = created.headers["set-cookie"]
        assert cookie_header.startswith("__Host-clearcut_session=")
        assert "Secure" in cookie_header
        assert "HttpOnly" in cookie_header
        assert "Path=/" in cookie_header
        assert "Domain=" not in cookie_header

        context = await client.get("/api/v1/session-context")
        assert context.status_code == 200
        assert context.json()["data"]["authenticated"] is True

        logout = await client.delete("/api/v1/sessions/current")
        assert logout.status_code == 204
        assert any(
            header.startswith("__Host-clearcut_session=")
            and "Max-Age=0" in header
            and "Secure" in header
            for header in logout.headers.get_list("set-cookie")
        )


@pytest.mark.asyncio
async def test_session_cookie_name_is_restricted_to_the_request_scheme() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with _client() as local_client:
        local_registration = await local_client.post(
            "/api/v1/users",
            json={
                "name": "Local Cookie User",
                "email": "local-cookie@example.com",
                "password": "Password123!",
            },
        )
        assert local_registration.status_code == 201
        local_token = local_client.cookies.get("clearcut_session")
        assert local_token

    async with _client("https://test") as secure_client:
        secure_registration = await secure_client.post(
            "/api/v1/users",
            json={
                "name": "Secure Cookie User",
                "email": "secure-cookie@example.com",
                "password": "Password123!",
            },
        )
        assert secure_registration.status_code == 201
        secure_token = secure_client.cookies.get("__Host-clearcut_session")
        assert secure_token

    async with _client("https://test") as https_client:
        https_client.cookies.set("clearcut_session", local_token)
        https_context = await https_client.get("/api/v1/session-context")
        assert https_context.status_code == 200
        assert https_context.json()["data"]["authenticated"] is False

    async with _client() as http_client:
        http_client.cookies.set("__Host-clearcut_session", secure_token)
        http_context = await http_client.get("/api/v1/session-context")
        assert http_context.status_code == 200
        assert http_context.json()["data"]["authenticated"] is False


@pytest.mark.asyncio
async def test_bearer_precedes_cookie_and_logout_revokes_only_bearer_session() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with _client() as registration_client:
        cookie_user = await registration_client.post(
            "/api/v1/users",
            json={
                "name": "Cookie User",
                "email": "cookie-principal@example.com",
                "password": "Password123!",
            },
        )
        assert cookie_user.status_code == 201
        cookie_token = registration_client.cookies.get("clearcut_session")
        assert cookie_token

        bearer_user = await registration_client.post(
            "/api/v1/users",
            json={
                "name": "Bearer User",
                "email": "bearer-principal@example.com",
                "password": "Password123!",
            },
        )
        assert bearer_user.status_code == 201
        bearer_token = registration_client.cookies.get("clearcut_session")
        assert bearer_token

    async with _client() as mixed_client:
        mixed_client.cookies.set("clearcut_session", cookie_token)
        mixed_context = await mixed_client.get(
            "/api/v1/session-context",
            headers={"authorization": f"Bearer {bearer_token}"},
        )
        assert mixed_context.status_code == 200
        assert mixed_context.json()["data"]["email"] == "bearer-principal@example.com"

        logout = await mixed_client.delete(
            "/api/v1/sessions/current",
            headers={"authorization": f"Bearer {bearer_token}"},
        )
        assert logout.status_code == 204

    async with _client() as bearer_replay_client:
        bearer_replay = await bearer_replay_client.get(
            "/api/v1/session-context",
            headers={"authorization": f"Bearer {bearer_token}"},
        )
        assert bearer_replay.json()["data"]["authenticated"] is False

    async with _client() as cookie_replay_client:
        cookie_replay_client.cookies.set("clearcut_session", cookie_token)
        cookie_replay = await cookie_replay_client.get("/api/v1/session-context")
        assert cookie_replay.json()["data"]["authenticated"] is True
        assert cookie_replay.json()["data"]["email"] == "cookie-principal@example.com"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "malicious_origin",
    ["https://test.attacker.example", "http://localhost:9999"],
)
async def test_identity_mutations_reject_untrusted_origins(
    malicious_origin: str,
) -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with _client() as client:
        registration = await client.post(
            "/api/v1/users",
            json={
                "name": "Rejected Origin",
                "email": "rejected-origin@example.com",
                "password": "Password123!",
            },
            headers={"origin": malicious_origin},
        )
        login = await client.post(
            "/api/v1/sessions",
            json={
                "email": "rejected-origin@example.com",
                "password": "Password123!",
            },
            headers={"origin": malicious_origin},
        )
        logout = await client.delete(
            "/api/v1/sessions/current",
            headers={"origin": malicious_origin},
        )

    for response in (registration, login, logout):
        assert response.status_code == 403, response.text
        assert response.json()["error"]["code"] == "permission_denied"

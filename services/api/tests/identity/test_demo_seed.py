import pytest
import sqlalchemy as sa
from clearcut.database import session_scope
from clearcut.init_db import _load_seed, init_and_seed_db
from clearcut.main import app
from httpx import ASGITransport, AsyncClient

seed = _load_seed()
TABLE_COUNT_SQL = {
    "users": "SELECT count(*) FROM users",
    "sessions": "SELECT count(*) FROM sessions",
    "organizations": "SELECT count(*) FROM organizations",
    "projects": "SELECT count(*) FROM projects",
    "clearance_items": "SELECT count(*) FROM clearance_items",
}


async def _register_real_user(email: str) -> str:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"origin": "http://test"},
    ) as client:
        response = await client.post(
            "/api/v1/users",
            json={
                "name": "Real User",
                "email": email,
                "password": "Password123!",
            },
        )
        assert response.status_code == 201, response.text
        token = client.cookies.get("clearcut_session")
        assert token
        return token


async def _row_count(table_name: str) -> int:
    async with session_scope() as session:
        result = await session.execute(sa.text(TABLE_COUNT_SQL[table_name]))
        return int(result.scalar_one())


@pytest.mark.asyncio
async def test_demo_seed_is_disabled_without_explicit_environment_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CLEARCUT_SEED_DEMO", raising=False)
    await init_and_seed_db(seed_if_empty=False)
    await _register_real_user("preserved-without-seed@example.com")

    users_before = await _row_count("users")
    sessions_before = await _row_count("sessions")
    seeded = await seed()

    assert seeded is False
    assert await _row_count("users") == users_before
    assert await _row_count("sessions") == sessions_before
    async with session_scope() as session:
        demo_org_count = (
            await session.execute(
                sa.text("SELECT count(*) FROM organizations WHERE slug = 'northlight'")
            )
        ).scalar_one()
    assert demo_org_count == 0


@pytest.mark.asyncio
async def test_enabled_demo_seed_is_idempotent_and_preserves_real_auth_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLEARCUT_SEED_DEMO", "true")
    await init_and_seed_db(seed_if_empty=False)
    token = await _register_real_user("preserved-with-demo@example.com")

    first_seeded = await seed()
    first_counts = {
        table_name: await _row_count(table_name)
        for table_name in ("users", "sessions", "organizations", "projects", "clearance_items")
    }
    second_seeded = await seed()
    second_counts = {
        table_name: await _row_count(table_name)
        for table_name in ("users", "sessions", "organizations", "projects", "clearance_items")
    }

    assert first_seeded is True
    assert second_seeded is False
    assert second_counts == first_counts

    async with session_scope() as session:
        current_demo_scripts = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM scripts s JOIN projects p ON p.id = s.project_id "
                    "JOIN organizations o ON o.id = p.org_id "
                    "WHERE o.slug = 'northlight' AND s.current_slot = 'current'"
                )
            )
        ).scalar_one()
    assert current_demo_scripts == 1

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"authorization": f"Bearer {token}"},
    ) as client:
        context = await client.get("/api/v1/session-context")
    assert context.status_code == 200
    assert context.json()["data"]["authenticated"] is True
    assert context.json()["data"]["email"] == "preserved-with-demo@example.com"

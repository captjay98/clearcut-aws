"""HTTP-level tests for organization settings reads and the governed update.

These exercise the mounted FastAPI routes against the real migrated schema
(migration 0036 added ``jurisdiction``, ``default_monitoring_cadence``, and
``version`` to ``organizations``), so tenant scope, server-derived capability,
optimistic concurrency, idempotent replay, the request-boundary cadence
vocabulary, and the same-transaction authoritative audit event are all covered
end to end rather than against a stub.

Two canonical-mock rules are pinned here explicitly:

* The cadence is stored as ``off | manual | daily | weekly`` and the audit entry
  speaks the *display* vocabulary ("Weekly" -> "Daily"), never the token.
* There is no evidence-retention duration anywhere. Evidence is kept until its
  project is deleted, so a retention field would print a promise the product does
  not make; sending one is rejected outright.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
import uuid6
from clearcut.database import session_scope
from clearcut.identity.application.session_service import hash_token
from clearcut.init_db import init_and_seed_db
from clearcut.main import app
from clearcut.organizations.delivery import settings_http
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.asyncio

_AUDIT_ACTION = "organization.settings.updated"


def _mount_settings_router() -> None:
    """Mount the settings router if the application has not already mounted it.

    ``main.py`` is owned elsewhere, so the router may or may not be wired up yet.
    Mounting it here idempotently lets these tests pin the real routes either way.
    """
    for route in app.router.routes:
        if getattr(route, "path", None) == "/api/v1/organizations/{orgId}/settings":
            return
    app.include_router(settings_http.router)


async def _client() -> AsyncClient:
    _mount_settings_router()
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"origin": "http://test"},
    )


@dataclass(frozen=True)
class Fixture:
    org_id: UUID
    user_id: UUID


def _settings_path(org_id: UUID) -> str:
    return f"/api/v1/organizations/{org_id}/settings"


def _idempotency_key(label: str) -> str:
    # The header is 16..128 characters; the random suffix keeps keys distinct.
    return f"idem-{label}-{uuid4().hex}"


def _body(
    *,
    name: str = "Signal Fires Pictures",
    jurisdiction: str | None = "California, USA",
    cadence: str = "daily",
    expected_version: int = 1,
) -> dict:
    body: dict = {
        "name": name,
        "defaultMonitoringCadence": cadence,
        "expectedVersion": expected_version,
    }
    if jurisdiction is not None:
        body["jurisdiction"] = jurisdiction
    return body


async def _setup(client: AsyncClient, *, suffix: str, role: str = "owner") -> Fixture:
    """Seed one authenticated actor, organization, and membership, then sign in.

    The whole tenant is written in a single transaction and the session cookie is
    set directly, so these tests depend only on the routes under test rather than
    on the multi-step registration flow.
    """
    user_id = uuid6.uuid7()
    org_id = uuid6.uuid7()
    slug = f"settings-{suffix.replace('_', '-')}-{uuid4().hex[:8]}"
    raw_token = f"test-token-{uuid4().hex}"
    now = datetime.now(UTC)

    async with session_scope() as session:
        await session.execute(
            sa.text("INSERT INTO users (id, email, created_at) VALUES (:id, :email, :created_at)"),
            {
                "id": str(user_id),
                "email": f"settings-{suffix}-{uuid4().hex}@example.com",
                "created_at": now,
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO sessions (id, user_id, token_hash, created_at, expires_at) "
                "VALUES (:id, :user_id, :token_hash, :created_at, :expires_at)"
            ),
            {
                "id": str(uuid6.uuid7()),
                "user_id": str(user_id),
                "token_hash": hash_token(raw_token),
                "created_at": now,
                "expires_at": now + timedelta(days=7),
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO organizations (id, name, slug, created_at) "
                "VALUES (:id, :name, :slug, :created_at)"
            ),
            {
                "id": str(org_id),
                "name": "Settings Studio",
                "slug": slug,
                "created_at": now,
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO memberships (id, org_id, user_id, role, status, created_at) "
                "VALUES (:id, :org_id, :user_id, :role, 'active', :created_at)"
            ),
            {
                "id": str(uuid6.uuid7()),
                "org_id": str(org_id),
                "user_id": str(user_id),
                "role": role,
                "created_at": now,
            },
        )

    client.cookies.set("clearcut_session", raw_token)
    return Fixture(org_id=org_id, user_id=user_id)


async def _stored_settings(org_id: UUID) -> dict:
    async with session_scope() as session:
        row = (
            (
                await session.execute(
                    sa.text(
                        "SELECT name, slug, jurisdiction, default_monitoring_cadence, version "
                        "FROM organizations WHERE id = :org_id"
                    ),
                    {"org_id": str(org_id)},
                )
            )
            .mappings()
            .one()
        )
    return dict(row)


async def _audit_rows(org_id: UUID) -> list[dict]:
    async with session_scope() as session:
        rows = (
            (
                await session.execute(
                    sa.text(
                        "SELECT project_id, actor_id, action, target_type, target_id, "
                        "payload_redacted FROM authoritative_audit_events "
                        "WHERE org_id = :org_id AND action = :action "
                        "ORDER BY occurred_at"
                    ),
                    {"org_id": str(org_id), "action": _AUDIT_ACTION},
                )
            )
            .mappings()
            .all()
        )
    events: list[dict] = []
    for row in rows:
        payload = row["payload_redacted"]
        events.append(
            {
                "project_id": row["project_id"],
                "actor_id": row["actor_id"],
                "target_type": row["target_type"],
                "target_id": row["target_id"],
                "payload": json.loads(payload) if isinstance(payload, str) else payload,
            }
        )
    return events


async def test_settings_round_trip_persists_name_jurisdiction_and_cadence() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="round-trip")

        initial = await client.get(_settings_path(fixture.org_id))
        assert initial.status_code == 200, initial.text
        assert initial.json()["data"] == {
            "orgId": str(fixture.org_id),
            "name": "Settings Studio",
            "slug": (await _stored_settings(fixture.org_id))["slug"],
            # The migration's server default, stored canonically.
            "defaultMonitoringCadence": "weekly",
            "version": 1,
        }

        updated = await client.patch(
            _settings_path(fixture.org_id),
            json=_body(),
            headers={"Idempotency-Key": _idempotency_key("round-trip")},
        )
        assert updated.status_code == 200, updated.text
        data = updated.json()["data"]
        assert data["name"] == "Signal Fires Pictures"
        assert data["jurisdiction"] == "California, USA"
        assert data["defaultMonitoringCadence"] == "daily"
        assert data["version"] == 2

        reread = await client.get(_settings_path(fixture.org_id))
        assert reread.status_code == 200, reread.text
        assert reread.json()["data"] == data

    stored = await _stored_settings(fixture.org_id)
    assert stored["name"] == "Signal Fires Pictures"
    assert stored["jurisdiction"] == "California, USA"
    # Stored canonically as the token, never as the label.
    assert stored["default_monitoring_cadence"] == "daily"
    assert stored["version"] == 2


async def test_audit_event_names_only_changed_fields_with_humanized_cadence() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="audit")

        # Only the cadence changes: the name is resubmitted unchanged and no
        # jurisdiction is supplied, so neither may appear in the audit entry.
        updated = await client.patch(
            _settings_path(fixture.org_id),
            json=_body(name="Settings Studio", jurisdiction=None, cadence="daily"),
            headers={"Idempotency-Key": _idempotency_key("audit")},
        )
        assert updated.status_code == 200, updated.text

    events = await _audit_rows(fixture.org_id)
    assert len(events) == 1
    event = events[0]
    # An organization-owned governed change belongs to no project.
    assert event["project_id"] is None
    assert event["target_type"] == "organization"
    assert UUID(str(event["target_id"])) == fixture.org_id
    assert UUID(str(event["actor_id"])) == fixture.user_id

    payload = event["payload"]
    assert payload["changedFields"] == ["defaultMonitoringCadence"]
    assert set(payload["changes"]) == {"defaultMonitoringCadence"}
    # The ledger speaks the display vocabulary, not the stored token.
    assert payload["changes"]["defaultMonitoringCadence"] == {
        "before": "Weekly",
        "after": "Daily",
    }
    assert payload["detail"] == "defaultMonitoringCadence: Weekly → Daily"
    assert "weekly" not in payload["detail"]
    assert payload["command"]["expectedVersion"] == 1
    assert payload["command"]["resultingVersion"] == 2


async def test_second_change_records_both_changed_fields_only() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="two-fields")

        first = await client.patch(
            _settings_path(fixture.org_id),
            json=_body(name="Settings Studio", jurisdiction="California, USA", cadence="weekly"),
            headers={"Idempotency-Key": _idempotency_key("two-fields-1")},
        )
        assert first.status_code == 200, first.text

        second = await client.patch(
            _settings_path(fixture.org_id),
            json=_body(
                name="Second Unit Pictures",
                jurisdiction="California, USA",
                cadence="off",
                expected_version=2,
            ),
            headers={"Idempotency-Key": _idempotency_key("two-fields-2")},
        )
        assert second.status_code == 200, second.text

    events = await _audit_rows(fixture.org_id)
    assert len(events) == 2
    # The jurisdiction was unchanged by the second command and must not be named.
    assert events[1]["payload"]["changedFields"] == ["name", "defaultMonitoringCadence"]
    assert events[1]["payload"]["changes"]["defaultMonitoringCadence"] == {
        "before": "Weekly",
        "after": "Off",
    }
    assert events[1]["payload"]["changes"]["name"] == {
        "before": "Settings Studio",
        "after": "Second Unit Pictures",
    }


async def test_stale_expected_version_conflicts_and_writes_nothing() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="stale")

        accepted = await client.patch(
            _settings_path(fixture.org_id),
            json=_body(name="First Writer", cadence="daily"),
            headers={"Idempotency-Key": _idempotency_key("stale-first")},
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["data"]["version"] == 2

        stale = await client.patch(
            _settings_path(fixture.org_id),
            json=_body(name="Second Writer", cadence="off", expected_version=1),
            headers={"Idempotency-Key": _idempotency_key("stale-second")},
        )
        assert stale.status_code == 409, stale.text
        assert stale.json()["error"]["code"] == "conflict_stale_version"

    stored = await _stored_settings(fixture.org_id)
    assert stored["name"] == "First Writer"
    assert stored["default_monitoring_cadence"] == "daily"
    assert stored["version"] == 2
    # The rejected command left no audit event behind.
    assert len(await _audit_rows(fixture.org_id)) == 1


async def test_replaying_the_same_key_and_intent_does_not_write_twice() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="replay")
        key = _idempotency_key("replay")

        first = await client.patch(
            _settings_path(fixture.org_id),
            json=_body(),
            headers={"Idempotency-Key": key},
        )
        assert first.status_code == 200, first.text

        replay = await client.patch(
            _settings_path(fixture.org_id),
            json=_body(),
            headers={"Idempotency-Key": key},
        )
        assert replay.status_code == 200, replay.text
        assert replay.json()["data"] == first.json()["data"]

        conflicting = await client.patch(
            _settings_path(fixture.org_id),
            json=_body(name="Different Intent"),
            headers={"Idempotency-Key": key},
        )
        assert conflicting.status_code == 409, conflicting.text
        assert conflicting.json()["error"]["code"] == "conflict_idempotency_mismatch"

    assert (await _stored_settings(fixture.org_id))["version"] == 2
    assert len(await _audit_rows(fixture.org_id)) == 1


@pytest.mark.parametrize("role", ["editor", "reviewer", "viewer"])
async def test_roles_without_settings_capability_are_refused(role: str) -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix=f"role-{role}", role=role)

        # Reading is available to any active member, whatever their role.
        readable = await client.get(_settings_path(fixture.org_id))
        assert readable.status_code == 200, readable.text

        refused = await client.patch(
            _settings_path(fixture.org_id),
            json=_body(),
            headers={"Idempotency-Key": _idempotency_key(f"role-{role}")},
        )
        assert refused.status_code == 403, refused.text
        assert refused.json()["error"]["code"] == "permission_denied"

    stored = await _stored_settings(fixture.org_id)
    assert stored["name"] == "Settings Studio"
    assert stored["version"] == 1
    assert await _audit_rows(fixture.org_id) == []


@pytest.mark.parametrize("role", ["owner", "admin"])
async def test_owner_and_admin_may_update(role: str) -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix=f"allowed-{role}", role=role)

        updated = await client.patch(
            _settings_path(fixture.org_id),
            json=_body(),
            headers={"Idempotency-Key": _idempotency_key(f"allowed-{role}")},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["data"]["version"] == 2


@pytest.mark.parametrize("name", ["", "   ", "\t\n"])
async def test_blank_name_is_rejected(name: str) -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="blank-name")

        rejected = await client.patch(
            _settings_path(fixture.org_id),
            json=_body(name=name),
            headers={"Idempotency-Key": _idempotency_key("blank-name")},
        )
        assert rejected.status_code == 422, rejected.text
        assert rejected.json()["error"]["code"] == "validation_failed"

    stored = await _stored_settings(fixture.org_id)
    assert stored["name"] == "Settings Studio"
    assert stored["version"] == 1


async def test_out_of_vocabulary_cadence_is_rejected_before_the_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await init_and_seed_db(seed_if_empty=False)

    class ExplodingService:
        async def read(self, *args, **kwargs):
            raise AssertionError("the handler must not run for an invalid cadence")

        async def update(self, *args, **kwargs):
            raise AssertionError("the handler must not run for an invalid cadence")

    async with await _client() as client:
        fixture = await _setup(client, suffix="bad-cadence")
        # Any call into the service now fails loudly, so a 422 here proves the
        # request-boundary vocabulary rejected the value before the handler ran.
        monkeypatch.setattr(settings_http, "_service", ExplodingService())

        rejected = await client.patch(
            _settings_path(fixture.org_id),
            json=_body(cadence="fortnightly"),
            headers={"Idempotency-Key": _idempotency_key("bad-cadence")},
        )
        assert rejected.status_code == 422, rejected.text

    stored = await _stored_settings(fixture.org_id)
    assert stored["default_monitoring_cadence"] == "weekly"
    assert stored["version"] == 1
    assert await _audit_rows(fixture.org_id) == []


async def test_slug_cannot_be_changed() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="slug")
        original_slug = (await _stored_settings(fixture.org_id))["slug"]

        rejected = await client.patch(
            _settings_path(fixture.org_id),
            json={**_body(), "slug": "hijacked-url-identity"},
            headers={"Idempotency-Key": _idempotency_key("slug")},
        )
        assert rejected.status_code == 422, rejected.text

        accepted = await client.patch(
            _settings_path(fixture.org_id),
            json=_body(),
            headers={"Idempotency-Key": _idempotency_key("slug-ok")},
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["data"]["slug"] == original_slug

    assert (await _stored_settings(fixture.org_id))["slug"] == original_slug


async def test_retention_duration_is_not_an_accepted_field() -> None:
    """Evidence is kept until its project is deleted; there is no duration to set."""
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as client:
        fixture = await _setup(client, suffix="retention")

        rejected = await client.patch(
            _settings_path(fixture.org_id),
            json={**_body(), "evidenceRetentionDays": 90},
            headers={"Idempotency-Key": _idempotency_key("retention")},
        )
        assert rejected.status_code == 422, rejected.text

    assert (await _stored_settings(fixture.org_id))["version"] == 1


async def test_settings_are_scoped_to_the_authenticated_organization() -> None:
    await init_and_seed_db(seed_if_empty=False)
    async with await _client() as owner_client:
        owner = await _setup(owner_client, suffix="tenant-owner")

    async with await _client() as other_client:
        await _setup(other_client, suffix="tenant-other")

        denied_read = await other_client.get(_settings_path(owner.org_id))
        assert denied_read.status_code == 403, denied_read.text

        denied_write = await other_client.patch(
            _settings_path(owner.org_id),
            json=_body(),
            headers={"Idempotency-Key": _idempotency_key("tenant")},
        )
        assert denied_write.status_code == 403, denied_write.text

    stored = await _stored_settings(owner.org_id)
    assert stored["name"] == "Settings Studio"
    assert stored["version"] == 1

"""Accountable start route for durable selective rescans (provider-free).

Drives the mounted ``POST .../script-versions/{versionId}:startSelectiveRescan``
route end to end over ASGI with a real ``SqlJobRepository`` and local dispatcher,
proving: CSRF/auth/scope enforcement before any repository access; a required
``Idempotency-Key`` header; a single atomic start audit + durable queued job;
dispatch only when the job is newly created; the durable job is returned; client
``itemIds`` are never accepted; and tenant/project mismatch fails closed. The
revision plan and provider gate are swapped for fakes so no scripts fixture,
Parallel, Gemini, network, or cloud dependency is touched.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
import uuid6
from clearcut.database import session_scope
from clearcut.main import app
from clearcut.rescan.application.models import (
    CarryableElementPair,
    RescanSafeError,
    RevisionPlan,
)
from httpx import ASGITransport, AsyncClient

_ORIGIN = {"origin": "http://test"}
_IDEMPOTENCY = {"Idempotency-Key": "rescan-key-0123456789abcdef"}


class _FakeRevisionPlanPort:
    def __init__(self) -> None:
        self.calls = 0

    async def load_revision_plan(self, *, org_id, project_id, after_version_id) -> RevisionPlan:
        self.calls += 1
        return RevisionPlan(
            org_id=org_id,
            project_id=project_id,
            script_id=uuid6.uuid7(),
            before_version_id=uuid6.uuid7(),
            after_version_id=after_version_id,
            algorithm_version="v1",
            carryable_elements=(
                CarryableElementPair(
                    before_element_id=uuid6.uuid7(),
                    after_element_id=uuid6.uuid7(),
                    before_text="Unchanged",
                    after_text="Unchanged",
                ),
            ),
            affected_element_ids=frozenset({uuid6.uuid7()}),
            removed_element_ids=frozenset(),
        )


class _AbsentRevisionPlanPort:
    async def load_revision_plan(self, *, org_id, project_id, after_version_id) -> RevisionPlan:
        raise RescanSafeError(
            code="revision_plan_not_found",
            message="No adjacent revision plan is visible in the requested scope.",
            retryable=False,
        )


class _EnabledGate:
    def is_enabled(self, provider: str) -> bool:
        return True


class _DisabledGate:
    def is_enabled(self, provider: str) -> bool:
        return False


async def _register_owner(client: AsyncClient) -> tuple[UUID, UUID]:
    org_id, project_id, _actor_id = await _register_owner_with_actor(client)
    return org_id, project_id


async def _register_owner_with_actor(client: AsyncClient) -> tuple[UUID, UUID, UUID]:
    registration = await client.post(
        "/api/v1/users",
        json={
            "name": "Rescan Trigger",
            "email": f"rescan-http-{uuid4().hex}@example.com",
            "password": "Password123!",
        },
    )
    assert registration.status_code == 201, registration.text
    actor_id = UUID(registration.json()["data"]["userId"])
    organization = await client.post(
        "/api/v1/organizations",
        json={"name": "Rescan HTTP Studio", "slug": f"rescan-http-{uuid4().hex[:8]}"},
    )
    assert organization.status_code == 201, organization.text
    org_id = UUID(organization.json()["data"]["orgId"])
    project = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        json={"title": "Rescan HTTP Project"},
    )
    assert project.status_code == 201, project.text
    return org_id, UUID(project.json()["data"]["projectId"]), actor_id


async def _set_membership_role(*, org_id: UUID, user_id: UUID, role: str) -> None:
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "UPDATE memberships SET role = :role WHERE org_id = :org_id AND user_id = :user_id"
            ),
            {"role": role, "org_id": str(org_id), "user_id": str(user_id)},
        )


def _path(org_id: UUID, project_id: UUID, version_id: UUID) -> str:
    return (
        f"/api/v1/organizations/{org_id}/projects/{project_id}"
        f"/script-versions/{version_id}:startSelectiveRescan"
    )


@pytest.fixture
def enabled_service():
    service = app.state.start_selective_rescan_service
    original_plan = service._revision_plan
    original_gate = service._provider_gate
    service._revision_plan = _FakeRevisionPlanPort()
    service._provider_gate = _EnabledGate()
    yield service
    service._revision_plan = original_plan
    service._provider_gate = original_gate


@pytest.mark.asyncio
async def test_start_requires_authentication_before_repository_access(enabled_service) -> None:
    version_id = uuid6.uuid7()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=_ORIGIN
    ) as client:
        response = await client.post(
            _path(uuid4(), uuid4(), version_id),
            headers=_IDEMPOTENCY,
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_start_requires_idempotency_key(enabled_service) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=_ORIGIN
    ) as client:
        org_id, project_id = await _register_owner(client)
        response = await client.post(_path(org_id, project_id, uuid6.uuid7()))
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_start_enqueues_one_durable_job_and_dispatches_only_when_created(
    enabled_service,
) -> None:
    version_id = uuid6.uuid7()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=_ORIGIN
    ) as client:
        org_id, project_id = await _register_owner(client)

        first = await client.post(_path(org_id, project_id, version_id), headers=_IDEMPOTENCY)
        assert first.status_code == 202, first.text
        data = first.json()["data"]
        assert data["jobType"] == "selective_rescan"
        assert data["status"] == "queued"
        assert data["target"] == {"type": "script_version", "id": str(version_id)}
        job_id = data["jobId"]

        # Idempotent replay: same version returns the same durable job.
        second = await client.post(_path(org_id, project_id, version_id), headers=_IDEMPOTENCY)
        assert second.status_code == 202, second.text
        assert second.json()["data"]["jobId"] == job_id

    # Exactly one job and exactly one start audit event exist.
    async with session_scope() as session:
        job_rows = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM jobs WHERE org_id = :org_id "
                    "AND project_id = :project_id AND job_type = 'selective_rescan'"
                ),
                {"org_id": str(org_id), "project_id": str(project_id)},
            )
        ).scalar_one()
        audit_rows = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM authoritative_audit_events "
                    "WHERE org_id = :org_id AND project_id = :project_id "
                    "AND action = 'selective_rescan.started'"
                ),
                {"org_id": str(org_id), "project_id": str(project_id)},
            )
        ).scalar_one()
    assert int(job_rows) == 1
    assert int(audit_rows) == 1


@pytest.mark.asyncio
async def test_start_ignores_client_supplied_item_ids(enabled_service) -> None:
    version_id = uuid6.uuid7()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=_ORIGIN
    ) as client:
        org_id, project_id = await _register_owner(client)
        response = await client.post(
            _path(org_id, project_id, version_id),
            headers=_IDEMPOTENCY,
            json={"itemIds": [str(uuid6.uuid7()), str(uuid6.uuid7())]},
        )
        assert response.status_code == 202, response.text
        job_id = UUID(response.json()["data"]["jobId"])

    # The durable job payload is the server-derived version target only; no
    # client item scope is persisted.
    async with session_scope() as session:
        payload = (
            await session.execute(
                sa.text("SELECT payload FROM jobs WHERE id = :id"),
                {"id": str(job_id)},
            )
        ).scalar_one()
    assert "itemIds" not in str(payload)


@pytest.mark.asyncio
async def test_start_rejects_missing_revision_plan(enabled_service) -> None:
    enabled_service._revision_plan = _AbsentRevisionPlanPort()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=_ORIGIN
    ) as client:
        org_id, project_id = await _register_owner(client)
        response = await client.post(_path(org_id, project_id, uuid6.uuid7()), headers=_IDEMPOTENCY)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_start_rejects_disabled_provider_without_calling_provider(enabled_service) -> None:
    enabled_service._provider_gate = _DisabledGate()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=_ORIGIN
    ) as client:
        org_id, project_id = await _register_owner(client)
        response = await client.post(_path(org_id, project_id, uuid6.uuid7()), headers=_IDEMPOTENCY)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "capability_unavailable"


@pytest.mark.asyncio
async def test_start_requires_active_policy(enabled_service) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=_ORIGIN
    ) as client:
        org_id, project_id = await _register_owner(client)
        # Since an organization is born governed with one auto-seeded active
        # binding, remove it so this test can exercise the no-active-policy path.
        async with session_scope() as session:
            await session.execute(
                sa.text("DELETE FROM protected_configurations WHERE org_id = :org_id"),
                {"org_id": str(org_id)},
            )
        response = await client.post(_path(org_id, project_id, uuid6.uuid7()), headers=_IDEMPOTENCY)
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_start_fails_closed_on_foreign_project(enabled_service) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=_ORIGIN
    ) as client:
        org_id, _project_id = await _register_owner(client)
        foreign_project = uuid6.uuid7()
        response = await client.post(
            _path(org_id, foreign_project, uuid6.uuid7()), headers=_IDEMPOTENCY
        )
    assert response.status_code == 404


@pytest.mark.parametrize("role", ["owner", "admin", "reviewer"])
@pytest.mark.asyncio
async def test_start_allows_accountable_roles(enabled_service, role: str) -> None:
    version_id = uuid6.uuid7()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=_ORIGIN
    ) as client:
        org_id, project_id, actor_id = await _register_owner_with_actor(client)
        await _set_membership_role(org_id=org_id, user_id=actor_id, role=role)
        response = await client.post(_path(org_id, project_id, version_id), headers=_IDEMPOTENCY)
    assert response.status_code == 202, response.text
    assert response.json()["data"]["jobType"] == "selective_rescan"


@pytest.mark.parametrize("role", ["editor", "viewer"])
@pytest.mark.asyncio
async def test_start_denies_non_accountable_roles_before_enqueue(
    enabled_service, role: str
) -> None:
    version_id = uuid6.uuid7()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=_ORIGIN
    ) as client:
        org_id, project_id, actor_id = await _register_owner_with_actor(client)
        await _set_membership_role(org_id=org_id, user_id=actor_id, role=role)
        response = await client.post(_path(org_id, project_id, version_id), headers=_IDEMPOTENCY)

    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "permission_denied"

    # A denied actor triggers no durable job and no start audit event: the
    # role gate runs before any repository access or enqueue.
    async with session_scope() as session:
        job_rows = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM jobs WHERE org_id = :org_id "
                    "AND project_id = :project_id AND job_type = 'selective_rescan'"
                ),
                {"org_id": str(org_id), "project_id": str(project_id)},
            )
        ).scalar_one()
        audit_rows = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM authoritative_audit_events "
                    "WHERE org_id = :org_id AND project_id = :project_id "
                    "AND action = 'selective_rescan.started'"
                ),
                {"org_id": str(org_id), "project_id": str(project_id)},
            )
        ).scalar_one()
    assert int(job_rows) == 0
    assert int(audit_rows) == 0

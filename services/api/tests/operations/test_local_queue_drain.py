"""The local queue drain executes child jobs stranded outside HTTP dispatch.

Without it, selective-rescan child detection/research enqueued through the
durable job repository sit queued forever in local mode: enqueue-time dispatch
only runs inside an HTTP request, and lease recovery only rescues interrupted
claims. These tests pin the drain's selection, per-job execution, failure
isolation, and cancellation behavior.
"""

import uuid
from uuid import UUID

import pytest
import sqlalchemy as sa
import uuid6
from clearcut.database import session_scope
from clearcut.main import _drain_due_local_jobs, app
from clearcut.operations.adapters.sql_job_repository import SqlJobRepository
from clearcut.operations.ports.job_repository import EnqueueJob
from httpx import ASGITransport, AsyncClient


async def _create_scope() -> tuple[UUID, UUID, UUID]:
    """Register a real user/org/project through the app (jobs hold tenant FKs)."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"origin": "http://test"},
    ) as client:
        registration = await client.post(
            "/api/v1/users",
            json={
                "name": "Drain Owner",
                "email": f"drain-{uuid.uuid4().hex}@example.com",
                "password": "Password123!",
            },
        )
        assert registration.status_code == 201, registration.text
        context = await client.get("/api/v1/session-context")
        actor_id = UUID(context.json()["data"]["userId"])
        organization = await client.post(
            "/api/v1/organizations",
            json={"name": "Drain Studio", "slug": f"drain-{uuid.uuid4().hex[:8]}"},
        )
        assert organization.status_code == 201, organization.text
        org_id = UUID(organization.json()["data"]["orgId"])
        project = await client.post(
            f"/api/v1/organizations/{org_id}/projects",
            json={"title": "Drained Children"},
        )
        assert project.status_code == 201, project.text
        return org_id, UUID(project.json()["data"]["projectId"]), actor_id


class FakeRunner:
    def __init__(self, *, fail_first: bool = False) -> None:
        self.executed: list[UUID] = []
        self._fail_first = fail_first

    async def run(self, job_id: UUID, org_id: UUID, project_id: UUID):
        if self._fail_first and not self.executed:
            self.executed.append(job_id)
            raise RuntimeError("job execution exploded")
        self.executed.append(job_id)
        return None


async def _enqueue(
    repository: SqlJobRepository,
    *,
    org_id: UUID,
    project_id: UUID,
    actor_id: UUID,
) -> UUID:
    """Enqueue a real research job inside an already-seeded tenant scope."""
    enqueued = await repository.enqueue(
        EnqueueJob(
            org_id=org_id,
            project_id=project_id,
            actor_id=actor_id,
            job_type="research",
            idempotency_key=f"drain-test:{uuid6.uuid7()}",
            payload={
                "schemaVersion": 1,
                "target": {"type": "clearance_item", "id": str(uuid6.uuid7())},
            },
            audit_action="research.started",
            target_type="clearance_item",
            target_id=uuid6.uuid7(),
        )
    )
    return enqueued.job.job_id


async def _set_status(job_id: UUID, status: str) -> None:
    async with session_scope() as session:
        await session.execute(
            sa.text("UPDATE jobs SET status = :status WHERE id = :job_id"),
            {"status": status, "job_id": str(job_id)},
        )


@pytest.mark.asyncio
async def test_drain_executes_due_jobs_across_tenants_in_order():
    repository = SqlJobRepository()
    runner = FakeRunner()
    first_org, first_project, first_actor = await _create_scope()
    second_org, second_project, second_actor = await _create_scope()
    first = await _enqueue(repository, org_id=first_org, project_id=first_project, actor_id=first_actor)
    second = await _enqueue(repository, org_id=second_org, project_id=second_project, actor_id=second_actor)

    await _drain_due_local_jobs(repository, runner)

    assert runner.executed == [first, second]


@pytest.mark.asyncio
async def test_drain_failing_job_does_not_block_remaining_jobs():
    repository = SqlJobRepository()
    runner = FakeRunner(fail_first=True)
    org_id, project_id, actor_id = await _create_scope()
    first = await _enqueue(repository, org_id=org_id, project_id=project_id, actor_id=actor_id)
    second = await _enqueue(repository, org_id=org_id, project_id=project_id, actor_id=actor_id)

    await _drain_due_local_jobs(repository, runner)

    assert runner.executed == [first, second]


@pytest.mark.asyncio
async def test_drain_skips_not_due_and_non_runnable_jobs():
    repository = SqlJobRepository()
    runner = FakeRunner()
    org_id, project_id, actor_id = await _create_scope()
    runnable = await _enqueue(repository, org_id=org_id, project_id=project_id, actor_id=actor_id)
    failed = await _enqueue(repository, org_id=org_id, project_id=project_id, actor_id=actor_id)
    await _set_status(failed, "manual_retry")
    cancelled = await _enqueue(repository, org_id=org_id, project_id=project_id, actor_id=actor_id)
    await _set_status(cancelled, "cancelled")

    await _drain_due_local_jobs(repository, runner)

    assert runner.executed == [runnable]


@pytest.mark.asyncio
async def test_dequeue_respects_batch_size_and_rejects_non_positive():
    repository = SqlJobRepository()
    org_id, project_id, actor_id = await _create_scope()
    for _ in range(3):
        await _enqueue(repository, org_id=org_id, project_id=project_id, actor_id=actor_id)

    first_batch = await repository.dequeue_due_local_jobs(2)
    assert len(first_batch) == 2

    with pytest.raises(ValueError):
        await repository.dequeue_due_local_jobs(0)

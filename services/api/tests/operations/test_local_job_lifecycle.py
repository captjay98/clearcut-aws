import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from clearcut.database import database_wall_clock_sql, session_scope
from clearcut.main import app, lifespan
from clearcut.operations.adapters.sql_job_repository import SqlJobRepository
from clearcut.operations.application.local_dispatcher import (
    LocalDispatchConfigurationError,
    LocalJobDispatcher,
)
from clearcut.operations.application.run_job import (
    JobExecutionError,
    JobExecutionResult,
    RunJobService,
)
from clearcut.operations.domain.jobs import RunStatus
from clearcut.operations.ports.job_repository import (
    EnqueueJob,
    JobLeaseLostError,
    JobNotFoundError,
    JobTransitionError,
    SafeJobError,
)
from fastapi import BackgroundTasks
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _create_scope() -> tuple[UUID, UUID, UUID]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"origin": "http://test"},
    ) as client:
        registration = await client.post(
            "/api/v1/users",
            json={
                "name": "Job Owner",
                "email": f"jobs-{uuid4().hex}@example.com",
                "password": "Password123!",
            },
        )
        assert registration.status_code == 201, registration.text
        context = await client.get("/api/v1/session-context")
        actor_id = UUID(context.json()["data"]["userId"])
        organization = await client.post(
            "/api/v1/organizations",
            json={"name": "Job Studio", "slug": f"job-studio-{uuid4().hex[:8]}"},
        )
        assert organization.status_code == 201, organization.text
        org_id = UUID(organization.json()["data"]["orgId"])
        project = await client.post(
            f"/api/v1/organizations/{org_id}/projects",
            json={"title": "Observable Jobs"},
        )
        assert project.status_code == 201, project.text
        return org_id, UUID(project.json()["data"]["projectId"]), actor_id


def _enqueue_command(
    org_id: UUID,
    project_id: UUID,
    actor_id: UUID,
    *,
    idempotency_key: str,
    job_type: str = "test",
) -> EnqueueJob:
    target_type = {
        "detection": "script_version",
        "research": "clearance_item",
        "selective_rescan": "script_version",
    }.get(job_type, "project")
    return EnqueueJob(
        org_id=org_id,
        project_id=project_id,
        actor_id=actor_id,
        job_type=job_type,
        idempotency_key=idempotency_key,
        payload={
            "schemaVersion": 1,
            "target": {"type": target_type, "id": str(project_id)},
        },
        audit_action=f"{job_type}.started",
        target_type="project",
        target_id=project_id,
    )


@pytest.mark.asyncio
async def test_enqueue_is_idempotent_and_successful_run_records_one_attempt() -> None:
    org_id, project_id, actor_id = await _create_scope()
    repository = SqlJobRepository()
    command = _enqueue_command(
        org_id,
        project_id,
        actor_id,
        idempotency_key="test:success",
    )

    first = await repository.enqueue(command)
    duplicate = await repository.enqueue(command)

    assert first.created is True
    assert duplicate.created is False
    assert duplicate.job.job_id == first.job.job_id
    assert duplicate.job.status is RunStatus.QUEUED

    async def succeed(_job):
        return JobExecutionResult(summary={"processed": 3})

    runner = RunJobService(
        repository=repository,
        processors={"test": succeed},
        lease_owner="local-test",
    )
    completed = await runner.run(first.job.job_id, org_id, project_id)

    assert completed.status is RunStatus.SUCCEEDED
    assert completed.progress == 100
    assert completed.stage == "succeeded"
    assert completed.result_summary == {"processed": 3}
    assert completed.error is None
    assert completed.attempt_count == 1
    assert [(attempt.number, attempt.status) for attempt in completed.attempts] == [
        (1, "succeeded")
    ]
    assert completed.attempts[0].started_at is not None
    assert completed.attempts[0].completed_at is not None


@pytest.mark.asyncio
async def test_typed_failure_can_retry_without_losing_attempt_history() -> None:
    org_id, project_id, actor_id = await _create_scope()
    repository = SqlJobRepository()
    enqueued = await repository.enqueue(
        _enqueue_command(
            org_id,
            project_id,
            actor_id,
            idempotency_key="test:retry",
        )
    )

    async def fail(_job):
        raise JobExecutionError(
            SafeJobError(
                code="provider_timeout",
                message="The provider did not respond in time.",
                retryable=True,
            )
        )

    failed = await RunJobService(
        repository=repository,
        processors={"test": fail},
        lease_owner="local-test",
    ).run(enqueued.job.job_id, org_id, project_id)
    assert failed.status is RunStatus.FAILED
    assert failed.error == SafeJobError(
        code="provider_timeout",
        message="The provider did not respond in time.",
        retryable=True,
    )
    assert failed.attempt_count == 1

    retried = await repository.retry(
        org_id=org_id,
        project_id=project_id,
        job_id=enqueued.job.job_id,
        actor_id=actor_id,
    )
    assert retried.status is RunStatus.QUEUED
    assert retried.error is None
    assert retried.attempt_count == 1

    async def succeed(_job):
        return JobExecutionResult(summary={"processed": 1})

    completed = await RunJobService(
        repository=repository,
        processors={"test": succeed},
        lease_owner="local-test",
    ).run(enqueued.job.job_id, org_id, project_id)
    assert completed.status is RunStatus.SUCCEEDED
    assert completed.attempt_count == 2
    assert [(attempt.number, attempt.status) for attempt in completed.attempts] == [
        (1, "failed"),
        (2, "succeeded"),
    ]
    assert completed.attempts[0].error is not None
    assert completed.attempts[0].error.code == "provider_timeout"


@pytest.mark.asyncio
async def test_cancelled_running_job_is_not_overwritten_by_late_processor_success() -> None:
    org_id, project_id, actor_id = await _create_scope()
    repository = SqlJobRepository()
    enqueued = await repository.enqueue(
        _enqueue_command(
            org_id,
            project_id,
            actor_id,
            idempotency_key="test:cancel",
        )
    )
    processor_started = asyncio.Event()
    release_processor = asyncio.Event()

    async def blocked(_job):
        processor_started.set()
        await release_processor.wait()
        return JobExecutionResult(summary={"shouldNotPersist": True})

    runner = RunJobService(
        repository=repository,
        processors={"test": blocked},
        lease_owner="local-test",
    )
    running_task = asyncio.create_task(runner.run(enqueued.job.job_id, org_id, project_id))
    await processor_started.wait()

    cancelled = await repository.cancel(
        org_id=org_id,
        project_id=project_id,
        job_id=enqueued.job.job_id,
        actor_id=actor_id,
    )
    release_processor.set()
    final = await running_task

    assert cancelled.status is RunStatus.CANCELLED
    assert final.status is RunStatus.CANCELLED
    assert final.result_summary is None
    assert final.attempts[0].status == "cancelled"


@pytest.mark.asyncio
async def test_cancel_uses_status_that_won_compare_and_set_for_attempt_audit() -> None:
    org_id, project_id, actor_id = await _create_scope()
    repository = SqlJobRepository()
    enqueued = await repository.enqueue(
        _enqueue_command(
            org_id,
            project_id,
            actor_id,
            idempotency_key="test:cancel-stale-read",
        )
    )
    claimed = await repository.claim(
        org_id=org_id,
        project_id=project_id,
        job_id=enqueued.job.job_id,
        lease_owner="concurrent-claimer",
    )
    assert claimed is not None
    assert claimed.status is RunStatus.RUNNING

    class StaleQueuedReadRepository(SqlJobRepository):
        def __init__(self) -> None:
            self._return_stale_status = True

        async def _get_row(self, session, read_org_id, read_project_id, read_job_id):
            row = await super()._get_row(
                session,
                read_org_id,
                read_project_id,
                read_job_id,
            )
            if row is not None and self._return_stale_status:
                self._return_stale_status = False
                return {**row, "status": "queued"}
            return row

    cancelled = await StaleQueuedReadRepository().cancel(
        org_id=org_id,
        project_id=project_id,
        job_id=enqueued.job.job_id,
        actor_id=actor_id,
    )

    assert cancelled.status is RunStatus.CANCELLED
    assert cancelled.attempt_count == 1
    assert [(attempt.number, attempt.status) for attempt in cancelled.attempts] == [
        (1, "cancelled")
    ]


@pytest.mark.asyncio
async def test_startup_recovery_marks_expired_local_running_jobs_interrupted() -> None:
    org_id, project_id, actor_id = await _create_scope()
    repository = SqlJobRepository()
    enqueued = await repository.enqueue(
        _enqueue_command(
            org_id,
            project_id,
            actor_id,
            idempotency_key="test:interrupted",
        )
    )
    claimed = await repository.claim(
        org_id=org_id,
        project_id=project_id,
        job_id=enqueued.job.job_id,
        lease_owner="abandoned-local-process",
    )
    assert claimed is not None
    assert claimed.status is RunStatus.RUNNING
    async with session_scope() as session:
        await session.execute(
            sa.text("UPDATE jobs SET lease_expires_at = :expired WHERE id = :job_id"),
            {
                "expired": datetime.now(UTC) - timedelta(seconds=1),
                "job_id": str(enqueued.job.job_id),
            },
        )

    recovered = await repository.recover_interrupted_local_jobs()
    assert [job.job_id for job in recovered] == [enqueued.job.job_id]
    assert recovered[0].status is RunStatus.MANUAL_RETRY
    assert recovered[0].error == SafeJobError(
        code="interrupted",
        message="Local execution was interrupted before completion.",
        retryable=True,
    )
    assert recovered[0].attempts[0].status == "interrupted"


@pytest.mark.asyncio
async def test_startup_recovery_preserves_running_job_with_active_lease() -> None:
    org_id, project_id, actor_id = await _create_scope()
    repository = SqlJobRepository()
    enqueued = await repository.enqueue(
        _enqueue_command(
            org_id,
            project_id,
            actor_id,
            idempotency_key="test:active-lease",
        )
    )
    claimed = await repository.claim(
        org_id=org_id,
        project_id=project_id,
        job_id=enqueued.job.job_id,
        lease_owner="active-local-process",
    )
    assert claimed is not None
    assert claimed.status is RunStatus.RUNNING
    assert claimed.lease_expires_at is not None
    assert claimed.lease_expires_at > datetime.now(UTC)

    recovered = await repository.recover_interrupted_local_jobs()
    current = await repository.get(
        org_id=org_id,
        project_id=project_id,
        job_id=enqueued.job.job_id,
    )

    assert recovered == ()
    assert current is not None
    assert current.status is RunStatus.RUNNING
    assert current.attempts[0].status == "running"


@pytest.mark.asyncio
async def test_unregistered_processor_fails_visibly_instead_of_succeeding() -> None:
    org_id, project_id, actor_id = await _create_scope()
    repository = SqlJobRepository()
    enqueued = await repository.enqueue(
        _enqueue_command(
            org_id,
            project_id,
            actor_id,
            idempotency_key="detection:unimplemented",
            job_type="detection",
        )
    )

    result = await RunJobService(
        repository=repository,
        processors={},
        lease_owner="local-test",
    ).run(enqueued.job.job_id, org_id, project_id)

    assert result.status is RunStatus.FAILED
    assert result.error == SafeJobError(
        code="processor_unavailable",
        message="No processor is configured for job type 'detection'.",
        retryable=False,
    )


def test_local_dispatch_rejects_multiple_processes() -> None:
    with pytest.raises(LocalDispatchConfigurationError, match="exactly one worker"):
        LocalJobDispatcher.validate_configuration(mode="local", worker_count=2)


@pytest.mark.asyncio
async def test_local_dispatcher_runs_registered_processor_via_background_tasks() -> None:
    org_id, project_id, actor_id = await _create_scope()
    repository = SqlJobRepository()
    enqueued = await repository.enqueue(
        _enqueue_command(
            org_id,
            project_id,
            actor_id,
            idempotency_key="test:background-dispatch",
        )
    )

    async def succeed(_job):
        return JobExecutionResult(summary={"dispatched": True})

    runner = RunJobService(
        repository=repository,
        processors={"test": succeed},
        lease_owner="local-background-test",
    )
    dispatcher = LocalJobDispatcher(runner=runner, mode="local", worker_count=1)
    background_tasks = BackgroundTasks()
    dispatcher.dispatch(background_tasks, enqueued.job)

    still_queued = await repository.get(
        org_id=org_id,
        project_id=project_id,
        job_id=enqueued.job.job_id,
    )
    assert still_queued is not None
    assert still_queued.status is RunStatus.QUEUED

    await background_tasks()
    completed = await repository.get(
        org_id=org_id,
        project_id=project_id,
        job_id=enqueued.job.job_id,
    )
    assert completed is not None
    assert completed.status is RunStatus.SUCCEEDED
    assert completed.result_summary == {"dispatched": True}


@pytest.mark.asyncio
async def test_retry_binds_new_attempt_events_to_retrying_actor() -> None:
    org_id, project_id, original_actor_id = await _create_scope()
    _other_org_id, _other_project_id, retrying_actor_id = await _create_scope()
    repository = SqlJobRepository()
    enqueued = await repository.enqueue(
        _enqueue_command(
            org_id,
            project_id,
            original_actor_id,
            idempotency_key="test:retry-actor",
        )
    )

    async def fail(_job):
        raise JobExecutionError(
            SafeJobError(
                code="provider_timeout",
                message="The provider did not respond in time.",
                retryable=True,
            )
        )

    await RunJobService(
        repository=repository,
        processors={"test": fail},
        lease_owner="original-attempt",
    ).run(enqueued.job.job_id, org_id, project_id)
    await repository.retry(
        org_id=org_id,
        project_id=project_id,
        job_id=enqueued.job.job_id,
        actor_id=retrying_actor_id,
    )

    async def succeed(_job):
        return JobExecutionResult(summary={"retried": True})

    await RunJobService(
        repository=repository,
        processors={"test": succeed},
        lease_owner="retry-attempt",
    ).run(enqueued.job.job_id, org_id, project_id)

    async with session_scope() as session:
        events = (
            (
                await session.execute(
                    sa.text(
                        "SELECT action, actor_id FROM authoritative_audit_events "
                        "WHERE org_id = :org_id AND project_id = :project_id "
                        "AND target_type = 'job' AND target_id = :job_id "
                        "AND action IN ("
                        "'job.attempt.started', 'job.attempt.succeeded', "
                        "'job.attempt.failed') ORDER BY occurred_at, id"
                    ),
                    {
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                        "job_id": str(enqueued.job.job_id),
                    },
                )
            )
            .mappings()
            .all()
        )

    assert [(event["action"], UUID(str(event["actor_id"]))) for event in events] == [
        ("job.attempt.started", original_actor_id),
        ("job.attempt.failed", original_actor_id),
        ("job.attempt.started", retrying_actor_id),
        ("job.attempt.succeeded", retrying_actor_id),
    ]


@pytest.mark.asyncio
async def test_startup_recovery_exposes_actorless_legacy_job_for_manual_retry() -> None:
    org_id, project_id, _actor_id = await _create_scope()
    legacy_job_id = uuid4()
    now = datetime.now(UTC)
    async with session_scope() as session:
        statement = sa.text(
            """
            INSERT INTO jobs (
                id, org_id, project_id, job_type, status, idempotency_key,
                payload, progress, stage, actor_id, correlation_id,
                attempt_count, available_at, created_at, updated_at,
                lease_owner, lease_expires_at
            ) VALUES (
                :id, :org_id, :project_id, 'test', 'running', :idempotency_key,
                :payload, 0, 'running', NULL, :correlation_id,
                0, :available_at, :created_at, :updated_at,
                'legacy-worker', :lease_expires_at
            )
            """
        ).bindparams(sa.bindparam("payload", type_=sa.JSON()))
        await session.execute(
            statement,
            {
                "id": str(legacy_job_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "idempotency_key": f"legacy:{legacy_job_id}",
                "payload": {"schemaVersion": 1},
                "correlation_id": str(legacy_job_id),
                "available_at": now,
                "created_at": now,
                "updated_at": now,
                "lease_expires_at": now - timedelta(seconds=1),
            },
        )

    repository = SqlJobRepository()
    recovered = await repository.recover_interrupted_local_jobs()
    current = await repository.get(
        org_id=org_id,
        project_id=project_id,
        job_id=legacy_job_id,
    )

    assert [job.job_id for job in recovered] == [legacy_job_id]
    assert current is not None
    assert current.status is RunStatus.MANUAL_RETRY
    assert current.error == SafeJobError(
        code="interrupted",
        message="Local execution was interrupted before completion.",
        retryable=True,
    )
    assert current.attempts == ()


def test_local_dispatch_rejects_conflicting_worker_environment(monkeypatch) -> None:
    monkeypatch.setenv("CLEARCUT_JOB_DISPATCH_MODE", "local")
    monkeypatch.setenv("CLEARCUT_API_WORKERS", "1")
    monkeypatch.setenv("WEB_CONCURRENCY", "2")
    runner = RunJobService(
        repository=SqlJobRepository(),
        processors={},
        lease_owner="configuration-test",
    )

    with pytest.raises(LocalDispatchConfigurationError, match="must match"):
        LocalJobDispatcher.from_environment(runner=runner)


def test_container_worker_command_uses_dispatch_worker_configuration() -> None:
    dockerfile = (Path(__file__).resolve().parents[4] / "Dockerfile").read_text()

    assert "--workers" in dockerfile
    assert "${CLEARCUT_API_WORKERS:-${WEB_CONCURRENCY:-1}}" in dockerfile


@pytest.mark.asyncio
async def test_expired_lease_cannot_finalize_job_success() -> None:
    org_id, project_id, actor_id = await _create_scope()
    repository = SqlJobRepository()
    enqueued = await repository.enqueue(
        _enqueue_command(
            org_id,
            project_id,
            actor_id,
            idempotency_key="test:expired-terminal-write",
        )
    )
    claimed = await repository.claim(
        org_id=org_id,
        project_id=project_id,
        job_id=enqueued.job.job_id,
        lease_owner="expired-worker",
    )
    assert claimed is not None
    async with session_scope() as session:
        await session.execute(
            sa.text("UPDATE jobs SET lease_expires_at = :expired WHERE id = :job_id"),
            {
                "expired": datetime.now(UTC) - timedelta(seconds=1),
                "job_id": str(enqueued.job.job_id),
            },
        )

    final = await repository.succeed(
        org_id=org_id,
        project_id=project_id,
        job_id=enqueued.job.job_id,
        attempt_number=claimed.attempt_count,
        lease_owner="expired-worker",
        summary={"mustNotPersist": True},
    )

    assert final.status is RunStatus.RUNNING
    assert final.result_summary is None


def test_database_wall_clock_sql_is_not_transaction_start_time() -> None:
    assert database_wall_clock_sql("postgresql") == "clock_timestamp()"
    assert database_wall_clock_sql("sqlite") == ("STRFTIME('%Y-%m-%d %H:%M:%f', 'now')")
    with pytest.raises(RuntimeError, match="Unsupported database dialect"):
        database_wall_clock_sql("mysql")


@pytest.mark.parametrize("terminal", ["succeed", "fail"])
@pytest.mark.asyncio
async def test_lease_expiring_while_terminal_update_waits_cannot_finalize_job(
    monkeypatch: pytest.MonkeyPatch,
    terminal: str,
) -> None:
    org_id, project_id, actor_id = await _create_scope()
    repository = SqlJobRepository()
    enqueued = await repository.enqueue(
        _enqueue_command(
            org_id,
            project_id,
            actor_id,
            idempotency_key=f"terminal-clock:{terminal}:{uuid4()}",
        )
    )
    claimed = await repository.claim(
        org_id=org_id,
        project_id=project_id,
        job_id=enqueued.job.job_id,
        lease_owner="terminal-clock-test",
    )
    assert claimed is not None
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "UPDATE jobs SET lease_expires_at = "
                "STRFTIME('%Y-%m-%d %H:%M:%f', 'now', '+0.10 seconds') "
                "WHERE id = :job_id AND org_id = :org_id "
                "AND project_id = :project_id"
            ),
            {
                "job_id": str(claimed.job_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
            },
        )

    original_execute = AsyncSession.execute
    delayed = False
    terminal_status = "succeeded" if terminal == "succeed" else "failed"

    async def execute_after_lease_expiry(
        session: AsyncSession,
        statement,
        params=None,
        **kwargs,
    ):
        nonlocal delayed
        sql = " ".join(str(statement).split())
        if not delayed and sql.startswith(f"UPDATE jobs SET status = '{terminal_status}'"):
            delayed = True
            await asyncio.sleep(0.20)
        return await original_execute(
            session,
            statement,
            params=params,
            **kwargs,
        )

    monkeypatch.setattr(AsyncSession, "execute", execute_after_lease_expiry)

    if terminal == "succeed":
        result = await repository.succeed(
            org_id=org_id,
            project_id=project_id,
            job_id=claimed.job_id,
            attempt_number=claimed.attempt_count,
            lease_owner="terminal-clock-test",
            summary={"reviewStatus": "unresolved"},
        )
    else:
        result = await repository.fail(
            org_id=org_id,
            project_id=project_id,
            job_id=claimed.job_id,
            attempt_number=claimed.attempt_count,
            lease_owner="terminal-clock-test",
            error=SafeJobError(
                code="provider_unavailable",
                message="The provider could not complete the request.",
                retryable=True,
            ),
        )

    assert delayed is True
    assert result.status is RunStatus.RUNNING
    async with session_scope() as session:
        terminal_attempt_count = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM authoritative_audit_events "
                    "WHERE target_id = :job_id AND action = :action"
                ),
                {
                    "job_id": str(claimed.job_id),
                    "action": f"job.attempt.{terminal_status}",
                },
            )
        ).scalar_one()
    assert terminal_attempt_count == 0


@pytest.mark.asyncio
async def test_cancelled_detection_can_be_governedly_retried_with_attempt_history() -> None:
    org_id, project_id, actor_id = await _create_scope()
    repository = SqlJobRepository()
    enqueued = await repository.enqueue(
        _enqueue_command(
            org_id,
            project_id,
            actor_id,
            idempotency_key="detection:cancelled-retry",
            job_type="detection",
        )
    )
    claimed = await repository.claim(
        org_id=org_id,
        project_id=project_id,
        job_id=enqueued.job.job_id,
        lease_owner="cancelled-detection-attempt",
    )
    assert claimed is not None

    cancelled = await repository.cancel(
        org_id=org_id,
        project_id=project_id,
        job_id=enqueued.job.job_id,
        actor_id=actor_id,
    )
    assert cancelled.status is RunStatus.CANCELLED
    assert [(attempt.number, attempt.status) for attempt in cancelled.attempts] == [
        (1, "cancelled")
    ]

    retried = await repository.retry(
        org_id=org_id,
        project_id=project_id,
        job_id=enqueued.job.job_id,
        actor_id=actor_id,
    )
    assert retried.job_id == enqueued.job.job_id
    assert retried.status is RunStatus.QUEUED
    assert retried.attempt_count == 1
    assert [(attempt.number, attempt.status) for attempt in retried.attempts] == [(1, "cancelled")]

    async def succeed(_job):
        return JobExecutionResult(summary={"retried": True})

    completed = await RunJobService(
        repository=repository,
        processors={"detection": succeed},
        lease_owner="retried-detection-attempt",
    ).run(enqueued.job.job_id, org_id, project_id)

    assert completed.attempt_count == 2
    assert [(attempt.number, attempt.status) for attempt in completed.attempts] == [
        (1, "cancelled"),
        (2, "succeeded"),
    ]
    async with session_scope() as session:
        actions = (
            (
                await session.execute(
                    sa.text(
                        "SELECT action FROM authoritative_audit_events "
                        "WHERE org_id = :org_id AND project_id = :project_id "
                        "AND target_type = 'job' AND target_id = :job_id "
                        "ORDER BY occurred_at, id"
                    ),
                    {
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                        "job_id": str(enqueued.job.job_id),
                    },
                )
            )
            .scalars()
            .all()
        )
    assert "job.attempt.cancelled" in actions
    assert "job.retry.requested" in actions


@pytest.mark.asyncio
async def test_progress_updates_are_monotonic_lease_and_attempt_fenced() -> None:
    org_id, project_id, actor_id = await _create_scope()
    repository = SqlJobRepository()
    enqueued = await repository.enqueue(
        _enqueue_command(
            org_id,
            project_id,
            actor_id,
            idempotency_key="detection:progress",
            job_type="detection",
        )
    )
    claimed = await repository.claim(
        org_id=org_id,
        project_id=project_id,
        job_id=enqueued.job.job_id,
        lease_owner="progress-owner",
    )
    assert claimed is not None

    progressed = await repository.update_progress(
        org_id=org_id,
        project_id=project_id,
        job_id=enqueued.job.job_id,
        attempt_number=1,
        lease_owner="progress-owner",
        progress=25,
        stage="detecting_candidates",
    )
    assert progressed.progress == 25
    assert progressed.stage == "detecting_candidates"

    with pytest.raises(JobTransitionError, match="active leased attempt"):
        await repository.update_progress(
            org_id=org_id,
            project_id=project_id,
            job_id=enqueued.job.job_id,
            attempt_number=1,
            lease_owner="wrong-owner",
            progress=30,
            stage="detecting_candidates",
        )
    with pytest.raises(JobTransitionError, match="monotonic"):
        await repository.update_progress(
            org_id=org_id,
            project_id=project_id,
            job_id=enqueued.job.job_id,
            attempt_number=1,
            lease_owner="progress-owner",
            progress=20,
            stage="reading_persisted_elements",
        )

    await repository.cancel(
        org_id=org_id,
        project_id=project_id,
        job_id=enqueued.job.job_id,
        actor_id=actor_id,
    )
    with pytest.raises(JobTransitionError, match="active leased attempt"):
        await repository.update_progress(
            org_id=org_id,
            project_id=project_id,
            job_id=enqueued.job.job_id,
            attempt_number=1,
            lease_owner="progress-owner",
            progress=50,
            stage="evaluating_findings",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("stale_outcome", ["success", "failure"])
async def test_stale_cancelled_attempt_cannot_finalize_retried_attempt(
    stale_outcome: str,
) -> None:
    org_id, project_id, actor_id = await _create_scope()
    repository = SqlJobRepository()
    enqueued = await repository.enqueue(
        _enqueue_command(
            org_id,
            project_id,
            actor_id,
            idempotency_key=f"detection:stale-{stale_outcome}",
            job_type="detection",
        )
    )
    first_started = asyncio.Event()
    second_started = asyncio.Event()
    release_first = asyncio.Event()
    release_second = asyncio.Event()

    async def process(job):
        if job.attempt_count == 1:
            first_started.set()
            await release_first.wait()
            if stale_outcome == "failure":
                raise JobExecutionError(
                    SafeJobError(
                        code="stale_failure",
                        message="The cancelled attempt failed late.",
                        retryable=True,
                    )
                )
            return JobExecutionResult(summary={"attempt": 1})
        second_started.set()
        await release_second.wait()
        return JobExecutionResult(summary={"attempt": 2})

    runner = RunJobService(
        repository=repository,
        processors={"detection": process},
        lease_owner="reused-process-owner",
    )
    first_task = asyncio.create_task(runner.run(enqueued.job.job_id, org_id, project_id))
    await first_started.wait()
    await repository.cancel(
        org_id=org_id,
        project_id=project_id,
        job_id=enqueued.job.job_id,
        actor_id=actor_id,
    )
    await repository.retry(
        org_id=org_id,
        project_id=project_id,
        job_id=enqueued.job.job_id,
        actor_id=actor_id,
    )
    second_task = asyncio.create_task(runner.run(enqueued.job.job_id, org_id, project_id))
    await second_started.wait()

    release_first.set()
    with pytest.raises(JobLeaseLostError, match="active leased attempt"):
        await first_task
    persisted_while_second_runs = await repository.get(
        org_id=org_id,
        project_id=project_id,
        job_id=enqueued.job.job_id,
    )

    assert persisted_while_second_runs is not None
    assert persisted_while_second_runs.status is RunStatus.RUNNING
    assert persisted_while_second_runs.attempt_count == 2
    assert persisted_while_second_runs.result_summary is None

    release_second.set()
    completed = await second_task
    assert completed.status is RunStatus.SUCCEEDED
    assert completed.result_summary == {"attempt": 2}
    assert [(attempt.number, attempt.status) for attempt in completed.attempts] == [
        (1, "cancelled"),
        (2, "succeeded"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case", "job_type"),
    [
        ("unsupported_job_type", "unsupported"),
        ("missing_schema", "test"),
        ("unsupported_schema", "test"),
        ("string_schema", "test"),
        ("float_schema", "test"),
        ("bool_schema", "test"),
        ("missing_target", "test"),
        ("non_object_target", "test"),
        ("integer_target_id", "test"),
        ("null_target_id", "test"),
        ("extra_payload_key", "test"),
        ("extra_target_key", "test"),
        ("malformed_target", "test"),
        ("wrong_detection_target_kind", "detection"),
        ("wrong_research_target_kind", "research"),
    ],
)
async def test_repository_maps_invalid_complete_job_payload_to_legacy_unknown(
    case: str,
    job_type: str,
) -> None:
    org_id, project_id, actor_id = await _create_scope()
    repository = SqlJobRepository()
    command = _enqueue_command(
        org_id,
        project_id,
        actor_id,
        idempotency_key=f"{job_type}:invalid-payload:{case}",
        job_type=job_type,
    )
    if job_type == "detection":
        command.payload["target"] = {
            "type": "script_version",
            "id": str(project_id),
        }

    if case == "missing_schema":
        command.payload.pop("schemaVersion")
    elif case == "unsupported_schema":
        command.payload["schemaVersion"] = 2
    elif case == "string_schema":
        command.payload["schemaVersion"] = "1"
    elif case == "float_schema":
        command.payload["schemaVersion"] = 1.0
    elif case == "bool_schema":
        command.payload["schemaVersion"] = True
    elif case == "missing_target":
        command.payload.pop("target")
    elif case == "non_object_target":
        command.payload["target"] = []
    elif case == "integer_target_id":
        command.payload["target"] = {
            "type": command.payload["target"]["type"],
            "id": 1,
        }
    elif case == "null_target_id":
        command.payload["target"] = {
            "type": command.payload["target"]["type"],
            "id": None,
        }
    elif case == "extra_payload_key":
        command.payload["unexpected"] = "value"
    elif case == "extra_target_key":
        command.payload["target"]["unexpected"] = "value"
    elif case == "malformed_target":
        command.payload["target"] = {"type": "project", "id": "not-a-uuid"}
    elif case in {"wrong_detection_target_kind", "wrong_research_target_kind"}:
        command.payload["target"] = {"type": "project", "id": str(project_id)}

    enqueued = await repository.enqueue(command)
    persisted = await repository.get(
        org_id=org_id,
        project_id=project_id,
        job_id=enqueued.job.job_id,
    )

    assert enqueued.job.target.type == "legacy_unknown"
    assert enqueued.job.target.id == enqueued.job.job_id
    assert persisted is not None
    assert persisted.target.type == "legacy_unknown"
    assert persisted.target.id == persisted.job_id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("job_type", "target_type"),
    [
        ("test", "project"),
        ("detection", "script_version"),
        ("research", "clearance_item"),
    ],
)
async def test_repository_preserves_known_strict_job_payloads(
    job_type: str,
    target_type: str,
) -> None:
    org_id, project_id, actor_id = await _create_scope()
    command = _enqueue_command(
        org_id,
        project_id,
        actor_id,
        idempotency_key=f"{job_type}:valid-payload",
        job_type=job_type,
    )
    command.payload["target"] = {"type": target_type, "id": str(project_id)}

    enqueued = await SqlJobRepository().enqueue(command)

    assert enqueued.job.target.type == target_type
    assert enqueued.job.target.id == project_id


@pytest.mark.asyncio
async def test_repository_maps_out_of_contract_persisted_target_type_to_legacy_unknown() -> None:
    org_id, project_id, actor_id = await _create_scope()
    repository = SqlJobRepository()
    command = _enqueue_command(
        org_id,
        project_id,
        actor_id,
        idempotency_key="test:malformed-target",
    )
    command.payload["target"] = {
        "type": "outside_openapi_contract",
        "id": str(project_id),
    }

    enqueued = await repository.enqueue(command)
    persisted = await repository.get(
        org_id=org_id,
        project_id=project_id,
        job_id=enqueued.job.job_id,
    )

    assert enqueued.job.target.type == "legacy_unknown"
    assert enqueued.job.target.id == enqueued.job.job_id
    assert persisted is not None
    assert persisted.target.type == "legacy_unknown"
    assert persisted.target.id == persisted.job_id


async def _claimed_progress_job(
    *,
    idempotency_key: str,
) -> tuple[UUID, UUID, SqlJobRepository, UUID]:
    org_id, project_id, actor_id = await _create_scope()
    repository = SqlJobRepository()
    enqueued = await repository.enqueue(
        _enqueue_command(
            org_id,
            project_id,
            actor_id,
            idempotency_key=idempotency_key,
            job_type="detection",
        )
    )
    claimed = await repository.claim(
        org_id=org_id,
        project_id=project_id,
        job_id=enqueued.job.job_id,
        lease_owner="focused-progress-owner",
    )
    assert claimed is not None
    return org_id, project_id, repository, enqueued.job.job_id


@pytest.mark.asyncio
async def test_update_progress_rejects_wrong_tenant_and_project_scope() -> None:
    org_id, project_id, repository, job_id = await _claimed_progress_job(
        idempotency_key="detection:progress-scope",
    )

    for scoped_org_id, scoped_project_id in (
        (uuid4(), project_id),
        (org_id, uuid4()),
    ):
        with pytest.raises(JobNotFoundError, match="not found"):
            await repository.update_progress(
                org_id=scoped_org_id,
                project_id=scoped_project_id,
                job_id=job_id,
                attempt_number=1,
                lease_owner="focused-progress-owner",
                progress=25,
                stage="detecting_candidates",
            )

    persisted = await repository.get(org_id=org_id, project_id=project_id, job_id=job_id)
    assert persisted is not None
    assert persisted.progress == 0
    assert persisted.stage == "running"


@pytest.mark.asyncio
async def test_update_progress_rejects_stale_attempt_number() -> None:
    org_id, project_id, repository, job_id = await _claimed_progress_job(
        idempotency_key="detection:progress-stale-attempt",
    )

    with pytest.raises(JobTransitionError, match="active leased attempt"):
        await repository.update_progress(
            org_id=org_id,
            project_id=project_id,
            job_id=job_id,
            attempt_number=2,
            lease_owner="focused-progress-owner",
            progress=25,
            stage="detecting_candidates",
        )

    persisted = await repository.get(org_id=org_id, project_id=project_id, job_id=job_id)
    assert persisted is not None
    assert persisted.progress == 0
    assert persisted.stage == "running"


@pytest.mark.asyncio
async def test_update_progress_rejects_expired_lease() -> None:
    org_id, project_id, repository, job_id = await _claimed_progress_job(
        idempotency_key="detection:progress-expired-lease",
    )
    async with session_scope() as session:
        await session.execute(
            sa.text("UPDATE jobs SET lease_expires_at = :expired WHERE id = :job_id"),
            {
                "expired": datetime.now(UTC) - timedelta(seconds=1),
                "job_id": str(job_id),
            },
        )

    with pytest.raises(JobTransitionError, match="active leased attempt"):
        await repository.update_progress(
            org_id=org_id,
            project_id=project_id,
            job_id=job_id,
            attempt_number=1,
            lease_owner="focused-progress-owner",
            progress=25,
            stage="detecting_candidates",
        )

    persisted = await repository.get(org_id=org_id, project_id=project_id, job_id=job_id)
    assert persisted is not None
    assert persisted.progress == 0
    assert persisted.stage == "running"


@pytest.mark.asyncio
@pytest.mark.parametrize("progress", [-0.01, 100.0, 100.01])
async def test_update_progress_rejects_out_of_range_active_progress(progress: float) -> None:
    org_id, project_id, repository, job_id = await _claimed_progress_job(
        idempotency_key=f"detection:progress-range:{progress}",
    )

    with pytest.raises(JobTransitionError, match="between 0 and 100"):
        await repository.update_progress(
            org_id=org_id,
            project_id=project_id,
            job_id=job_id,
            attempt_number=1,
            lease_owner="focused-progress-owner",
            progress=progress,
            stage="detecting_candidates",
        )

    persisted = await repository.get(org_id=org_id, project_id=project_id, job_id=job_id)
    assert persisted is not None
    assert persisted.progress == 0
    assert persisted.stage == "running"


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["", "   ", "\n\t"])
async def test_update_progress_rejects_blank_stage(stage: str) -> None:
    org_id, project_id, repository, job_id = await _claimed_progress_job(
        idempotency_key=f"detection:progress-stage:{stage!r}",
    )

    with pytest.raises(JobTransitionError, match="named stage"):
        await repository.update_progress(
            org_id=org_id,
            project_id=project_id,
            job_id=job_id,
            attempt_number=1,
            lease_owner="focused-progress-owner",
            progress=25,
            stage=stage,
        )

    persisted = await repository.get(org_id=org_id, project_id=project_id, job_id=job_id)
    assert persisted is not None
    assert persisted.progress == 0
    assert persisted.stage == "running"


@pytest.mark.asyncio
async def test_renew_lease_is_tenant_attempt_and_owner_fenced() -> None:
    org_id, project_id, actor_id = await _create_scope()
    repository = SqlJobRepository(lease_duration=timedelta(seconds=1))
    enqueued = await repository.enqueue(
        _enqueue_command(
            org_id,
            project_id,
            actor_id,
            idempotency_key="test:renew-lease-fences",
        )
    )
    claimed = await repository.claim(
        org_id=org_id,
        project_id=project_id,
        job_id=enqueued.job.job_id,
        lease_owner="renew-owner",
    )
    assert claimed is not None
    assert claimed.lease_expires_at is not None
    await asyncio.sleep(0.01)

    renewed = await repository.renew_lease(
        org_id=org_id,
        project_id=project_id,
        job_id=claimed.job_id,
        attempt_number=claimed.attempt_count,
        lease_owner="renew-owner",
    )

    assert renewed.status is RunStatus.RUNNING
    assert renewed.lease_expires_at is not None
    assert renewed.lease_expires_at > claimed.lease_expires_at

    for attempt_number, lease_owner in (
        (claimed.attempt_count + 1, "renew-owner"),
        (claimed.attempt_count, "wrong-owner"),
    ):
        with pytest.raises(JobLeaseLostError, match="active leased attempt"):
            await repository.renew_lease(
                org_id=org_id,
                project_id=project_id,
                job_id=claimed.job_id,
                attempt_number=attempt_number,
                lease_owner=lease_owner,
            )

    for scoped_org_id, scoped_project_id in (
        (uuid4(), project_id),
        (org_id, uuid4()),
    ):
        with pytest.raises(JobNotFoundError, match="not found"):
            await repository.renew_lease(
                org_id=scoped_org_id,
                project_id=scoped_project_id,
                job_id=claimed.job_id,
                attempt_number=claimed.attempt_count,
                lease_owner="renew-owner",
            )


@pytest.mark.asyncio
async def test_heartbeat_renews_lease_while_processor_runs_longer_than_ttl() -> None:
    org_id, project_id, actor_id = await _create_scope()
    repository = SqlJobRepository(lease_duration=timedelta(milliseconds=120))
    enqueued = await repository.enqueue(
        _enqueue_command(
            org_id,
            project_id,
            actor_id,
            idempotency_key="test:heartbeat-long-work",
        )
    )

    async def slow_processor(_job):
        await asyncio.sleep(0.35)
        return JobExecutionResult(summary={"renewed": True})

    completed = await RunJobService(
        repository=repository,
        processors={"test": slow_processor},
        lease_owner="heartbeat-owner",
        heartbeat_interval_seconds=0.03,
    ).run(enqueued.job.job_id, org_id, project_id)

    assert completed.status is RunStatus.SUCCEEDED
    assert completed.result_summary == {"renewed": True}
    assert completed.attempts[0].status == "succeeded"


@pytest.mark.asyncio
async def test_heartbeat_ownership_loss_cancels_work_and_cannot_finalize() -> None:
    org_id, project_id, actor_id = await _create_scope()
    repository = SqlJobRepository(lease_duration=timedelta(seconds=1))
    enqueued = await repository.enqueue(
        _enqueue_command(
            org_id,
            project_id,
            actor_id,
            idempotency_key="test:heartbeat-ownership-loss",
        )
    )
    processor_started = asyncio.Event()
    processor_stopped = asyncio.Event()

    async def blocked_processor(_job) -> JobExecutionResult:
        processor_started.set()
        try:
            await asyncio.Event().wait()
            return JobExecutionResult(summary={"unreachable": True})
        finally:
            processor_stopped.set()

    runner = RunJobService(
        repository=repository,
        processors={"test": blocked_processor},
        lease_owner="original-owner",
        heartbeat_interval_seconds=0.02,
    )
    running = asyncio.create_task(runner.run(enqueued.job.job_id, org_id, project_id))
    await asyncio.wait_for(processor_started.wait(), timeout=1)
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "UPDATE jobs SET lease_owner = 'replacement-owner', "
                "lease_expires_at = STRFTIME('%Y-%m-%d %H:%M:%f', 'now', '+1 second') "
                "WHERE id = :job_id AND org_id = :org_id AND project_id = :project_id"
            ),
            {
                "job_id": str(enqueued.job.job_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
            },
        )

    with pytest.raises(JobLeaseLostError, match="active leased attempt"):
        await asyncio.wait_for(running, timeout=1)
    await asyncio.wait_for(processor_stopped.wait(), timeout=1)

    persisted = await repository.get(
        org_id=org_id,
        project_id=project_id,
        job_id=enqueued.job.job_id,
    )
    assert persisted is not None
    assert persisted.status is RunStatus.RUNNING
    assert persisted.result_summary is None
    assert persisted.error is None


@pytest.mark.asyncio
async def test_lifespan_periodically_recovers_expired_job_without_restart() -> None:
    org_id, project_id, actor_id = await _create_scope()
    repository = SqlJobRepository(lease_duration=timedelta(milliseconds=80))
    enqueued = await repository.enqueue(
        _enqueue_command(
            org_id,
            project_id,
            actor_id,
            idempotency_key="test:live-recovery",
        )
    )
    claimed = await repository.claim(
        org_id=org_id,
        project_id=project_id,
        job_id=enqueued.job.job_id,
        lease_owner="abandoned-live-worker",
    )
    assert claimed is not None

    original_repository = app.state.job_repository
    original_dispatcher = app.state.job_dispatcher
    original_interval = getattr(app.state, "local_job_recovery_interval_seconds", None)
    app.state.job_repository = repository
    app.state.job_dispatcher = LocalJobDispatcher(
        runner=app.state.job_runner,
        mode="local",
        worker_count=1,
    )
    app.state.local_job_recovery_interval_seconds = 0.02
    try:
        async with lifespan(app):
            async with asyncio.timeout(1):
                while True:
                    current = await repository.get(
                        org_id=org_id,
                        project_id=project_id,
                        job_id=enqueued.job.job_id,
                    )
                    if current is not None and current.status is RunStatus.MANUAL_RETRY:
                        break
                    await asyncio.sleep(0.01)
        assert current is not None
        assert current.error is not None
        assert current.error.code == "interrupted"
    finally:
        app.state.job_repository = original_repository
        app.state.job_dispatcher = original_dispatcher
        if original_interval is None:
            del app.state.local_job_recovery_interval_seconds
        else:
            app.state.local_job_recovery_interval_seconds = original_interval


@pytest.mark.asyncio
async def test_lifespan_stops_periodic_recovery_task_on_shutdown() -> None:
    class CountingRecoveryRepository:
        def __init__(self) -> None:
            self.calls = 0
            self.called_twice = asyncio.Event()

        async def recover_interrupted_local_jobs(self):
            self.calls += 1
            if self.calls >= 2:
                self.called_twice.set()
            return ()

    repository = CountingRecoveryRepository()
    original_repository = app.state.job_repository
    original_dispatcher = app.state.job_dispatcher
    original_interval = getattr(app.state, "local_job_recovery_interval_seconds", None)
    app.state.job_repository = repository
    app.state.job_dispatcher = LocalJobDispatcher(
        runner=app.state.job_runner,
        mode="local",
        worker_count=1,
    )
    app.state.local_job_recovery_interval_seconds = 0.01
    try:
        async with lifespan(app):
            await asyncio.wait_for(repository.called_twice.wait(), timeout=1)
        calls_after_shutdown = repository.calls
        await asyncio.sleep(0.04)
        assert repository.calls == calls_after_shutdown
    finally:
        app.state.job_repository = original_repository
        app.state.job_dispatcher = original_dispatcher
        if original_interval is None:
            del app.state.local_job_recovery_interval_seconds
        else:
            app.state.local_job_recovery_interval_seconds = original_interval


@pytest.mark.asyncio
@pytest.mark.parametrize("lease_state", ["expired", "cancelled"])
async def test_renew_lease_rejects_inactive_lease_without_extending_expiry(
    lease_state: str,
) -> None:
    org_id, project_id, actor_id = await _create_scope()
    repository = SqlJobRepository(lease_duration=timedelta(minutes=1))
    enqueued = await repository.enqueue(
        _enqueue_command(
            org_id,
            project_id,
            actor_id,
            idempotency_key=f"test:renew-inactive:{lease_state}",
        )
    )
    claimed = await repository.claim(
        org_id=org_id,
        project_id=project_id,
        job_id=enqueued.job.job_id,
        lease_owner="inactive-renew-owner",
    )
    assert claimed is not None

    if lease_state == "expired":
        async with session_scope() as session:
            await session.execute(
                sa.text("UPDATE jobs SET lease_expires_at = :expired WHERE id = :job_id"),
                {
                    "expired": datetime.now(UTC) - timedelta(seconds=1),
                    "job_id": str(claimed.job_id),
                },
            )
    else:
        async with session_scope() as session:
            await session.execute(
                sa.text("UPDATE jobs SET status = 'cancelled' WHERE id = :job_id"),
                {"job_id": str(claimed.job_id)},
            )

    async with session_scope() as session:
        expiry_before = (
            await session.execute(
                sa.text("SELECT lease_expires_at FROM jobs WHERE id = :job_id"),
                {"job_id": str(claimed.job_id)},
            )
        ).scalar_one()

    with pytest.raises(JobLeaseLostError, match="active leased attempt"):
        await repository.renew_lease(
            org_id=org_id,
            project_id=project_id,
            job_id=claimed.job_id,
            attempt_number=claimed.attempt_count,
            lease_owner="inactive-renew-owner",
        )

    async with session_scope() as session:
        expiry_after = (
            await session.execute(
                sa.text("SELECT lease_expires_at FROM jobs WHERE id = :job_id"),
                {"job_id": str(claimed.job_id)},
            )
        ).scalar_one()
    assert expiry_after == expiry_before


@pytest.mark.asyncio
async def test_recovery_sweep_updates_only_configured_batch_size() -> None:
    org_id, project_id, actor_id = await _create_scope()
    repository = SqlJobRepository(recovery_batch_size=2)
    job_ids: list[UUID] = []
    for index in range(3):
        enqueued = await repository.enqueue(
            _enqueue_command(
                org_id,
                project_id,
                actor_id,
                idempotency_key=f"test:bounded-recovery:{index}",
            )
        )
        claimed = await repository.claim(
            org_id=org_id,
            project_id=project_id,
            job_id=enqueued.job.job_id,
            lease_owner=f"abandoned-batch-worker-{index}",
        )
        assert claimed is not None
        job_ids.append(claimed.job_id)

    async with session_scope() as session:
        await session.execute(
            sa.text(
                "UPDATE jobs SET lease_expires_at = :expired "
                "WHERE org_id = :org_id AND project_id = :project_id"
            ),
            {
                "expired": datetime.now(UTC) - timedelta(seconds=1),
                "org_id": str(org_id),
                "project_id": str(project_id),
            },
        )

    recovered = await repository.recover_interrupted_local_jobs()
    persisted = [
        await repository.get(org_id=org_id, project_id=project_id, job_id=job_id)
        for job_id in job_ids
    ]

    assert len(recovered) == 2
    assert all(job.status is RunStatus.MANUAL_RETRY for job in recovered)
    assert sum(job is not None and job.status is RunStatus.MANUAL_RETRY for job in persisted) == 2
    assert sum(job is not None and job.status is RunStatus.RUNNING for job in persisted) == 1


@pytest.mark.asyncio
async def test_lifespan_recovers_expired_jobs_before_yield() -> None:
    class StartupRecoveryRepository:
        def __init__(self) -> None:
            self.calls = 0

        async def recover_interrupted_local_jobs(self):
            self.calls += 1
            return ()

    repository = StartupRecoveryRepository()
    original_repository = app.state.job_repository
    original_dispatcher = app.state.job_dispatcher
    original_interval = getattr(app.state, "local_job_recovery_interval_seconds", None)
    app.state.job_repository = repository
    app.state.job_dispatcher = LocalJobDispatcher(
        runner=app.state.job_runner,
        mode="local",
        worker_count=1,
    )
    app.state.local_job_recovery_interval_seconds = 60
    try:
        assert repository.calls == 0
        async with lifespan(app):
            assert repository.calls == 1
    finally:
        app.state.job_repository = original_repository
        app.state.job_dispatcher = original_dispatcher
        if original_interval is None:
            del app.state.local_job_recovery_interval_seconds
        else:
            app.state.local_job_recovery_interval_seconds = original_interval


@pytest.mark.asyncio
async def test_local_dispatcher_absorbs_expected_lease_loss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = RunJobService(
        repository=SqlJobRepository(),
        processors={},
        lease_owner="superseded-background-runner",
    )

    async def lose_superseded_lease(
        _job_id: UUID,
        _org_id: UUID,
        _project_id: UUID,
    ) -> None:
        raise JobLeaseLostError("The dispatched attempt was superseded.")

    monkeypatch.setattr(runner, "run", lose_superseded_lease)
    dispatcher = LocalJobDispatcher(runner=runner, mode="local", worker_count=1)
    background_tasks = BackgroundTasks()
    dispatcher.dispatch_identifiers(
        background_tasks,
        job_id=uuid4(),
        org_id=uuid4(),
        project_id=uuid4(),
    )

    await background_tasks()


@pytest.mark.asyncio
async def test_list_jobs_bulk_loads_lifecycle_in_constant_queries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org_id, project_id, actor_id = await _create_scope()
    repository = SqlJobRepository()
    jobs = [
        await repository.enqueue(
            _enqueue_command(
                org_id,
                project_id,
                actor_id,
                idempotency_key=f"test:bulk-list:{index}",
            )
        )
        for index in range(3)
    ]
    claimed = await repository.claim(
        org_id=org_id,
        project_id=project_id,
        job_id=jobs[0].job.job_id,
        lease_owner="bulk-list-worker",
    )
    assert claimed is not None
    await repository.cancel(
        org_id=org_id,
        project_id=project_id,
        job_id=claimed.job_id,
        actor_id=actor_id,
    )

    original_execute = AsyncSession.execute
    query_count = 0

    async def count_execute(session, statement, params=None, **kwargs):
        nonlocal query_count
        query_count += 1
        return await original_execute(session, statement, params=params, **kwargs)

    monkeypatch.setattr(AsyncSession, "execute", count_execute)

    page = await repository.list(org_id=org_id, project_id=project_id)

    listed_by_id = {job.job_id: job for job in page.jobs}
    assert set(listed_by_id) == {job.job.job_id for job in jobs}
    assert page.total_count == 3
    assert page.next_cursor is None
    assert [
        (attempt.number, attempt.status) for attempt in listed_by_id[claimed.job_id].attempts
    ] == [(1, "cancelled")]
    assert [event.action for event in listed_by_id[claimed.job_id].history] == ["cancelled"]
    assert query_count == 4



@pytest.mark.asyncio
async def test_cancelled_selective_rescan_can_be_governedly_retried_with_attempt_history() -> None:
    """A cancelled selective_rescan is retryable only via an accountable request,
    with the same durable attempt-history parity as detection."""
    org_id, project_id, actor_id = await _create_scope()
    repository = SqlJobRepository()
    enqueued = await repository.enqueue(
        _enqueue_command(
            org_id,
            project_id,
            actor_id,
            idempotency_key="selective_rescan:cancelled-retry",
            job_type="selective_rescan",
        )
    )
    claimed = await repository.claim(
        org_id=org_id,
        project_id=project_id,
        job_id=enqueued.job.job_id,
        lease_owner="cancelled-rescan-attempt",
    )
    assert claimed is not None

    cancelled = await repository.cancel(
        org_id=org_id,
        project_id=project_id,
        job_id=enqueued.job.job_id,
        actor_id=actor_id,
    )
    assert cancelled.status is RunStatus.CANCELLED
    assert [(attempt.number, attempt.status) for attempt in cancelled.attempts] == [
        (1, "cancelled")
    ]

    retried = await repository.retry(
        org_id=org_id,
        project_id=project_id,
        job_id=enqueued.job.job_id,
        actor_id=actor_id,
    )
    assert retried.job_id == enqueued.job.job_id
    assert retried.status is RunStatus.QUEUED
    assert retried.attempt_count == 1
    assert [(attempt.number, attempt.status) for attempt in retried.attempts] == [(1, "cancelled")]

    async def succeed(_job):
        return JobExecutionResult(summary={"retried": True})

    completed = await RunJobService(
        repository=repository,
        processors={"selective_rescan": succeed},
        lease_owner="retried-rescan-attempt",
    ).run(enqueued.job.job_id, org_id, project_id)

    assert completed.attempt_count == 2
    assert [(attempt.number, attempt.status) for attempt in completed.attempts] == [
        (1, "cancelled"),
        (2, "succeeded"),
    ]

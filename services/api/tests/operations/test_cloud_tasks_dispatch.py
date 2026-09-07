"""Cloud Tasks wire contract, tested without credentials or network access."""

import base64
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from clearcut.operations.adapters import cloud_tasks
from clearcut.operations.ports import job_dispatcher


class FakeCredentials:
    async def authorization(self) -> str:
        return "Bearer fake-access-token"


def config():
    return cloud_tasks.CloudTasksConfiguration(
        project_id="cinema",
        location="us-central1",
        queue="jobs",
        target_url="https://api.example.com/api/internal/jobs:execute",
        audience="https://api.example.com",
        service_account_email="tasks@cinema.iam.gserviceaccount.com",
    )


def envelope():
    return job_dispatcher.JobDispatchRequest(
        org_id=uuid4(),
        project_id=uuid4(),
        job_id=uuid4(),
        available_at=datetime(2026, 9, 7, tzinfo=UTC),
        attempt_count=0,
    )


@pytest.mark.asyncio
async def test_task_is_deterministic_minimal_scoped_and_oidc_authenticated():
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={"name": json.loads(request.content)["task"]["name"]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        dispatcher = cloud_tasks.CloudTasksClient(
            configuration=config(),
            client=client,
            credentials=FakeCredentials(),
        )
        command = envelope()
        first = await dispatcher.create_task(command)
        second = await dispatcher.create_task(command)
    assert first.task_name == second.task_name
    assert first.status is job_dispatcher.DispatchStatus.CONFIRMED
    task = json.loads(requests[0].content)["task"]
    assert (
        str(requests[0].url)
        == "https://cloudtasks.googleapis.com/v2/projects/cinema/locations/us-central1/queues/jobs/tasks"
    )
    assert requests[0].headers["authorization"] == "Bearer fake-access-token"
    assert task["name"].startswith("projects/cinema/locations/us-central1/queues/jobs/tasks/cc-")
    assert task["httpRequest"]["httpMethod"] == "POST"
    assert task["httpRequest"]["url"] == config().target_url
    assert task["httpRequest"]["oidcToken"] == {
        "audience": config().audience,
        "serviceAccountEmail": config().service_account_email,
    }
    assert json.loads(base64.b64decode(task["httpRequest"]["body"])) == {
        "orgId": str(command.org_id),
        "projectId": str(command.project_id),
        "jobId": str(command.job_id),
    }
    assert task["scheduleTime"] == "2026-09-07T00:00:00Z"
    assert task["dispatchDeadline"] == "1800s"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status, expected", [(409, "already_exists"), (429, "error"), (503, "error"), (403, "error")]
)
async def test_provider_failures_are_typed_and_only_conflict_is_acknowledged(status, expected):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(status))
    ) as client:
        dispatcher = cloud_tasks.CloudTasksClient(
            configuration=config(), client=client, credentials=FakeCredentials()
        )
        if expected == "error":
            with pytest.raises(job_dispatcher.JobDispatchError):
                await dispatcher.create_task(envelope())
        else:
            result = await dispatcher.create_task(envelope())
            assert result.status is job_dispatcher.DispatchStatus.ALREADY_EXISTS


def test_task_identity_changes_for_human_retry_even_before_first_attempt():
    from dataclasses import replace

    command = envelope()
    assert cloud_tasks.task_name(config(), command) != cloud_tasks.task_name(
        config(),
        replace(command, available_at=command.available_at + timedelta(seconds=1)),
    )
    assert cloud_tasks.task_name(config(), command) != cloud_tasks.task_name(
        config(),
        replace(command, org_id=uuid4()),
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://api.example.com/api/internal/jobs:execute",
        "https://other.example.com/api/internal/jobs:execute",
        "https://api.example.com/wrong",
        "https://api.example.com/api/internal/jobs:execute?x=1",
    ],
)
def test_dispatch_configuration_rejects_insecure_or_cross_service_target(url):
    from dataclasses import replace

    with pytest.raises(ValueError):
        replace(config(), target_url=url)


@pytest.mark.asyncio
async def test_cloud_tasks_job_dispatcher_schedules_and_confirms_outbox():
    from clearcut.operations.domain.jobs import RunStatus
    from clearcut.operations.ports.job_repository import JobTarget
    from fastapi import BackgroundTasks

    command = envelope()
    job = job_dispatcher.JobRecord(
        job_id=command.job_id,
        org_id=command.org_id,
        project_id=command.project_id,
        actor_id=None,
        correlation_id=uuid4(),
        job_type="detection",
        target=JobTarget("script_version", uuid4()),
        status=RunStatus.QUEUED,
        idempotency_key="key-1",
        payload={"schemaVersion": 1, "target": {"type": "script_version", "id": str(uuid4())}},
        progress=0.0,
        stage="queued",
        result_summary=None,
        error=None,
        attempt_count=0,
        attempts=(),
        history=(),
        available_at=command.available_at,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        lease_owner=None,
        lease_expires_at=None,
    )

    created_tasks = []
    confirmed_tasks = []

    class MockClient(job_dispatcher.TaskClientPort):
        async def create_task(
            self, cmd: job_dispatcher.JobDispatchRequest
        ) -> job_dispatcher.DispatchReceipt:
            created_tasks.append(cmd)
            return job_dispatcher.DispatchReceipt(
                job_dispatcher.DispatchStatus.CONFIRMED, "tasks/123"
            )

    class MockOutbox(job_dispatcher.DispatchOutboxPort):
        async def pending_dispatches(self, *, limit: int = 100):
            return ()

        async def confirm_dispatch(
            self, cmd: job_dispatcher.JobDispatchRequest
        ) -> job_dispatcher.DispatchReceipt:
            confirmed_tasks.append(cmd)
            return job_dispatcher.DispatchReceipt(job_dispatcher.DispatchStatus.CONFIRMED)

    dispatcher = cloud_tasks.CloudTasksJobDispatcher(
        client=MockClient(),
        outbox=MockOutbox(),
    )
    bg = BackgroundTasks()
    receipt = dispatcher.dispatch(bg, job)

    assert receipt.status is job_dispatcher.DispatchStatus.SCHEDULED
    assert len(bg.tasks) == 1

    # Execute the background task
    for task in bg.tasks:
        await task()

    assert created_tasks == [command]
    assert confirmed_tasks == [command]

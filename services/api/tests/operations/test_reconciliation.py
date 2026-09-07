"""Test outbox reconciliation and expired lease recovery."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from clearcut.bootstrap.settings import ClearcutSettings
from clearcut.main import create_app
from clearcut.operations.adapters.cloud_tasks import (
    UnverifiedTokenVerifier,
)
from clearcut.operations.application.reconcile_jobs import (
    InMemoryDispatchOutbox,
    ReconcileJobsService,
)
from clearcut.operations.ports.job_dispatcher import (
    DispatchReceipt,
    DispatchStatus,
    JobDispatchError,
    JobDispatchRequest,
    TaskClientPort,
)
from clearcut.operations.ports.job_repository import (
    EnqueueJob,
    JobRecord,
    JobRepositoryPort,
)
from httpx import ASGITransport, AsyncClient

AUDIENCE = "https://api.example.com"
CALLER_EMAIL = "tasks-caller@cinema.iam.gserviceaccount.com"
ISSUER = "https://accounts.google.com"


def _make_jwt(claims: dict) -> str:
    header = (
        base64.urlsafe_b64encode(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
        .decode()
        .rstrip("=")
    )
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"{header}.{payload}.fake-sig"


def _valid_token() -> str:
    return _make_jwt(
        {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "email": CALLER_EMAIL,
            "email_verified": True,
            "sub": "1234567890",
        }
    )


class MockTaskClient(TaskClientPort):
    def __init__(self, outcomes: dict[UUID, DispatchStatus | str] | None = None) -> None:
        self._outcomes = outcomes or {}
        self.dispatched: list[JobDispatchRequest] = []

    async def create_task(self, command: JobDispatchRequest) -> DispatchReceipt:
        self.dispatched.append(command)
        outcome = self._outcomes.get(command.job_id, DispatchStatus.CONFIRMED)
        if outcome == "error":
            raise JobDispatchError("Delivery could not be confirmed.")
        status = outcome if isinstance(outcome, DispatchStatus) else DispatchStatus(outcome)
        return DispatchReceipt(status=status, task_name=f"tasks/{command.job_id}")


class MockJobRepository(JobRepositoryPort):
    def __init__(self, recovered: list[JobRecord] | None = None) -> None:
        self._recovered = recovered or []
        self.access_count = 0

    async def enqueue(self, command: EnqueueJob):
        raise NotImplementedError

    async def list(self, **kwargs):
        raise NotImplementedError

    async def get(self, **kwargs):
        raise NotImplementedError

    async def claim(self, **kwargs):
        raise NotImplementedError

    async def renew_lease(self, **kwargs):
        raise NotImplementedError

    async def update_progress(self, **kwargs):
        raise NotImplementedError

    async def succeed(self, **kwargs):
        raise NotImplementedError

    async def fail(self, **kwargs):
        raise NotImplementedError

    async def retry(self, **kwargs):
        raise NotImplementedError

    async def cancel(self, **kwargs):
        raise NotImplementedError

    async def recover_interrupted_local_jobs(self) -> tuple[JobRecord, ...]:
        self.access_count += 1
        return tuple(self._recovered)


@pytest.mark.asyncio
async def test_reconcile_service_dispatches_pending_and_recovers_expired_leases():
    cmd1 = JobDispatchRequest(uuid4(), uuid4(), uuid4(), datetime.now(UTC), 0)
    cmd2 = JobDispatchRequest(uuid4(), uuid4(), uuid4(), datetime.now(UTC), 0)
    cmd3 = JobDispatchRequest(uuid4(), uuid4(), uuid4(), datetime.now(UTC), 0)

    outbox = InMemoryDispatchOutbox([cmd1, cmd2, cmd3])
    # cmd1 -> CONFIRMED, cmd2 -> ALREADY_EXISTS (also confirmed), cmd3 -> error (remains pending)
    client = MockTaskClient(
        {
            cmd1.job_id: DispatchStatus.CONFIRMED,
            cmd2.job_id: DispatchStatus.ALREADY_EXISTS,
            cmd3.job_id: "error",
        }
    )
    repo = MockJobRepository()

    service = ReconcileJobsService(outbox=outbox, client=client, repository=repo)
    result = await service.reconcile()

    assert result.dispatched_count == 2
    assert result.failed_count == 1
    assert result.recovered_count == 0
    assert outbox.confirmed == [cmd1, cmd2]
    # cmd3 remains pending in outbox
    remaining = await outbox.pending_dispatches()
    assert remaining == (cmd3,)


@pytest.mark.asyncio
async def test_reconcile_endpoint_requires_strict_oidc_auth():
    settings = ClearcutSettings.from_environment(
        {
            "CLEARCUT_DEPLOYMENT_PROFILE": "local",
            "CLEARCUT_STORAGE_ADAPTER": "filesystem",
            "CLEARCUT_STORAGE_PATH": "/tmp/test-storage",
            "CLEARCUT_DISPATCH_ADAPTER": "local",
            "CLEARCUT_DISPATCH_ENABLED": "true",
        }
    )
    app = create_app(settings)
    app.state.token_verifier = UnverifiedTokenVerifier()
    app.state.settings = ClearcutSettings.model_validate(
        {
            "profile": "gcp",
            "database": {"url": "postgresql+asyncpg://user:pass@localhost:5432/clearcut"},
            "storage": {"adapter": "gcs", "bucket": "test-bucket", "project_id": "cinema"},
            "dispatch": {
                "adapter": "cloud_tasks",
                "enabled": True,
                "project_id": "cinema",
                "location": "us-central1",
                "queue": "jobs",
                "target_url": "https://api.example.com/api/internal/jobs:execute",
                "audience": AUDIENCE,
                "service_account_email": CALLER_EMAIL,
            },
            "authentication": {"adapter": "builtin"},
            "secrets": {"backend": "secret_manager"},
        }
    )

    outbox = InMemoryDispatchOutbox()
    client = MockTaskClient()
    repo = MockJobRepository()
    app.state.reconcile_jobs_service = ReconcileJobsService(
        outbox=outbox, client=client, repository=repo
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://api.example.com"
    ) as http_client:
        # 1. No auth -> 401
        res_no_auth = await http_client.post("/api/internal/jobs:reconcile")
        assert res_no_auth.status_code == 401

        # 2. Wrong audience -> 403
        bad_token = _make_jwt(
            {
                "iss": ISSUER,
                "aud": "https://wrong.example.com",
                "email": CALLER_EMAIL,
                "email_verified": True,
            }
        )
        res_bad_aud = await http_client.post(
            "/api/internal/jobs:reconcile",
            headers={"authorization": f"Bearer {bad_token}"},
        )
        assert res_bad_aud.status_code == 403

        # 3. Valid token -> 200
        valid_token = _valid_token()
        res_valid = await http_client.post(
            "/api/internal/jobs:reconcile",
            headers={"authorization": f"Bearer {valid_token}"},
        )
        assert res_valid.status_code == 200
        data = res_valid.json()["data"]
        assert data["dispatchedCount"] == 0
        assert data["recoveredCount"] == 0
        assert data["failedCount"] == 0

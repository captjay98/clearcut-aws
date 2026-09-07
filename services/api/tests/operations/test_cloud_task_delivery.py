"""Test protected Cloud Tasks execution and strict Google OIDC verification."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
import uuid6
from clearcut.bootstrap.settings import (
    ClearcutSettings,
)
from clearcut.main import create_app
from clearcut.operations.adapters.cloud_tasks import (
    UnverifiedTokenVerifier,
)
from clearcut.operations.application.run_job import JobExecutionResult, RunJobService
from clearcut.operations.domain.jobs import RunStatus
from clearcut.operations.ports.job_repository import (
    EnqueueJob,
    JobAttempt,
    JobPage,
    JobRecord,
    JobRepositoryPort,
    JobTarget,
    SafeJobError,
)
from httpx import ASGITransport, AsyncClient

AUDIENCE = "https://api.example.com"
CALLER_EMAIL = "tasks-caller@cinema.iam.gserviceaccount.com"
ISSUER = "https://accounts.google.com"


def _make_jwt(claims: dict[str, Any]) -> str:
    header = (
        base64.urlsafe_b64encode(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
        .decode()
        .rstrip("=")
    )
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    sig = "fake-sig"
    return f"{header}.{payload}.{sig}"


def _valid_token(
    *,
    iss: str = ISSUER,
    aud: str = AUDIENCE,
    email: str = CALLER_EMAIL,
    email_verified: bool = True,
) -> str:
    return _make_jwt(
        {
            "iss": iss,
            "aud": aud,
            "email": email,
            "email_verified": email_verified,
            "sub": "1234567890",
        }
    )


class FakeTokenVerifier:
    def __init__(self, claims: dict[str, Any] | None = None, should_fail: bool = False) -> None:
        self._claims = claims
        self._should_fail = should_fail
        self._unverified = UnverifiedTokenVerifier()

    def verify_token(self, token: str, *, audience: str) -> dict[str, Any]:
        if self._should_fail:
            raise RuntimeError("Invalid token signature or expired token.")
        if self._claims is not None:
            return self._claims
        return self._unverified.verify_token(token, audience=audience)


class MockJobRepository(JobRepositoryPort):
    def __init__(self) -> None:
        self.jobs: dict[tuple[UUID, UUID, UUID], JobRecord] = {}
        self.access_count = 0

    async def enqueue(self, command: EnqueueJob) -> Any:
        raise NotImplementedError

    async def list(
        self, *, org_id: UUID, project_id: UUID, limit: int = 50, cursor: UUID | None = None
    ) -> JobPage:
        raise NotImplementedError

    async def get(self, *, org_id: UUID, project_id: UUID, job_id: UUID) -> JobRecord | None:
        self.access_count += 1
        return self.jobs.get((org_id, project_id, job_id))

    async def claim(
        self, *, org_id: UUID, project_id: UUID, job_id: UUID, lease_owner: str
    ) -> JobRecord | None:
        self.access_count += 1
        job = self.jobs.get((org_id, project_id, job_id))
        if job is None:
            return None
        if job.status not in {RunStatus.QUEUED, RunStatus.RETRY_WAIT}:
            return None
        claimed = JobRecord(
            job_id=job.job_id,
            org_id=job.org_id,
            project_id=job.project_id,
            actor_id=job.actor_id,
            correlation_id=job.correlation_id,
            job_type=job.job_type,
            target=job.target,
            status=RunStatus.RUNNING,
            idempotency_key=job.idempotency_key,
            payload=job.payload,
            progress=0.1,
            stage="running",
            result_summary=None,
            error=None,
            attempt_count=job.attempt_count + 1,
            attempts=job.attempts
            + (
                JobAttempt(
                    number=job.attempt_count + 1,
                    status="running",
                    started_at=datetime.now(UTC),
                    completed_at=None,
                    error=None,
                ),
            ),
            history=job.history,
            available_at=job.available_at,
            created_at=job.created_at,
            updated_at=datetime.now(UTC),
            lease_owner=lease_owner,
            lease_expires_at=datetime.now(UTC),
        )
        self.jobs[(org_id, project_id, job_id)] = claimed
        return claimed

    async def renew_lease(
        self, *, org_id: UUID, project_id: UUID, job_id: UUID, attempt_number: int, lease_owner: str
    ) -> JobRecord:
        raise NotImplementedError

    async def update_progress(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        job_id: UUID,
        attempt_number: int,
        lease_owner: str,
        progress: float,
        stage: str,
    ) -> JobRecord:
        raise NotImplementedError

    async def succeed(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        job_id: UUID,
        attempt_number: int,
        lease_owner: str,
        summary: dict[str, Any],
    ) -> JobRecord:
        self.access_count += 1
        job = self.jobs[(org_id, project_id, job_id)]
        completed = JobRecord(
            job_id=job.job_id,
            org_id=job.org_id,
            project_id=job.project_id,
            actor_id=job.actor_id,
            correlation_id=job.correlation_id,
            job_type=job.job_type,
            target=job.target,
            status=RunStatus.SUCCEEDED,
            idempotency_key=job.idempotency_key,
            payload=job.payload,
            progress=1.0,
            stage="succeeded",
            result_summary=summary,
            error=None,
            attempt_count=job.attempt_count,
            attempts=job.attempts,
            history=job.history,
            available_at=job.available_at,
            created_at=job.created_at,
            updated_at=datetime.now(UTC),
            lease_owner=None,
            lease_expires_at=None,
        )
        self.jobs[(org_id, project_id, job_id)] = completed
        return completed

    async def fail(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        job_id: UUID,
        attempt_number: int,
        lease_owner: str,
        error: SafeJobError,
    ) -> JobRecord:
        raise NotImplementedError

    async def retry(
        self, *, org_id: UUID, project_id: UUID, job_id: UUID, actor_id: UUID
    ) -> JobRecord:
        raise NotImplementedError

    async def cancel(
        self, *, org_id: UUID, project_id: UUID, job_id: UUID, actor_id: UUID
    ) -> JobRecord:
        raise NotImplementedError

    async def recover_interrupted_local_jobs(self) -> tuple[JobRecord, ...]:
        return ()


def _test_app(repo: MockJobRepository, *, verifier: Any = None):
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
    app.state.job_repository = repo
    app.state.token_verifier = verifier or FakeTokenVerifier()
    # Configure dispatch settings on app state for internal routes
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

    async def mock_processor(job: JobRecord) -> JobExecutionResult:
        return JobExecutionResult(summary={"detectedCount": 5})

    app.state.job_runner = RunJobService(
        repository=repo,
        processors={"detection": mock_processor},
        lease_owner="test-worker",
    )
    return app


@pytest.mark.asyncio
async def test_execution_route_rejects_missing_or_malformed_auth_before_repo_access():
    repo = MockJobRepository()
    app = _test_app(repo)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://api.example.com"
    ) as client:
        # Missing auth header
        res1 = await client.post(
            "/api/internal/jobs:execute",
            json={"orgId": str(uuid4()), "projectId": str(uuid4()), "jobId": str(uuid4())},
        )
        assert res1.status_code == 401
        assert res1.json()["error"]["code"] == "authentication_required"

        # Malformed scheme
        res2 = await client.post(
            "/api/internal/jobs:execute",
            json={"orgId": str(uuid4()), "projectId": str(uuid4()), "jobId": str(uuid4())},
            headers={"authorization": "Basic abc123"},
        )
        assert res2.status_code == 401
        assert res2.json()["error"]["code"] == "authentication_required"

    assert repo.access_count == 0, "Repository must NOT be accessed when auth fails"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "token_kwargs, expected_status, expected_code",
    [
        ({"iss": "https://malicious.issuer.com"}, 403, "permission_denied"),
        ({"aud": "https://wrong-audience.example.com"}, 403, "permission_denied"),
        ({"email": "attacker@cinema.iam.gserviceaccount.com"}, 403, "permission_denied"),
        ({"email_verified": False}, 403, "permission_denied"),
    ],
)
async def test_execution_route_rejects_invalid_claims_before_repo_access(
    token_kwargs, expected_status, expected_code
):
    repo = MockJobRepository()
    app = _test_app(repo)
    token = _valid_token(**token_kwargs)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://api.example.com"
    ) as client:
        res = await client.post(
            "/api/internal/jobs:execute",
            json={"orgId": str(uuid4()), "projectId": str(uuid4()), "jobId": str(uuid4())},
            headers={"authorization": f"Bearer {token}"},
        )
        assert res.status_code == expected_status
        assert res.json()["error"]["code"] == expected_code

    assert repo.access_count == 0, "Repository must NOT be accessed on claim mismatch"


@pytest.mark.asyncio
async def test_execution_route_executes_job_with_valid_token():
    repo = MockJobRepository()
    app = _test_app(repo)
    org_id, project_id, job_id = uuid4(), uuid4(), uuid6.uuid7()
    now = datetime.now(UTC)

    repo.jobs[(org_id, project_id, job_id)] = JobRecord(
        job_id=job_id,
        org_id=org_id,
        project_id=project_id,
        actor_id=uuid4(),
        correlation_id=uuid6.uuid7(),
        job_type="detection",
        target=JobTarget(type="script_version", id=uuid4()),
        status=RunStatus.QUEUED,
        idempotency_key="det-1",
        payload={"schemaVersion": 1, "target": {"type": "script_version", "id": str(uuid4())}},
        progress=0.0,
        stage="queued",
        result_summary=None,
        error=None,
        attempt_count=0,
        attempts=(),
        history=(),
        available_at=now,
        created_at=now,
        updated_at=now,
        lease_owner=None,
        lease_expires_at=None,
    )

    token = _valid_token()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://api.example.com"
    ) as client:
        res = await client.post(
            "/api/internal/jobs:execute",
            json={"orgId": str(org_id), "projectId": str(project_id), "jobId": str(job_id)},
            headers={"authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["jobId"] == str(job_id)
        assert data["status"] == "succeeded"
        assert data["resultSummary"] == {"detectedCount": 5}


@pytest.mark.asyncio
async def test_duplicate_delivery_is_idempotent():
    repo = MockJobRepository()
    app = _test_app(repo)
    org_id, project_id, job_id = uuid4(), uuid4(), uuid6.uuid7()
    now = datetime.now(UTC)

    repo.jobs[(org_id, project_id, job_id)] = JobRecord(
        job_id=job_id,
        org_id=org_id,
        project_id=project_id,
        actor_id=uuid4(),
        correlation_id=uuid6.uuid7(),
        job_type="detection",
        target=JobTarget(type="script_version", id=uuid4()),
        status=RunStatus.QUEUED,
        idempotency_key="det-dup",
        payload={"schemaVersion": 1, "target": {"type": "script_version", "id": str(uuid4())}},
        progress=0.0,
        stage="queued",
        result_summary=None,
        error=None,
        attempt_count=0,
        attempts=(),
        history=(),
        available_at=now,
        created_at=now,
        updated_at=now,
        lease_owner=None,
        lease_expires_at=None,
    )

    token = _valid_token()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://api.example.com"
    ) as client:
        first = await client.post(
            "/api/internal/jobs:execute",
            json={"orgId": str(org_id), "projectId": str(project_id), "jobId": str(job_id)},
            headers={"authorization": f"Bearer {token}"},
        )
        assert first.status_code == 200
        assert first.json()["data"]["status"] == "succeeded"

        # Duplicate delivery of already-succeeded job
        second = await client.post(
            "/api/internal/jobs:execute",
            json={"orgId": str(org_id), "projectId": str(project_id), "jobId": str(job_id)},
            headers={"authorization": f"Bearer {token}"},
        )
        assert second.status_code == 200
        assert second.json()["data"]["status"] == "succeeded"
        assert second.json()["data"]["attemptCount"] == 1


@pytest.mark.asyncio
async def test_execution_route_returns_404_for_unknown_job():
    repo = MockJobRepository()
    app = _test_app(repo)
    token = _valid_token()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://api.example.com"
    ) as client:
        res = await client.post(
            "/api/internal/jobs:execute",
            json={"orgId": str(uuid4()), "projectId": str(uuid4()), "jobId": str(uuid4())},
            headers={"authorization": f"Bearer {token}"},
        )
        assert res.status_code == 404
        assert res.json()["error"]["code"] == "not_found"

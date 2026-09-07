from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
import uuid6
from clearcut.database import session_scope
from clearcut.detection.adapters.hermetic_runtime import HermeticDetectionRuntime
from clearcut.detection.runtime_provider import get_detection_runtime
from clearcut.main import app
from clearcut.operations.adapters.sql_job_repository import SqlJobRepository
from clearcut.operations.application.run_job import (
    JobExecutionError,
    RunJobService,
)
from clearcut.operations.ports.job_repository import EnqueueJob, SafeJobError
from httpx import ASGITransport, AsyncClient


async def _client() -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"origin": "http://test"},
    )


async def _create_project(
    client: AsyncClient,
    suffix: str,
) -> tuple[UUID, UUID, UUID]:
    registration = await client.post(
        "/api/v1/users",
        json={
            "name": f"Job User {suffix}",
            "email": f"job-http-{suffix}-{uuid4().hex}@example.com",
            "password": "Password123!",
        },
    )
    assert registration.status_code == 201, registration.text
    context = await client.get("/api/v1/session-context")
    actor_id = UUID(context.json()["data"]["userId"])
    organization = await client.post(
        "/api/v1/organizations",
        json={"name": f"Job Studio {suffix}", "slug": f"job-{suffix}-{uuid4().hex[:8]}"},
    )
    assert organization.status_code == 201, organization.text
    org_id = UUID(organization.json()["data"]["orgId"])
    project = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        json={"title": f"Job Project {suffix}"},
    )
    assert project.status_code == 201, project.text
    return org_id, UUID(project.json()["data"]["projectId"]), actor_id


def _command(
    org_id: UUID,
    project_id: UUID,
    actor_id: UUID,
    key: str,
    *,
    job_type: str = "test",
) -> EnqueueJob:
    target_type = {
        "detection": "script_version",
        "research": "clearance_item",
    }.get(job_type, "project")
    return EnqueueJob(
        org_id=org_id,
        project_id=project_id,
        actor_id=actor_id,
        job_type=job_type,
        idempotency_key=key,
        payload={
            "schemaVersion": 1,
            "target": {"type": target_type, "id": str(project_id)},
        },
        audit_action=f"{job_type}.started",
        target_type="project",
        target_id=project_id,
    )


class RecordingDispatcher:
    mode = "local"
    durable = False

    def __init__(self, repository: SqlJobRepository) -> None:
        self.repository = repository
        self.dispatched: list[UUID] = []
        self.observed_committed: list[UUID] = []

    def dispatch(self, background_tasks, job) -> None:
        self.dispatched.append(job.job_id)

        async def observe_commit() -> None:
            persisted = await self.repository.get(
                org_id=job.org_id,
                project_id=job.project_id,
                job_id=job.job_id,
            )
            if persisted is not None:
                self.observed_committed.append(persisted.job_id)

        background_tasks.add_task(observe_commit)


@pytest.mark.asyncio
async def test_job_reads_are_scoped_and_return_safe_lifecycle_fields() -> None:
    repository = SqlJobRepository()
    original_repository = app.state.job_repository
    app.state.job_repository = repository
    try:
        async with await _client() as owner:
            org_id, project_id, actor_id = await _create_project(owner, "owner")
            enqueued = await repository.enqueue(
                _command(org_id, project_id, actor_id, "test:http-read")
            )

            listed = await owner.get(f"/api/v1/organizations/{org_id}/projects/{project_id}/jobs")
            detail = await owner.get(
                f"/api/v1/organizations/{org_id}/projects/{project_id}/jobs/{enqueued.job.job_id}"
            )

        assert listed.status_code == 200, listed.text
        assert listed.json()["meta"]["totalCount"] == 1
        assert len(listed.json()["data"]) == 1
        assert detail.status_code == 200, detail.text
        assert detail.json()["data"] == listed.json()["data"][0]
        assert detail.json()["data"] == {
            "jobId": str(enqueued.job.job_id),
            "status": "queued",
            "jobType": "test",
            "target": {"type": "project", "id": str(project_id)},
            "canRetry": False,
            "progress": 0.0,
            "stage": "queued",
            "resultSummary": None,
            "error": None,
            "attemptCount": 0,
            "attempts": [],
            "history": [],
            "availableAt": detail.json()["data"]["availableAt"],
            "createdAt": detail.json()["data"]["createdAt"],
            "updatedAt": detail.json()["data"]["updatedAt"],
        }

        async with await _client() as other:
            other_org, other_project, _other_actor = await _create_project(other, "other")
            denied = await other.get(
                f"/api/v1/organizations/{other_org}/projects/{other_project}/jobs/"
                f"{enqueued.job.job_id}"
            )
        assert denied.status_code == 404
        assert denied.json()["error"]["code"] == "not_found"
    finally:
        app.state.job_repository = original_repository


@pytest.mark.asyncio
async def test_retry_and_cancel_are_transactional_and_dispatch_after_commit() -> None:
    repository = SqlJobRepository()
    dispatcher = RecordingDispatcher(repository)
    original_repository = app.state.job_repository
    original_dispatcher = app.state.job_dispatcher
    app.state.job_repository = repository
    app.state.job_dispatcher = dispatcher
    try:
        async with await _client() as client:
            org_id, project_id, actor_id = await _create_project(client, "mutations")
            failed_job = await repository.enqueue(
                _command(org_id, project_id, actor_id, "test:http-retry")
            )

            async def fail(_job):
                raise JobExecutionError(
                    SafeJobError(
                        code="provider_unavailable",
                        message="The provider is unavailable.",
                        retryable=True,
                    )
                )

            await RunJobService(
                repository=repository,
                processors={"test": fail},
                lease_owner="http-test",
            ).run(failed_job.job.job_id, org_id, project_id)

            retried = await client.post(
                f"/api/v1/organizations/{org_id}/projects/{project_id}/jobs/"
                f"{failed_job.job.job_id}:retry"
            )
            assert retried.status_code == 200, retried.text
            assert retried.json()["data"]["status"] == "queued"
            assert dispatcher.dispatched == [failed_job.job.job_id]
            assert dispatcher.observed_committed == [failed_job.job.job_id]

            queued_job = await repository.enqueue(
                _command(org_id, project_id, actor_id, "test:http-cancel")
            )
            cancelled = await client.post(
                f"/api/v1/organizations/{org_id}/projects/{project_id}/jobs/"
                f"{queued_job.job.job_id}:cancel"
            )
            duplicate_cancel = await client.post(
                f"/api/v1/organizations/{org_id}/projects/{project_id}/jobs/"
                f"{queued_job.job.job_id}:cancel"
            )

        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["data"]["status"] == "cancelled"
        assert duplicate_cancel.status_code == 409
        assert duplicate_cancel.json()["error"]["code"] == "conflict"
    finally:
        app.state.job_repository = original_repository
        app.state.job_dispatcher = original_dispatcher


@pytest.mark.asyncio
async def test_detection_dispatches_once_only_after_job_commit() -> None:
    repository = SqlJobRepository()
    dispatcher = RecordingDispatcher(repository)
    original_repository = app.state.job_repository
    original_dispatcher = app.state.job_dispatcher
    app.state.job_repository = repository
    app.state.job_dispatcher = dispatcher
    app.dependency_overrides[get_detection_runtime] = lambda: HermeticDetectionRuntime()
    try:
        async with await _client() as client:
            org_id, project_id, actor_id = await _create_project(client, "dispatch")
            script_id = uuid4()
            version_id = uuid4()
            async with session_scope() as session:
                await session.execute(
                    sa.text(
                        "INSERT INTO scripts "
                        "(id, org_id, project_id, title, current_slot, created_at) "
                        "VALUES (:id, :org, :project, 'Dispatch test', 'current', CURRENT_TIMESTAMP)"
                    ),
                    {"id": str(script_id), "org": str(org_id), "project": str(project_id)},
                )
                await session.execute(
                    sa.text(
                        "INSERT INTO script_versions "
                        "(id, script_id, org_id, project_id, ordinal, source_hash, "
                        "parser_version, created_at) VALUES "
                        "(:id, :script, :org, :project, 1, 'hash', '1.0', CURRENT_TIMESTAMP)"
                    ),
                    {
                        "id": str(version_id),
                        "script": str(script_id),
                        "org": str(org_id),
                        "project": str(project_id),
                    },
                )

            first = await client.post(
                f"/api/v1/organizations/{org_id}/projects/{project_id}/"
                f"script-versions/{version_id}:detect"
            )
            duplicate = await client.post(
                f"/api/v1/organizations/{org_id}/projects/{project_id}/"
                f"script-versions/{version_id}:detect"
            )

        assert first.status_code == 202, first.text
        assert duplicate.status_code == 202, duplicate.text
        assert duplicate.json()["data"]["jobId"] == first.json()["data"]["jobId"]
        assert dispatcher.dispatched == [UUID(first.json()["data"]["jobId"])]
        assert dispatcher.observed_committed == dispatcher.dispatched

        async with session_scope() as session:
            audit_count = (
                await session.execute(
                    sa.text(
                        "SELECT count(*) FROM authoritative_audit_events "
                        "WHERE org_id = :org AND project_id = :project "
                        "AND action = 'detection.started'"
                    ),
                    {"org": str(org_id), "project": str(project_id)},
                )
            ).scalar_one()
        assert audit_count == 1
        assert actor_id
    finally:
        app.state.job_repository = original_repository
        app.state.job_dispatcher = original_dispatcher
        app.dependency_overrides.pop(get_detection_runtime, None)


@pytest.mark.asyncio
async def test_health_discloses_local_dispatch_is_not_durable() -> None:
    repository = SqlJobRepository()
    dispatcher = RecordingDispatcher(repository)
    original_dispatcher = app.state.job_dispatcher
    app.state.job_dispatcher = dispatcher
    try:
        async with await _client() as client:
            response = await client.get("/healthz")
        assert response.status_code == 200
        assert response.json()["jobDispatch"] == {
            "mode": "local",
            "durable": False,
        }
        assert response.json()["deployment"] == {
            "profile": "local",
            "databaseConfigured": True,
            "storageAdapter": "filesystem",
            "dispatchAdapter": "local",
            "dispatchEnabled": True,
            "authenticationAdapter": "builtin",
            "secretBackend": "environment",
            "paidProvidersEnabled": [],
        }
    finally:
        app.state.job_dispatcher = original_dispatcher


@pytest.mark.asyncio
async def test_cancelled_detection_retry_is_redispatched_after_commit() -> None:
    repository = SqlJobRepository()
    dispatcher = RecordingDispatcher(repository)
    original_repository = app.state.job_repository
    original_dispatcher = app.state.job_dispatcher
    app.state.job_repository = repository
    app.state.job_dispatcher = dispatcher
    try:
        async with await _client() as client:
            org_id, project_id, actor_id = await _create_project(client, "cancelled-retry")
            enqueued = await repository.enqueue(
                _command(
                    org_id,
                    project_id,
                    actor_id,
                    "detection:http-cancelled-retry",
                    job_type="detection",
                )
            )
            claimed = await repository.claim(
                org_id=org_id,
                project_id=project_id,
                job_id=enqueued.job.job_id,
                lease_owner="cancelled-http-attempt",
            )
            assert claimed is not None
            await repository.cancel(
                org_id=org_id,
                project_id=project_id,
                job_id=enqueued.job.job_id,
                actor_id=actor_id,
            )

            retried = await client.post(
                f"/api/v1/organizations/{org_id}/projects/{project_id}/jobs/"
                f"{enqueued.job.job_id}:retry"
            )

        assert retried.status_code == 200, retried.text
        data = retried.json()["data"]
        assert data["jobId"] == str(enqueued.job.job_id)
        assert data["status"] == "queued"
        assert [(attempt["number"], attempt["status"]) for attempt in data["attempts"]] == [
            (1, "cancelled")
        ]
        assert data["canRetry"] is False
        assert dispatcher.dispatched == [enqueued.job.job_id]
        assert dispatcher.observed_committed == [enqueued.job.job_id]
    finally:
        app.state.job_repository = original_repository
        app.state.job_dispatcher = original_dispatcher


@pytest.mark.asyncio
async def test_queued_detection_cancellation_remains_in_public_history_after_retry() -> None:
    repository = SqlJobRepository()
    dispatcher = RecordingDispatcher(repository)
    original_repository = app.state.job_repository
    original_dispatcher = app.state.job_dispatcher
    app.state.job_repository = repository
    app.state.job_dispatcher = dispatcher
    try:
        async with await _client() as client:
            org_id, project_id, actor_id = await _create_project(client, "queued-history")
            enqueued = await repository.enqueue(
                _command(
                    org_id,
                    project_id,
                    actor_id,
                    "detection:queued-history",
                    job_type="detection",
                )
            )
            cancelled = await client.post(
                f"/api/v1/organizations/{org_id}/projects/{project_id}/jobs/"
                f"{enqueued.job.job_id}:cancel"
            )
            retried = await client.post(
                f"/api/v1/organizations/{org_id}/projects/{project_id}/jobs/"
                f"{enqueued.job.job_id}:retry"
            )

        assert cancelled.status_code == 200, cancelled.text
        assert retried.status_code == 200, retried.text
        data = retried.json()["data"]
        assert data["attemptCount"] == 0
        assert data["attempts"] == []
        assert [event["action"] for event in data["history"]] == [
            "cancelled",
            "retry_requested",
        ]
        assert all(event["actorId"] == str(actor_id) for event in data["history"])
        assert all(event["occurredAt"] for event in data["history"])
        assert dispatcher.dispatched == [enqueued.job.job_id]
    finally:
        app.state.job_repository = original_repository
        app.state.job_dispatcher = original_dispatcher


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case", "status_value"),
    [
        ("unsupported_job_type", "manual_retry"),
        ("missing_schema", "manual_retry"),
        ("unsupported_schema", "failed"),
        ("string_schema", "manual_retry"),
        ("float_schema", "manual_retry"),
        ("bool_schema", "cancelled"),
        ("missing_target", "manual_retry"),
        ("non_object_target", "manual_retry"),
        ("integer_target_id", "manual_retry"),
        ("null_target_id", "manual_retry"),
        ("extra_payload_key", "manual_retry"),
        ("extra_target_key", "failed"),
        ("malformed_target", "cancelled"),
        ("wrong_detection_target_kind", "cancelled"),
        ("wrong_research_target_kind", "manual_retry"),
    ],
)
async def test_job_http_hides_controls_for_invalid_complete_job_payloads(
    case: str,
    status_value: str,
) -> None:
    job_type = {
        "unsupported_job_type": "unsupported",
        "wrong_research_target_kind": "research",
    }.get(case, "detection")
    repository = SqlJobRepository()
    original_repository = app.state.job_repository
    app.state.job_repository = repository
    try:
        async with await _client() as owner:
            org_id, project_id, actor_id = await _create_project(
                owner,
                f"s-{case[:4].replace('_', '-')}",
            )
            command = _command(
                org_id,
                project_id,
                actor_id,
                f"{job_type}:http-invalid:{case}",
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
                command.payload["target"] = {
                    "type": "script_version",
                    "id": "not-a-uuid",
                }
            elif case in {"wrong_detection_target_kind", "wrong_research_target_kind"}:
                command.payload["target"] = {
                    "type": "project",
                    "id": str(project_id),
                }
            enqueued = await repository.enqueue(command)
            async with session_scope() as session:
                await session.execute(
                    sa.text(
                        "UPDATE jobs SET status = :status, stage = :status, error = :error "
                        "WHERE id = :job_id AND org_id = :org_id AND project_id = :project_id"
                    ),
                    {
                        "status": status_value,
                        "error": (
                            '{"code":"retryable","message":"Retryable.","retryable":true}'
                            if status_value == "failed"
                            else None
                        ),
                        "job_id": str(enqueued.job.job_id),
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                    },
                )

            listed = await owner.get(f"/api/v1/organizations/{org_id}/projects/{project_id}/jobs")
            detail = await owner.get(
                f"/api/v1/organizations/{org_id}/projects/{project_id}/jobs/{enqueued.job.job_id}"
            )
            retry = await owner.post(
                f"/api/v1/organizations/{org_id}/projects/{project_id}/jobs/"
                f"{enqueued.job.job_id}:retry"
            )

        expected_target = {
            "type": "legacy_unknown",
            "id": str(enqueued.job.job_id),
        }
        assert listed.status_code == 200, listed.text
        assert detail.status_code == 200, detail.text
        assert listed.json()["data"][0]["target"] == expected_target
        assert detail.json()["data"]["target"] == expected_target
        assert detail.json()["data"]["canRetry"] is False
        assert retry.status_code == 409, retry.text
        assert retry.json()["error"]["code"] == "conflict"
    finally:
        app.state.job_repository = original_repository


@pytest.mark.asyncio
async def test_job_api_never_serializes_out_of_contract_persisted_target_type() -> None:
    repository = SqlJobRepository()
    original_repository = app.state.job_repository
    app.state.job_repository = repository
    try:
        async with await _client() as owner:
            org_id, project_id, actor_id = await _create_project(owner, "malformed-target")
            command = _command(org_id, project_id, actor_id, "test:http-malformed-target")
            command.payload["target"] = {
                "type": "outside_openapi_contract",
                "id": str(project_id),
            }
            enqueued = await repository.enqueue(command)

            listed = await owner.get(f"/api/v1/organizations/{org_id}/projects/{project_id}/jobs")
            detail = await owner.get(
                f"/api/v1/organizations/{org_id}/projects/{project_id}/jobs/{enqueued.job.job_id}"
            )

        assert listed.status_code == 200, listed.text
        assert detail.status_code == 200, detail.text
        expected_target = {
            "type": "legacy_unknown",
            "id": str(enqueued.job.job_id),
        }
        assert listed.json()["data"][0]["target"] == expected_target
        assert detail.json()["data"]["target"] == expected_target
        assert detail.json()["data"]["canRetry"] is False
    finally:
        app.state.job_repository = original_repository


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "malicious_origin",
    ["https://test.attacker.example", "http://localhost:9999"],
)
async def test_governed_job_mutation_rejects_untrusted_origin(
    malicious_origin: str,
) -> None:
    repository = SqlJobRepository()
    original_repository = app.state.job_repository
    app.state.job_repository = repository
    try:
        async with await _client() as owner:
            org_id, project_id, actor_id = await _create_project(owner, "csrf-host-substring")
            enqueued = await repository.enqueue(
                _command(org_id, project_id, actor_id, "test:csrf-host-substring")
            )

            rejected = await owner.post(
                f"/api/v1/organizations/{org_id}/projects/{project_id}/jobs/"
                f"{enqueued.job.job_id}:cancel",
                headers={"origin": malicious_origin},
            )

        assert rejected.status_code == 403, rejected.text
        assert rejected.json()["error"]["code"] == "permission_denied"
        persisted = await repository.get(
            org_id=org_id,
            project_id=project_id,
            job_id=enqueued.job.job_id,
        )
        assert persisted is not None
        assert persisted.status.value == "queued"
    finally:
        app.state.job_repository = original_repository


@pytest.mark.asyncio
async def test_job_list_is_cursor_paginated_without_losing_total_count() -> None:
    repository = SqlJobRepository()
    original_repository = app.state.job_repository
    app.state.job_repository = repository
    try:
        async with await _client() as client:
            org_id, project_id, actor_id = await _create_project(client, "pagination")
            enqueued = [
                await repository.enqueue(
                    _command(
                        org_id,
                        project_id,
                        actor_id,
                        f"test:http-page:{index}",
                    )
                )
                for index in range(3)
            ]
            async with session_scope() as session:
                await session.execute(
                    sa.text(
                        "UPDATE jobs SET created_at = :created_at "
                        "WHERE org_id = :org_id AND project_id = :project_id"
                    ),
                    {
                        "created_at": "2026-08-31T12:00:00+00:00",
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                    },
                )

            first = await client.get(
                f"/api/v1/organizations/{org_id}/projects/{project_id}/jobs",
                params={"limit": 2},
            )
            assert first.status_code == 200, first.text
            first_data = first.json()["data"]
            assert len(first_data) == 2
            assert first.json()["meta"]["totalCount"] == 3
            assert first.json()["meta"]["nextCursor"] == first_data[-1]["jobId"]

            second = await client.get(
                f"/api/v1/organizations/{org_id}/projects/{project_id}/jobs",
                params={"limit": 2, "cursor": first.json()["meta"]["nextCursor"]},
            )

        assert second.status_code == 200, second.text
        assert len(second.json()["data"]) == 1
        assert second.json()["meta"]["totalCount"] == 3
        assert "nextCursor" not in second.json()["meta"]
        listed_ids = {item["jobId"] for item in first_data + second.json()["data"]}
        assert listed_ids == {str(result.job.job_id) for result in enqueued}
    finally:
        app.state.job_repository = original_repository


@pytest.mark.parametrize(
    "cursor",
    [str(uuid4()), "0190ABCD-ABCD-7ABC-8ABC-ABCDEFABCDEF"],
)
@pytest.mark.asyncio
async def test_job_list_rejects_noncanonical_uuid7_cursor(cursor: str) -> None:
    repository = SqlJobRepository()
    original_repository = app.state.job_repository
    app.state.job_repository = repository
    try:
        async with await _client() as client:
            org_id, project_id, _actor_id = await _create_project(client, "uuid7-cursor")
            response = await client.get(
                f"/api/v1/organizations/{org_id}/projects/{project_id}/jobs",
                params={"cursor": cursor},
            )

        assert response.status_code == 422
    finally:
        app.state.job_repository = original_repository


@pytest.mark.asyncio
async def test_job_list_missing_and_other_project_cursors_do_not_leak() -> None:
    repository = SqlJobRepository()
    original_repository = app.state.job_repository
    app.state.job_repository = repository
    try:
        async with await _client() as client:
            org_id, project_id, actor_id = await _create_project(client, "scoped-cursor")
            for index in range(2):
                await repository.enqueue(
                    _command(
                        org_id,
                        project_id,
                        actor_id,
                        f"test:scoped-cursor:{index}",
                    )
                )
            other_project_response = await client.post(
                f"/api/v1/organizations/{org_id}/projects",
                json={"title": "Other Cursor Project"},
            )
            assert other_project_response.status_code == 201
            other_project_id = UUID(other_project_response.json()["data"]["projectId"])
            other_job = await repository.enqueue(
                _command(
                    org_id,
                    other_project_id,
                    actor_id,
                    "test:other-project-cursor",
                )
            )

            responses = [
                await client.get(
                    f"/api/v1/organizations/{org_id}/projects/{project_id}/jobs",
                    params={"limit": 1, "cursor": str(cursor)},
                )
                for cursor in (uuid6.uuid7(), other_job.job.job_id)
            ]

        for response in responses:
            assert response.status_code == 200, response.text
            assert response.json()["data"] == []
            assert response.json()["meta"]["totalCount"] == 2
            assert "nextCursor" not in response.json()["meta"]
    finally:
        app.state.job_repository = original_repository

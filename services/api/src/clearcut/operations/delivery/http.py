"""Tenant-scoped observable job reads and governed lifecycle mutations."""

from typing import Annotated
from uuid import UUID

import uuid6
from clearcut.delivery_errors import error_response
from clearcut.identity.delivery.scope import RequestScope, get_request_scope
from clearcut.operations.ports.job_repository import (
    JobNotFoundError,
    JobRecord,
    JobTransitionError,
)
from clearcut.organizations.delivery.http import verify_csrf_origin
from fastapi import APIRouter, BackgroundTasks, Path, Query, Request, status
from fastapi.responses import JSONResponse

router = APIRouter(
    prefix="/api/v1/organizations/{orgId}/projects/{projectId}/jobs",
    tags=["operations"],
)

OrgIdParam = Annotated[str, Path(alias="orgId")]
ProjectIdParam = Annotated[str, Path(alias="projectId")]
JobIdParam = Annotated[str, Path(alias="jobId")]
UUIDV7_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"


async def _scope(request: Request, org_id: str, project_id: str) -> RequestScope:
    return await get_request_scope(request, org_id=org_id, project_id=project_id)


def _job_id(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


def _meta(
    *,
    total_count: int | None = None,
    next_cursor: UUID | None = None,
) -> dict[str, str | int]:
    result: dict[str, str | int] = {"requestId": str(uuid6.uuid7())}
    if total_count is not None:
        result["totalCount"] = total_count
    if next_cursor is not None:
        result["nextCursor"] = str(next_cursor)
    return result


def job_to_data(job: JobRecord) -> dict[str, object]:
    return {
        "jobId": str(job.job_id),
        "status": job.status.value,
        "jobType": job.job_type,
        "target": {"type": job.target.type, "id": str(job.target.id)},
        "canRetry": (
            job.target.type != "legacy_unknown"
            and (
                job.status.value == "manual_retry"
                or (job.status.value == "failed" and bool(job.error and job.error.retryable))
                or (job.status.value == "cancelled" and job.job_type == "detection")
            )
        ),
        "progress": job.progress,
        "stage": job.stage,
        "resultSummary": job.result_summary,
        "error": (
            {
                "code": job.error.code,
                "message": job.error.message,
                "retryable": job.error.retryable,
            }
            if job.error
            else None
        ),
        "attemptCount": job.attempt_count,
        "attempts": [
            {
                "number": attempt.number,
                "status": attempt.status,
                "startedAt": attempt.started_at.isoformat(),
                "completedAt": (attempt.completed_at.isoformat() if attempt.completed_at else None),
                "error": (
                    {
                        "code": attempt.error.code,
                        "message": attempt.error.message,
                        "retryable": attempt.error.retryable,
                    }
                    if attempt.error
                    else None
                ),
            }
            for attempt in job.attempts
        ],
        "history": [
            {
                "action": event.action,
                "actorId": str(event.actor_id),
                "occurredAt": event.occurred_at.isoformat(),
            }
            for event in job.history
        ],
        "availableAt": job.available_at.isoformat(),
        "createdAt": job.created_at.isoformat(),
        "updatedAt": job.updated_at.isoformat(),
    }


def _not_found() -> JSONResponse:
    return error_response(
        status_code=status.HTTP_404_NOT_FOUND,
        code="not_found",
        message="Job was not found.",
    )


def _conflict(error: JobTransitionError) -> JSONResponse:
    return error_response(
        status_code=status.HTTP_409_CONFLICT,
        code="conflict",
        message=str(error),
    )


@router.get("", operation_id="listJobs")
async def list_jobs(
    request: Request,
    org_id: OrgIdParam,
    project_id: ProjectIdParam,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(pattern=UUIDV7_PATTERN)] = None,
) -> dict:
    scope = await _scope(request, org_id, project_id)
    parsed_cursor = UUID(cursor) if cursor is not None else None
    page = await request.app.state.job_repository.list(
        org_id=scope.org_id,
        project_id=scope.project_id,
        limit=limit,
        cursor=parsed_cursor,
    )
    return {
        "data": [job_to_data(job) for job in page.jobs],
        "meta": _meta(
            total_count=page.total_count,
            next_cursor=page.next_cursor,
        ),
    }


@router.get("/{jobId}", operation_id="getJob")
async def get_job(
    request: Request,
    org_id: OrgIdParam,
    project_id: ProjectIdParam,
    job_id_raw: JobIdParam,
):
    scope = await _scope(request, org_id, project_id)
    parsed_job_id = _job_id(job_id_raw)
    if parsed_job_id is None:
        return _not_found()
    job = await request.app.state.job_repository.get(
        org_id=scope.org_id,
        project_id=scope.project_id,
        job_id=parsed_job_id,
    )
    if job is None:
        return _not_found()
    return {"data": job_to_data(job), "meta": _meta()}


@router.post("/{jobId}:retry", operation_id="retryJob")
async def retry_job(
    request: Request,
    background_tasks: BackgroundTasks,
    org_id: OrgIdParam,
    project_id: ProjectIdParam,
    job_id_raw: JobIdParam,
):
    verify_csrf_origin(request)
    scope = await _scope(request, org_id, project_id)
    parsed_job_id = _job_id(job_id_raw)
    if parsed_job_id is None:
        return _not_found()
    try:
        job = await request.app.state.job_repository.retry(
            org_id=scope.org_id,
            project_id=scope.project_id,
            job_id=parsed_job_id,
            actor_id=scope.user_id,
        )
    except JobNotFoundError:
        return _not_found()
    except JobTransitionError as error:
        return _conflict(error)
    request.app.state.job_dispatcher.dispatch(background_tasks, job)
    return {"data": job_to_data(job), "meta": _meta()}


@router.post("/{jobId}:cancel", operation_id="cancelJob")
async def cancel_job(
    request: Request,
    org_id: OrgIdParam,
    project_id: ProjectIdParam,
    job_id_raw: JobIdParam,
):
    verify_csrf_origin(request)
    scope = await _scope(request, org_id, project_id)
    parsed_job_id = _job_id(job_id_raw)
    if parsed_job_id is None:
        return _not_found()
    try:
        job = await request.app.state.job_repository.cancel(
            org_id=scope.org_id,
            project_id=scope.project_id,
            job_id=parsed_job_id,
            actor_id=scope.user_id,
        )
    except JobNotFoundError:
        return _not_found()
    except JobTransitionError as error:
        return _conflict(error)
    return {"data": job_to_data(job), "meta": _meta()}

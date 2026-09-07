"""Internal Cloud Tasks and Scheduler delivery routes protected by strict Google OIDC."""

from __future__ import annotations

from uuid import UUID

import uuid6
from clearcut.delivery_errors import error_response
from clearcut.operations.adapters.cloud_tasks import (
    OidcAuthError,
    verify_google_oidc_claims,
)
from clearcut.operations.application.reconcile_jobs import ReconcileJobsService
from clearcut.operations.application.run_job import RunJobService
from clearcut.operations.delivery.http import job_to_data
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(
    prefix="/api/internal",
    tags=["internal-operations"],
)


class ExecuteJobTaskBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    org_id: UUID = Field(alias="orgId")
    project_id: UUID = Field(alias="projectId")
    job_id: UUID = Field(alias="jobId")


def _authenticate_cloud_tasks_caller(request: Request) -> JSONResponse | None:
    """Validate Google OIDC issuer, audience, and dedicated caller before repo access."""
    authorization = request.headers.get("authorization")
    if not authorization:
        return error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="authentication_required",
            message="Google OIDC authorization is required.",
        )

    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.casefold() != "bearer" or not token.strip():
        return error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="authentication_required",
            message="Bearer token authorization is required.",
        )

    settings = getattr(request.app.state, "settings", None)
    if (
        settings is None
        or not settings.dispatch.audience
        or not settings.dispatch.service_account_email
    ):
        return error_response(
            status_code=status.HTTP_403_FORBIDDEN,
            code="permission_denied",
            message="Cloud Tasks dispatch configuration is incomplete.",
        )

    expected_audience = settings.dispatch.audience
    expected_caller = settings.dispatch.service_account_email
    token_verifier = getattr(request.app.state, "token_verifier", None)

    try:
        verify_google_oidc_claims(
            token.strip(),
            expected_audience=expected_audience,
            expected_caller=expected_caller,
            verifier=token_verifier,
        )
    except OidcAuthError as error:
        return error_response(
            status_code=error.status_code,
            code=error.code,
            message=error.message,
        )
    except Exception:
        return error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="authentication_required",
            message="Token verification failed.",
        )
    return None


@router.post(
    "/jobs:execute",
    operation_id="executeInternalJob",
    response_model=None,
)
async def execute_job(body: ExecuteJobTaskBody, request: Request) -> dict | JSONResponse:
    auth_error = _authenticate_cloud_tasks_caller(request)
    if auth_error is not None:
        return auth_error

    runner: RunJobService = request.app.state.job_runner
    try:
        job = await runner.run(
            job_id=body.job_id,
            org_id=body.org_id,
            project_id=body.project_id,
        )
    except RuntimeError as error:
        if "not found in its tenant scope" in str(error):
            return error_response(
                status_code=status.HTTP_404_NOT_FOUND,
                code="not_found",
                message="Job was not found in its tenant scope.",
            )
        raise

    return {
        "data": job_to_data(job),
        "meta": {"requestId": str(uuid6.uuid7())},
    }


@router.post(
    "/jobs:reconcile",
    operation_id="reconcileInternalJobs",
    response_model=None,
)
async def reconcile_jobs(request: Request) -> dict | JSONResponse:
    auth_error = _authenticate_cloud_tasks_caller(request)
    if auth_error is not None:
        return auth_error

    reconcile_service: ReconcileJobsService = request.app.state.reconcile_jobs_service
    result = await reconcile_service.reconcile()

    return {
        "data": {
            "dispatchedCount": result.dispatched_count,
            "recoveredCount": result.recovered_count,
            "failedCount": result.failed_count,
        },
        "meta": {"requestId": str(uuid6.uuid7())},
    }

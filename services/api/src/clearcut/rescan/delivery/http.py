"""Accountable start route for durable selective rescans.

Mounts ``POST .../script-versions/{versionId}:startSelectiveRescan``. The route
enforces CSRF and a required ``Idempotency-Key`` header, resolves the request
scope (authentication and organization/project membership) and requires an
accountable role (owner/admin/reviewer) before any repository access, and
delegates the governed decision to
:class:`~clearcut.rescan.application.start_rescan.StartSelectiveRescanService`.

Client-supplied ``itemIds`` are accepted syntactically but never used: the
durable payload is the server-derived after-version target only. Dispatch runs
only when the enqueue newly created the job, and only after the enqueue
transaction has committed, so a dispatch failure leaves a durable queued job for
reconciliation. Status is read through the shared operations ``getJob`` route.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Header,
    HTTPException,
    Path,
    Request,
    status,
)

from clearcut.identity.delivery.scope import get_request_scope
from clearcut.operations.delivery.http import job_to_data
from clearcut.organizations.delivery.http import verify_csrf_origin
from clearcut.rescan.application.start_rescan import (
    StartRescanAccepted,
    StartRescanRejection,
)

router = APIRouter(
    prefix="/api/v1/organizations/{orgId}/projects/{projectId}/script-versions/{versionId}",
    tags=["rescan"],
)

_ACCOUNTABLE_RESCAN_ROLES = frozenset({"owner", "admin", "reviewer"})


def _require_accountable_rescan_role(scope: object) -> None:
    if getattr(scope, "role", None) not in _ACCOUNTABLE_RESCAN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Starting a selective rescan requires an authorized accountable reviewer",
        )


@router.post(
    ":startSelectiveRescan",
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="startSelectiveRescan",
)
async def start_selective_rescan(
    request: Request,
    background_tasks: BackgroundTasks,
    org_id: Annotated[str, Path(alias="orgId")],
    project_id: Annotated[str, Path(alias="projectId")],
    version_id: Annotated[str, Path(alias="versionId")],
    _idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
) -> dict:
    verify_csrf_origin(request)
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)
    if scope.org_id is None or scope.project_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Selective rescan requires organization and project scope.",
        )
    _require_accountable_rescan_role(scope)

    try:
        parsed_version_id = UUID(version_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Script version not found",
        ) from None

    service = request.app.state.start_selective_rescan_service
    outcome = await service.start(
        org_id=scope.org_id,
        project_id=scope.project_id,
        actor_id=scope.user_id,
        after_version_id=parsed_version_id,
    )

    if not isinstance(outcome, StartRescanAccepted):
        raise _rejection_to_http(outcome.reason, outcome.message)

    result = outcome.enqueue
    if result.created:
        request.app.state.job_dispatcher.dispatch(background_tasks, result.job)
    return {
        "data": job_to_data(result.job),
        "meta": {"requestId": str(result.job.correlation_id)},
    }


def _rejection_to_http(reason: StartRescanRejection, message: str) -> HTTPException:
    if reason is StartRescanRejection.REVISION_PLAN_NOT_FOUND:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)
    if reason is StartRescanRejection.PROVIDER_DISABLED:
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=message)
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)


__all__ = ["router"]

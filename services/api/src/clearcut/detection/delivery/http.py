"""Scoped detection enqueue and post-commit local dispatch."""
from typing import Annotated
from uuid import UUID

import sqlalchemy as sa
from clearcut.database import session_scope
from clearcut.detection.ports.model_runtime import ModelRuntimePort
from clearcut.detection.runtime_provider import get_detection_runtime
from clearcut.identity.delivery.scope import get_request_scope
from clearcut.operations.delivery.http import job_to_data
from clearcut.operations.ports.job_repository import EnqueueJob
from clearcut.organizations.delivery.http import verify_csrf_origin
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Path,
    Request,
    status,
)

router = APIRouter(
    prefix="/api/v1/organizations/{orgId}/projects/{projectId}/script-versions/{versionId}",
    tags=["detection"],
)


@router.post(":detect", status_code=status.HTTP_202_ACCEPTED, operation_id="startDetection")
async def start_detection(
    request: Request,
    background_tasks: BackgroundTasks,
    org_id: Annotated[str, Path(alias="orgId")],
    project_id: Annotated[str, Path(alias="projectId")],
    version_id: Annotated[str, Path(alias="versionId")],
    _runtime: Annotated[ModelRuntimePort, Depends(get_detection_runtime)],
) -> dict:
    verify_csrf_origin(request)
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)
    if scope.org_id is None or scope.project_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Detection requires organization and project scope.",
        )
    scope_org_id = scope.org_id
    scope_project_id = scope.project_id

    try:
        parsed_version_id = UUID(version_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Script version not found",
        ) from None

    async with session_scope() as session:
        version = (
            await session.execute(
                sa.text(
                    "SELECT id FROM script_versions "
                    "WHERE id = :version_id AND org_id = :org_id "
                    "AND project_id = :project_id"
                ),
                {
                    "version_id": str(parsed_version_id),
                    "org_id": str(scope_org_id),
                    "project_id": str(scope_project_id),
                },
            )
        ).mappings().first()
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Script version not found in project",
        )

    result = await request.app.state.job_repository.enqueue(
        EnqueueJob(
            org_id=scope_org_id,
            project_id=scope_project_id,
            actor_id=scope.user_id,
            job_type="detection",
            idempotency_key=f"detection:{parsed_version_id}",
            payload={
                "schemaVersion": 1,
                "target": {
                    "type": "script_version",
                    "id": str(parsed_version_id),
                },
            },
            audit_action="detection.started",
            target_type="script_version",
            target_id=parsed_version_id,
        )
    )
    if result.created:
        request.app.state.job_dispatcher.dispatch(background_tasks, result.job)
    return {
        "data": job_to_data(result.job),
        "meta": {"requestId": str(result.job.correlation_id)},
    }

"""Scoped detection delivery: startDetection (contract operationId)."""
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
import uuid6
from fastapi import APIRouter, Depends, HTTPException, Request, status

from clearcut.database import session_scope
from clearcut.detection.ports.model_runtime import ModelRuntimePort
from clearcut.detection.runtime_provider import get_detection_runtime
from clearcut.identity.delivery.scope import get_request_scope
from clearcut.organizations.delivery.http import verify_csrf_origin

router = APIRouter(
    prefix="/api/v1/organizations/{org_id}/projects/{project_id}/script-versions/{version_id}",
    tags=["detection"],
)


@router.post(":detect", status_code=status.HTTP_202_ACCEPTED)
async def start_detection(
    org_id: str,
    project_id: str,
    version_id: str,
    request: Request,
    runtime: ModelRuntimePort = Depends(get_detection_runtime),
) -> dict:
    verify_csrf_origin(request)
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)

    try:
        parsed_version_id = UUID(version_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Script version not found")

    now = datetime.now(UTC)
    job_id = uuid6.uuid7()

    async with session_scope() as session:
        # Enforce the version belongs to this tenant/project — no cross-tenant detection.
        res = await session.execute(
            sa.text(
                "SELECT id FROM script_versions "
                "WHERE id = :vid AND org_id = :org AND project_id = :proj"
            ),
            {"vid": str(parsed_version_id), "org": str(scope.org_id), "proj": str(scope.project_id)},
        )
        if not res.mappings().first():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Script version not found in project",
            )

        # Persist a real job row + immutable audit event in one transaction.
        await session.execute(
            sa.text(
                "INSERT INTO jobs (id, org_id, project_id, job_type, target_id, status, progress, created_at) "
                "VALUES (:id, :org, :proj, 'detection', :target, 'queued', 0, :created)"
            ),
            {
                "id": str(job_id),
                "org": str(scope.org_id),
                "proj": str(scope.project_id),
                "target": str(parsed_version_id),
                "created": now.isoformat(),
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO audit_events "
                "(id, org_id, project_id, action, actor_id, target_id, target_type, details, created_at) "
                "VALUES (:id, :org, :proj, 'detection.started', :actor, :target, 'script_version', :details, :created)"
            ),
            {
                "id": str(uuid6.uuid7()),
                "org": str(scope.org_id),
                "proj": str(scope.project_id),
                "actor": str(scope.user_id),
                "target": str(parsed_version_id),
                "details": '{"job_type": "detection"}',
                "created": now.isoformat(),
            },
        )

    return {
        "data": {
            "jobId": str(job_id),
            "status": "queued",
            "jobType": "detection",
            "progress": 0,
            "createdAt": now.isoformat(),
        },
        "meta": {},
    }

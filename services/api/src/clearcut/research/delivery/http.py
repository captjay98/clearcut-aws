"""Scoped research delivery: startResearch (contract operationId)."""
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
import uuid6
from fastapi import APIRouter, Depends, HTTPException, Request, status

from clearcut.database import session_scope
from clearcut.identity.delivery.scope import get_request_scope
from clearcut.organizations.delivery.http import verify_csrf_origin
from clearcut.research.runtime_provider import ResearchRuntime, get_research_runtime

router = APIRouter(
    prefix="/api/v1/organizations/{org_id}/projects/{project_id}/clearance-items/{item_id}",
    tags=["research"],
)


@router.post(":research", status_code=status.HTTP_202_ACCEPTED)
async def start_research(
    org_id: str,
    project_id: str,
    item_id: str,
    request: Request,
    runtime: ResearchRuntime = Depends(get_research_runtime),
) -> dict:
    verify_csrf_origin(request)
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)

    try:
        parsed_item_id = UUID(item_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clearance item not found")

    now = datetime.now(UTC)
    job_id = uuid6.uuid7()

    async with session_scope() as session:
        # Enforce the item belongs to this tenant/project — no cross-tenant research.
        res = await session.execute(
            sa.text(
                "SELECT id FROM clearance_items "
                "WHERE id = :iid AND org_id = :org AND project_id = :proj"
            ),
            {"iid": str(parsed_item_id), "org": str(scope.org_id), "proj": str(scope.project_id)},
        )
        if not res.mappings().first():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Clearance item not found in project",
            )

        await session.execute(
            sa.text(
                "INSERT INTO jobs (id, org_id, project_id, job_type, target_id, status, progress, created_at) "
                "VALUES (:id, :org, :proj, 'research', :target, 'queued', 0, :created)"
            ),
            {
                "id": str(job_id),
                "org": str(scope.org_id),
                "proj": str(scope.project_id),
                "target": str(parsed_item_id),
                "created": now.isoformat(),
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO audit_events "
                "(id, org_id, project_id, action, actor_id, target_id, target_type, details, created_at) "
                "VALUES (:id, :org, :proj, 'research.started', :actor, :target, 'clearance_item', :details, :created)"
            ),
            {
                "id": str(uuid6.uuid7()),
                "org": str(scope.org_id),
                "proj": str(scope.project_id),
                "actor": str(scope.user_id),
                "target": str(parsed_item_id),
                "details": '{"job_type": "research"}',
                "created": now.isoformat(),
            },
        )

    return {
        "data": {
            "jobId": str(job_id),
            "status": "queued",
            "jobType": "research",
            "progress": 0,
            "createdAt": now.isoformat(),
        },
        "meta": {},
    }

"""Scoped research enqueue and post-commit local dispatch."""

from typing import Annotated
from uuid import UUID

import sqlalchemy as sa
from clearcut.database import session_scope
from clearcut.identity.delivery.scope import get_request_scope
from clearcut.operations.delivery.http import job_to_data
from clearcut.operations.ports.job_repository import EnqueueJob
from clearcut.organizations.delivery.http import verify_csrf_origin
from clearcut.research.runtime_provider import ResearchRuntime, get_research_runtime
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
    prefix="/api/v1/organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}",
    tags=["research"],
)


@router.post(":research", status_code=status.HTTP_202_ACCEPTED, operation_id="startResearch")
async def start_research(
    request: Request,
    background_tasks: BackgroundTasks,
    org_id: Annotated[str, Path(alias="orgId")],
    project_id: Annotated[str, Path(alias="projectId")],
    item_id: Annotated[str, Path(alias="itemId")],
    _runtime: Annotated[ResearchRuntime, Depends(get_research_runtime)],
) -> dict:
    verify_csrf_origin(request)
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)
    if scope.org_id is None or scope.project_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found in organization",
        )
    scope_org_id = scope.org_id
    scope_project_id = scope.project_id

    try:
        parsed_item_id = UUID(item_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clearance item not found",
        ) from None

    async with session_scope() as session:
        item = (
            (
                await session.execute(
                    sa.text(
                        "SELECT id FROM clearance_items "
                        "WHERE id = :item_id AND org_id = :org_id "
                        "AND project_id = :project_id"
                    ),
                    {
                        "item_id": str(parsed_item_id),
                        "org_id": str(scope_org_id),
                        "project_id": str(scope_project_id),
                    },
                )
            )
            .mappings()
            .first()
        )
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clearance item not found in project",
        )

    # A human starting research after failure requests a new run. Keep failed
    # jobs immutable; concurrent clicks for the same generation still deduplicate.
    base_key = f"research:{parsed_item_id}"
    async with session_scope() as session:
        failed_count = int(
            (
                await session.execute(
                    sa.text(
                        "SELECT count(*) FROM jobs WHERE org_id = :org AND project_id = :project "
                        "AND job_type = 'research' AND status = 'failed' "
                        "AND (idempotency_key = :base OR idempotency_key LIKE :generations)"
                    ),
                    {
                        "org": str(scope_org_id),
                        "project": str(scope_project_id),
                        "base": base_key,
                        "generations": base_key + ":after:%",
                    },
                )
            ).scalar_one()
        )
    research_key = f"{base_key}:after:{failed_count}" if failed_count else base_key

    result = await request.app.state.job_repository.enqueue(
        EnqueueJob(
            org_id=scope_org_id,
            project_id=scope_project_id,
            actor_id=scope.user_id,
            job_type="research",
            idempotency_key=research_key,
            payload={
                "schemaVersion": 1,
                "target": {
                    "type": "clearance_item",
                    "id": str(parsed_item_id),
                },
            },
            audit_action="research.started",
            target_type="clearance_item",
            target_id=parsed_item_id,
        )
    )
    if result.created:
        request.app.state.job_dispatcher.dispatch(background_tasks, result.job)
    return {
        "data": job_to_data(result.job),
        "meta": {"requestId": str(result.job.correlation_id)},
    }

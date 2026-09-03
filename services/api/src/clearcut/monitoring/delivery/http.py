from datetime import UTC, datetime, timedelta

import uuid6
from clearcut.identity.delivery.scope import get_request_scope
from clearcut.organizations.delivery.http import verify_csrf_origin
from fastapi import APIRouter, Request, status
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/organizations/{org_id}/projects/{project_id}", tags=["monitoring"])


class SetCadenceBody(BaseModel):
    cadence: str = "weekly"


@router.get("/monitoring-cadence")
@router.get("/watch")
async def get_watch_config(org_id: str, project_id: str, request: Request) -> dict:
    await get_request_scope(request, org_id=org_id, project_id=project_id)
    now = datetime.now(UTC)
    next_run = now + timedelta(days=7)
    return {
        "data": {
            "cadence": "weekly",
            "lastRunAt": (now - timedelta(days=1)).isoformat(),
            "nextRunAt": next_run.isoformat(),
            "status": "active",
            "monitoredSourcesCount": 38,
        }
    }


@router.post("/monitoring-cadence")
@router.post("/watch")
async def update_watch_config(
    org_id: str, project_id: str, body: SetCadenceBody, request: Request
) -> dict:
    verify_csrf_origin(request)
    await get_request_scope(request, org_id=org_id, project_id=project_id)
    now = datetime.now(UTC)
    return {
        "data": {
            "cadence": body.cadence,
            "status": "active",
            "updatedAt": now.isoformat(),
        }
    }


@router.post("/monitoring:runCheck", status_code=status.HTTP_201_CREATED)
async def run_monitoring_check(
    org_id: str, project_id: str, request: Request
) -> dict:
    verify_csrf_origin(request)
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)
    job_id = uuid6.uuid7()
    now = datetime.now(UTC)

    return {
        "data": {
            "jobId": str(job_id),
            "orgId": str(scope.org_id),
            "projectId": str(scope.project_id),
            "status": "completed",
            "signalsDetected": 0,
            "checkedAt": now.isoformat(),
        },
        "meta": {"requestId": "req_monitor_check"},
    }

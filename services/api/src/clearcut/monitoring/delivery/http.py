from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

prefix = "/api/v1/organizations/{org_id}/projects/{project_id}/watch"
router = APIRouter(prefix=prefix, tags=["monitoring"])


@router.get("")
async def get_watch_config(org_id: str, project_id: str) -> JSONResponse:
    config = {
        "cadence": "weekly",
        "last_run_at": "2026-08-30T12:00:00Z",
        "next_run_at": "2026-09-06T12:00:00Z",
        "status": "active",
        "monitored_sources_count": 38,
    }
    return JSONResponse(content={"data": config})


@router.post("")
async def update_watch_config(
    org_id: str, project_id: str, payload: dict[str, Any]
) -> JSONResponse:
    return JSONResponse(content={"data": payload, "status": "updated"})

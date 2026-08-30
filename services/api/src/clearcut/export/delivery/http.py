from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

prefix = "/api/v1/organizations/{org_id}/projects/{project_id}/report"
router = APIRouter(prefix=prefix, tags=["export"])


@router.get("")
async def get_report_status(org_id: str, project_id: str) -> JSONResponse:
    report = {
        "snapshot_id": "snap-001",
        "version_label": "v2 (Blue Revision)",
        "content_hash": "sha256:8f49a88cd72b9a714e8248c871587391",
        "status": "released",
        "is_released": True,
        "items_evaluated": 38,
    }
    return JSONResponse(content={"data": report})


@router.post("/release")
async def release_report(
    org_id: str, project_id: str, payload: dict[str, Any]
) -> JSONResponse:
    release = {
        "release_id": "rel-001",
        "snapshot_id": payload.get("snapshot_id", "snap-001"),
        "attestation": payload.get("attestation", ""),
        "status": "released",
    }
    return JSONResponse(content={"data": release}, status_code=201)

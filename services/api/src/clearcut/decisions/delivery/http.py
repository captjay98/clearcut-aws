from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(
    prefix="/api/v1/organizations/{org_id}/projects/{project_id}/items/{item_id}/decisions",
    tags=["decisions"]
)

@router.post("")
async def record_decision(
    org_id: str,
    project_id: str,
    item_id: str,
    payload: dict[str, Any]
) -> JSONResponse:
    decision = {
        "decision_id": "dec-001",
        "item_id": item_id,
        "action": payload.get("action", "accept_as_is"),
        "rationale": payload.get("rationale", ""),
        "status": "committed"
    }
    return JSONResponse(content={"data": decision}, status_code=201)

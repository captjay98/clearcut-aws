from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/v1/organizations/{org_id}/records", tags=["records"])

@router.get("")
async def list_audit_records(org_id: str) -> JSONResponse:
    records = [
        {
            "event_id": "aud-001",
            "action": "report_snapshot_released",
            "target_type": "report_release",
            "actor_id": "user-01",
            "created_at": "2026-08-30T15:58:30Z",
            "redacted_summary": "Released Pre-Clearance Dossier for v2 (Blue Revision)",
        },
        {
            "event_id": "aud-002",
            "action": "rewrite_proposal_approved",
            "target_type": "rewrite_proposal",
            "actor_id": "user-02",
            "created_at": "2026-08-30T15:20:10Z",
            "redacted_summary": "Approved Greeking substitution for item CC-104",
        }
    ]
    return JSONResponse(content={"data": records, "meta": {"total_count": len(records)}})

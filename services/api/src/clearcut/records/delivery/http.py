import json

import sqlalchemy as sa
from clearcut.database import session_scope
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/v1/organizations/{org_id}/records", tags=["records"])

@router.get("")
async def list_audit_records(org_id: str) -> JSONResponse:
    async with session_scope() as session:
        res = await session.execute(
            sa.text("""
                SELECT id, action, target_type, target_id, actor_id, details, created_at
                FROM audit_events
                ORDER BY created_at DESC
                LIMIT 50
            """)
        )
        rows = res.fetchall()
        records = []
        for r in rows:
            details = r.details if isinstance(r.details, dict) else json.loads(r.details) if r.details else {}
            records.append({
                "event_id": str(r.id),
                "action": r.action,
                "target_type": r.target_type,
                "target_id": str(r.target_id),
                "actor_id": str(r.actor_id),
                "created_at": r.created_at.isoformat() if hasattr(r.created_at, 'isoformat') else str(r.created_at),
                "details": details,
                "redacted_summary": f"{r.action} on {r.target_type} ({str(r.target_id)[:8]})",
            })
    return JSONResponse(content={"data": records, "meta": {"total_count": len(records)}})

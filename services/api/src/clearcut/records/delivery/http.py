import json
import sqlalchemy as sa
from fastapi import APIRouter, Request

from clearcut.database import session_scope
from clearcut.identity.delivery.scope import get_request_scope

router = APIRouter(prefix="/api/v1/organizations/{org_id}", tags=["records", "audit"])


@router.get("/audit-events")
@router.get("/records")
async def list_audit_events(org_id: str, request: Request) -> dict:
    scope = await get_request_scope(request, org_id=org_id)
    async with session_scope() as session:
        res = await session.execute(
            sa.text("""
                SELECT id, action, target_type, target_id, actor_id, details, created_at
                FROM audit_events
                WHERE org_id = :org_id
                ORDER BY created_at DESC
                LIMIT 100
            """),
            {"org_id": str(scope.org_id)},
        )
        rows = res.fetchall()
        records = []
        for r in rows:
            details = r.details if isinstance(r.details, dict) else json.loads(r.details) if r.details else {}
            records.append({
                "eventId": str(r.id),
                "action": r.action,
                "targetType": r.target_type,
                "targetId": str(r.target_id),
                "actorId": str(r.actor_id),
                "createdAt": r.created_at.isoformat() if hasattr(r.created_at, "isoformat") else str(r.created_at),
                "details": details,
                "redactedSummary": f"{r.action} on {r.target_type} ({str(r.target_id)[:8]})",
            })
    return {"data": records, "meta": {"count": len(records)}}

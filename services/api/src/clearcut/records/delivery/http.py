"""Canonical Records boundaries; authoritative read models are implemented in Task 11."""
import json
from typing import Annotated, Literal

import sqlalchemy as sa
from clearcut.database import session_scope
from clearcut.delivery_errors import capability_unavailable
from clearcut.identity.delivery.scope import get_request_scope
from fastapi import APIRouter, Path, Query, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/v1/organizations/{orgId}", tags=["records", "audit"])
_RECORDS_UNAVAILABLE = (
    "Authoritative Records are not available until ledger read models are configured."
)
RecordView = Literal["activity", "runsAndTools", "evaluations", "policies", "operations"]


async def _authorize(request: Request, org_id: str) -> None:
    await get_request_scope(request, org_id=org_id)


@router.get("/records", operation_id="listRecords")
async def list_records(
    request: Request,
    org_id: Annotated[str, Path(alias="orgId")],
    view: RecordView,
    cursor: str | None = None,
    project_id: Annotated[str | None, Query(alias="projectId")] = None,
) -> JSONResponse:
    await _authorize(request, org_id)
    return capability_unavailable(_RECORDS_UNAVAILABLE)


@router.get("/records/{recordId}", operation_id="getRecord")
async def get_record(
    request: Request,
    org_id: Annotated[str, Path(alias="orgId")],
    record_id: Annotated[str, Path(alias="recordId")],
) -> JSONResponse:
    await _authorize(request, org_id)
    return capability_unavailable(_RECORDS_UNAVAILABLE)


@router.get("/provider-attempts/{attemptId}", operation_id="getProviderAttempt")
async def get_provider_attempt(
    request: Request,
    org_id: Annotated[str, Path(alias="orgId")],
    attempt_id: Annotated[str, Path(alias="attemptId")],
) -> JSONResponse:
    await _authorize(request, org_id)
    return capability_unavailable(_RECORDS_UNAVAILABLE)


@router.get("/audit-events", include_in_schema=False)
async def list_legacy_audit_events(
    request: Request,
    org_id: Annotated[str, Path(alias="orgId")],
) -> dict:
    """Temporary compatibility projection; canonical Records never reads this table."""
    scope = await get_request_scope(request, org_id=org_id)
    async with session_scope() as session:
        result = await session.execute(
            sa.text("""
                SELECT id, action, target_type, target_id, actor_id, details, created_at
                FROM audit_events
                WHERE org_id = :org_id
                ORDER BY created_at DESC
                LIMIT 100
            """),
            {"org_id": str(scope.org_id)},
        )
        records = []
        for row in result.fetchall():
            details = (
                row.details
                if isinstance(row.details, dict)
                else json.loads(row.details)
                if row.details
                else {}
            )
            records.append(
                {
                    "eventId": str(row.id),
                    "action": row.action,
                    "targetType": row.target_type,
                    "targetId": str(row.target_id),
                    "actorId": str(row.actor_id),
                    "createdAt": (
                        row.created_at.isoformat()
                        if hasattr(row.created_at, "isoformat")
                        else str(row.created_at)
                    ),
                    "details": details,
                    "redactedSummary": (
                        f"{row.action} on {row.target_type} ({str(row.target_id)[:8]})"
                    ),
                }
            )
    return {"data": records, "meta": {"count": len(records)}}

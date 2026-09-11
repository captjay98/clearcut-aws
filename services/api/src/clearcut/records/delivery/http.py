"""Canonical Records boundaries backed by the authoritative audit ledger."""
from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal
from uuid import UUID

import sqlalchemy as sa
import uuid6
from clearcut.database import session_scope
from clearcut.delivery_errors import error_response
from clearcut.identity.delivery.scope import get_request_scope
from fastapi import APIRouter, Path, Query, Request, status
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/v1/organizations/{orgId}", tags=["records", "audit"])
RecordView = Literal["activity", "runsAndTools", "evaluations", "policies", "operations"]

# Activity is the unfiltered ledger. Other views narrow by action prefix so the
# surface stays a projection of the same immutable events, not a second source.
_VIEW_ACTION_PREFIX: dict[str, tuple[str, ...]] = {
    "activity": (),
    "runsAndTools": ("detection.", "research.", "rescan.", "parse.", "import."),
    "evaluations": ("evaluation.", "judge.", "learning."),
    "policies": ("policy.", "configuration.", "protected."),
    "operations": ("report.", "release.", "job.", "monitoring."),
}

_LIST_RECORDS = sa.text(
    """
    SELECT e.id, e.org_id, e.project_id, e.action, e.actor_id, e.target_id,
           e.target_type, e.payload_redacted, e.occurred_at, e.correlation_id,
           u.email AS actor_email
    FROM authoritative_audit_events e
    LEFT JOIN users u ON u.id = e.actor_id
    WHERE CAST(e.org_id AS text) = :org_id
      AND (:project_id = '' OR CAST(e.project_id AS text) = :project_id)
    ORDER BY e.occurred_at DESC, e.id DESC
    LIMIT 200
    """
)

_GET_RECORD = sa.text(
    """
    SELECT e.id, e.org_id, e.project_id, e.action, e.actor_id, e.target_id,
           e.target_type, e.payload_redacted, e.occurred_at, e.correlation_id,
           u.email AS actor_email
    FROM authoritative_audit_events e
    LEFT JOIN users u ON u.id = e.actor_id
    WHERE CAST(e.id AS text) = :record_id
      AND CAST(e.org_id AS text) = :org_id
    """
)


async def _authorize(request: Request, org_id: str) -> str:
    scope = await get_request_scope(request, org_id=org_id)
    assert scope.org_id is not None
    return str(scope.org_id)


def _receipt_hash(event_id: str, action: str, occurred_at: object) -> str:
    stamp = occurred_at.isoformat() if hasattr(occurred_at, "isoformat") else str(occurred_at)
    material = f"{event_id}|{action}|{stamp}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _serialize(row: object) -> dict:
    mapping = row._mapping if hasattr(row, "_mapping") else row  # type: ignore[union-attr]
    payload = mapping["payload_redacted"]
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {"raw": payload}
    elif payload is None:
        payload = {}
    occurred = mapping["occurred_at"]
    project_id = mapping["project_id"]
    return {
        "recordId": str(mapping["id"]),
        "orgId": str(mapping["org_id"]),
        "projectId": str(project_id) if project_id is not None else None,
        "eventType": mapping["action"],
        "actorId": str(mapping["actor_id"]),
        "actorEmail": mapping["actor_email"],
        "payload": payload,
        "receiptHash": _receipt_hash(str(mapping["id"]), mapping["action"], occurred),
        "timestamp": occurred.isoformat() if hasattr(occurred, "isoformat") else str(occurred),
    }


@router.get("/records", operation_id="listRecords")
async def list_records(
    request: Request,
    org_id: Annotated[str, Path(alias="orgId")],
    view: RecordView,
    cursor: str | None = None,
    project_id: Annotated[str | None, Query(alias="projectId")] = None,
) -> JSONResponse:
    org_uuid = await _authorize(request, org_id)
    prefixes = _VIEW_ACTION_PREFIX.get(view, ())
    async with session_scope() as session:
        result = await session.execute(
            _LIST_RECORDS,
            {
                "org_id": org_uuid,
                "project_id": project_id or "",
            },
        )
        rows = result.fetchall()
    records = []
    for row in rows:
        serialized = _serialize(row)
        if prefixes and not serialized["eventType"].startswith(prefixes):
            continue
        records.append(serialized)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "data": records,
            "meta": {"requestId": str(uuid6.uuid7()), "totalCount": len(records)},
        },
    )


@router.get("/records/{recordId}", operation_id="getRecord")
async def get_record(
    request: Request,
    org_id: Annotated[str, Path(alias="orgId")],
    record_id: Annotated[str, Path(alias="recordId")],
) -> JSONResponse:
    org_uuid = await _authorize(request, org_id)
    try:
        UUID(record_id)
    except ValueError:
        return error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="not_found",
            message="Record not found",
        )
    async with session_scope() as session:
        row = (
            await session.execute(
                _GET_RECORD,
                {"record_id": record_id, "org_id": org_uuid},
            )
        ).first()
    if row is None:
        return error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="not_found",
            message="Record not found",
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "data": _serialize(row),
            "meta": {"requestId": str(uuid6.uuid7())},
        },
    )


@router.get("/provider-attempts/{attemptId}", operation_id="getProviderAttempt")
async def get_provider_attempt(
    request: Request,
    org_id: Annotated[str, Path(alias="orgId")],
    attempt_id: Annotated[str, Path(alias="attemptId")],
) -> JSONResponse:
    """Provider attempt provenance is not part of the Records ledger yet."""
    await _authorize(request, org_id)
    return error_response(
        status_code=status.HTTP_404_NOT_FOUND,
        code="not_found",
        message="Provider attempt not found",
    )


@router.get("/audit-events", include_in_schema=False)
async def list_legacy_audit_events(
    request: Request,
    org_id: Annotated[str, Path(alias="orgId")],
) -> dict:
    """Temporary compatibility projection over the authoritative ledger."""
    org_uuid = await _authorize(request, org_id)
    async with session_scope() as session:
        result = await session.execute(
            sa.text(
                """
                SELECT id, action, target_type, target_id, actor_id,
                       payload_redacted, occurred_at
                FROM authoritative_audit_events
                WHERE CAST(org_id AS text) = :org_id
                ORDER BY occurred_at DESC
                LIMIT 100
                """
            ),
            {"org_id": org_uuid},
        )
        records = []
        for row in result.fetchall():
            payload = row.payload_redacted
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except json.JSONDecodeError:
                    payload = {"raw": payload}
            elif payload is None:
                payload = {}
            records.append(
                {
                    "eventId": str(row.id),
                    "action": row.action,
                    "targetType": row.target_type,
                    "targetId": str(row.target_id),
                    "actorId": str(row.actor_id),
                    "createdAt": (
                        row.occurred_at.isoformat()
                        if hasattr(row.occurred_at, "isoformat")
                        else str(row.occurred_at)
                    ),
                    "details": payload,
                    "redactedSummary": (
                        f"{row.action} on {row.target_type} ({str(row.target_id)[:8]})"
                    ),
                }
            )
    return {"data": records, "meta": {"count": len(records)}}

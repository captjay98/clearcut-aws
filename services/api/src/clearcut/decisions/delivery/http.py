import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID
import uuid6
import sqlalchemy as sa
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from clearcut.database import session_scope
from clearcut.identity.delivery.scope import get_request_scope
from clearcut.organizations.delivery.http import verify_csrf_origin

router = APIRouter(
    prefix="/api/v1/organizations/{org_id}/projects/{project_id}/items/{item_id}/decisions",
    tags=["decisions"],
)


class RecordDecisionBody(BaseModel):
    decision: str = Field(min_length=1)
    rationale: str = Field(min_length=1)


@router.post("", status_code=status.HTTP_201_CREATED)
async def record_decision(
    org_id: str,
    project_id: str,
    item_id: str,
    body: RecordDecisionBody,
    request: Request,
) -> dict:
    verify_csrf_origin(request)
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)
    try:
        parsed_item_id = UUID(item_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    dec_id = uuid6.uuid7()
    audit_id = uuid6.uuid7()
    now = datetime.now(UTC)

    async with session_scope() as session:
        # Check item existence in org and project
        item_res = await session.execute(
            sa.text("""
                SELECT id FROM clearance_items
                WHERE id = :id AND org_id = :org_id AND project_id = :project_id
            """),
            {
                "id": str(parsed_item_id),
                "org_id": str(scope.org_id),
                "project_id": str(scope.project_id),
            },
        )
        if not item_res.mappings().first():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clearance item not found")

        # Insert decision
        await session.execute(
            sa.text("""
                INSERT INTO evidence_decisions (
                    id, org_id, project_id, item_id, actor_id, decision_type, rationale, created_at
                ) VALUES (
                    :id, :org_id, :project_id, :item_id, :actor_id, :decision_type, :rationale, :created_at
                )
            """),
            {
                "id": str(dec_id),
                "org_id": str(scope.org_id),
                "project_id": str(scope.project_id),
                "item_id": str(parsed_item_id),
                "actor_id": str(scope.user_id),
                "decision_type": body.decision,
                "rationale": body.rationale,
                "created_at": now,
            },
        )

        # Update item workflow status
        await session.execute(
            sa.text("""
                UPDATE clearance_items
                SET status = 'decided', workflow_status = 'closed'
                WHERE id = :id AND org_id = :org_id AND project_id = :project_id
            """),
            {
                "id": str(parsed_item_id),
                "org_id": str(scope.org_id),
                "project_id": str(scope.project_id),
            },
        )

        # Record immutable audit event in the same transaction
        await session.execute(
            sa.text("""
                INSERT INTO audit_events (
                    id, org_id, project_id, action, actor_id, target_id, target_type, details, created_at
                ) VALUES (
                    :id, :org_id, :project_id, 'evidence.decision_recorded', :actor_id, :target_id, 'clearance_item', :details, :created_at
                )
            """),
            {
                "id": str(audit_id),
                "org_id": str(scope.org_id),
                "project_id": str(scope.project_id),
                "actor_id": str(scope.user_id),
                "target_id": str(parsed_item_id),
                "details": json.dumps({"decision": body.decision, "rationale": body.rationale}),
                "created_at": now,
            },
        )

    return {
        "data": {
            "id": str(dec_id),
            "itemId": str(parsed_item_id),
            "orgId": str(scope.org_id),
            "projectId": str(scope.project_id),
            "actorId": str(scope.user_id),
            "decision": body.decision,
            "rationale": body.rationale,
            "status": "committed",
            "createdAt": now.isoformat(),
        },
        "meta": {"requestId": "req_record_decision"},
    }

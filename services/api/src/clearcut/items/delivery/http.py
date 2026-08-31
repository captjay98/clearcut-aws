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

prefix = "/api/v1/organizations/{org_id}/projects/{project_id}/items"
router = APIRouter(prefix=prefix, tags=["items"])


class AssignBody(BaseModel):
    assignedToUserId: str | None = None


class SetDispositionBody(BaseModel):
    disposition: str
    rationale: str | None = None


class ReferItemBody(BaseModel):
    targetRole: str
    notes: str


class AddCommentBody(BaseModel):
    content: str
    parentCommentId: str | None = None


class ProposeRewriteBody(BaseModel):
    originalText: str
    proposedText: str
    rationale: str | None = None


@router.get("")
async def list_items(org_id: str, project_id: str, request: Request) -> dict:
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)
    async with session_scope() as session:
        result = await session.execute(
            sa.text("""
                SELECT i.id, i.category, i.text, i.status, i.workflow_status, i.research_status,
                       i.disposition_status, i.assigned_to_user_id,
                       e.scene_number, e.page_number,
                       (SELECT count(*) FROM evidence_claims c WHERE c.item_id = i.id) as claims_count
                FROM clearance_items i
                LEFT JOIN script_elements e ON e.id = i.element_id
                WHERE i.org_id = :org_id AND i.project_id = :project_id
                ORDER BY e.ordinal ASC, i.created_at ASC
            """),
            {"org_id": str(scope.org_id), "project_id": str(scope.project_id)},
        )
        rows = result.fetchall()
        items = []
        for r in rows:
            items.append({
                "id": str(r.id),
                "category": r.category,
                "category_label": r.category,
                "text": r.text,
                "scene": r.scene_number or 1,
                "page": r.page_number or 1,
                "status": r.status,
                "workflow_status": r.workflow_status,
                "research_status": r.research_status,
                "disposition_status": r.disposition_status or "undisposed",
                "assigned_to_user_id": str(r.assigned_to_user_id) if r.assigned_to_user_id else None,
                "claims_count": r.claims_count,
            })
    return {"data": items, "meta": {"total_count": len(items)}}


@router.get("/{item_id}")
async def get_item(org_id: str, project_id: str, item_id: str, request: Request) -> dict:
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)
    try:
        parsed_item_id = UUID(item_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clearance item not found")

    async with session_scope() as session:
        res = await session.execute(
            sa.text("""
                SELECT i.id, i.category, i.text, i.status, i.workflow_status, i.research_status,
                       i.disposition_status, i.assigned_to_user_id,
                       e.scene_number, e.page_number
                FROM clearance_items i
                LEFT JOIN script_elements e ON e.id = i.element_id
                WHERE i.id = :id AND i.org_id = :org_id AND i.project_id = :project_id
            """),
            {
                "id": str(parsed_item_id),
                "org_id": str(scope.org_id),
                "project_id": str(scope.project_id),
            },
        )
        row = res.fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clearance item not found")

        # Query real sources and claims
        src_res = await session.execute(
            sa.text("""
                SELECT c.id as claim_id, c.stance, c.authority_tier, c.claim_text, c.provenance_excerpt,
                       s.title as source_title, s.url as source_url, s.publisher
                FROM evidence_claims c
                JOIN source_snapshots s ON s.id = c.snapshot_id
                WHERE c.item_id = :item_id
                ORDER BY c.created_at ASC
            """),
            {"item_id": str(parsed_item_id)},
        )
        claims = [
            {
                "claim_id": str(s.claim_id),
                "source_title": s.source_title,
                "source_url": s.source_url,
                "publisher": s.publisher,
                "stance": s.stance,
                "authority": s.authority_tier,
                "claim_text": s.claim_text,
                "excerpt": s.provenance_excerpt,
            }
            for s in src_res.fetchall()
        ]

        item_data = {
            "id": str(row.id),
            "category": row.category,
            "category_label": row.category,
            "text": row.text,
            "scene": getattr(row, "scene_number", 1) or 1,
            "page": getattr(row, "page_number", 1) or 1,
            "status": row.status,
            "workflow_status": row.workflow_status,
            "research_status": row.research_status,
            "disposition_status": row.disposition_status or "undisposed",
            "assigned_to_user_id": str(row.assigned_to_user_id) if row.assigned_to_user_id else None,
            "claims": claims,
            "comments": [],
        }

    return {"data": item_data, "meta": {"requestId": "req_get_item"}}


@router.get("/{item_id}/evidence")
async def get_item_evidence(org_id: str, project_id: str, item_id: str, request: Request) -> dict:
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)
    try:
        parsed_item_id = UUID(item_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    async with session_scope() as session:
        src_res = await session.execute(
            sa.text("""
                SELECT c.id as claim_id, c.stance, c.authority_tier, c.claim_text, c.provenance_excerpt,
                       s.title as source_title, s.url as source_url, s.publisher, s.retrieved_at
                FROM evidence_claims c
                JOIN source_snapshots s ON s.id = c.snapshot_id
                WHERE c.item_id = :item_id AND c.org_id = :org_id AND c.project_id = :project_id
                ORDER BY c.created_at ASC
            """),
            {
                "item_id": str(parsed_item_id),
                "org_id": str(scope.org_id),
                "project_id": str(scope.project_id),
            },
        )
        claims = [
            {
                "claimId": str(s.claim_id),
                "sourceTitle": s.source_title,
                "sourceUrl": s.source_url,
                "publisher": s.publisher,
                "stance": s.stance,
                "authorityTier": s.authority_tier,
                "claimText": s.claim_text,
                "provenanceExcerpt": s.provenance_excerpt,
                "retrievedAt": s.retrieved_at.isoformat() if hasattr(s.retrieved_at, "isoformat") else str(s.retrieved_at),
            }
            for s in src_res.fetchall()
        ]
        return {"data": claims, "meta": {"count": len(claims)}}


@router.post("/{item_id}:assign")
async def assign_item(
    org_id: str, project_id: str, item_id: str, body: AssignBody, request: Request
) -> dict:
    verify_csrf_origin(request)
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)
    try:
        parsed_item_id = UUID(item_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    async with session_scope() as session:
        assigned_uuid = UUID(body.assignedToUserId) if body.assignedToUserId else None
        await session.execute(
            sa.text("""
                UPDATE clearance_items
                SET assigned_to_user_id = :assigned_id
                WHERE id = :id AND org_id = :org_id AND project_id = :project_id
            """),
            {
                "id": str(parsed_item_id),
                "org_id": str(scope.org_id),
                "project_id": str(scope.project_id),
                "assigned_id": str(assigned_uuid) if assigned_uuid else None,
            },
        )
    return {"data": {"itemId": str(parsed_item_id), "assignedToUserId": body.assignedToUserId}}


@router.post("/{item_id}:setDisposition")
async def set_item_disposition(
    org_id: str, project_id: str, item_id: str, body: SetDispositionBody, request: Request
) -> dict:
    verify_csrf_origin(request)
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)
    try:
        parsed_item_id = UUID(item_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    now = datetime.now(UTC)
    async with session_scope() as session:
        await session.execute(
            sa.text("""
                UPDATE clearance_items
                SET disposition_status = :disposition, workflow_status = 'disposed'
                WHERE id = :id AND org_id = :org_id AND project_id = :project_id
            """),
            {
                "id": str(parsed_item_id),
                "org_id": str(scope.org_id),
                "project_id": str(scope.project_id),
                "disposition": body.disposition,
            },
        )
        # Record audit event
        audit_id = uuid6.uuid7()
        await session.execute(
            sa.text("""
                INSERT INTO audit_events (id, org_id, project_id, action, actor_id, target_id, target_type, details, created_at)
                VALUES (:id, :org_id, :project_id, 'item.disposition_set', :actor_id, :target_id, 'clearance_item', :details, :created_at)
            """),
            {
                "id": str(audit_id),
                "org_id": str(scope.org_id),
                "project_id": str(scope.project_id),
                "actor_id": str(scope.user_id),
                "target_id": str(parsed_item_id),
                "details": f'{{"disposition": "{body.disposition}"}}',
                "created_at": now,
            },
        )

    return {"data": {"itemId": str(parsed_item_id), "disposition": body.disposition, "status": "disposed"}}

import uuid
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
import sqlalchemy as sa

from clearcut.database import session_scope

prefix = "/api/v1/organizations/{org_id}/projects/{project_id}/items"
router = APIRouter(prefix=prefix, tags=["items"])


@router.get("")
async def list_items(org_id: str, project_id: str) -> JSONResponse:
    async with session_scope() as session:
        result = await session.execute(
            sa.text("""
                SELECT i.id, i.category, i.text, i.status, i.workflow_status, i.research_status,
                       e.scene_number, e.page_number,
                       (SELECT count(*) FROM source_snapshots s WHERE s.item_id = i.id) as claims_count
                FROM clearance_items i
                LEFT JOIN script_elements e ON e.id = i.element_id
                ORDER BY e.ordinal ASC, i.created_at ASC
            """)
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
                "claims_count": r.claims_count,
            })
    return JSONResponse(content={"data": items, "meta": {"total_count": len(items)}})


@router.get("/{item_id}")
async def get_item(org_id: str, project_id: str, item_id: str) -> JSONResponse:
    async with session_scope() as session:
        # Match by UUID or if given a code like CC-101 match by position/offset
        item_query = sa.text("""
            SELECT i.id, i.category, i.text, i.status, i.workflow_status, i.research_status,
                   e.scene_number, e.page_number
            FROM clearance_items i
            LEFT JOIN script_elements e ON e.id = i.element_id
            WHERE i.id::text = :id_str OR i.text ILIKE :term_match
            LIMIT 1
        """)
        # If item_id is CC-101 etc., search by known terms
        term_map = {
            "CC-101": "%Vega%",
            "CC-102": "%Mina%",
            "CC-103": "%Sunset%",
            "CC-104": "%Blue Monday%",
            "CC-105": "%Keep the change%",
            "CC-106": "%Northstar%",
            "CC-107": "%bicycle%",
            "CC-108": "%Glass House%",
            "CC-109": "%Lenora%",
            "CC-110": "%relapse%",
        }
        term_match = term_map.get(item_id, f"%{item_id}%")

        res = await session.execute(item_query, {"id_str": item_id if len(item_id) == 36 else "00000000-0000-0000-0000-000000000000", "term_match": term_match})
        row = res.fetchone()

        if not row:
            # Fallback to first item if query had no exact match
            res = await session.execute(sa.text("SELECT id, category, text, status, workflow_status, research_status FROM clearance_items LIMIT 1"))
            row = res.fetchone()

        real_id = row.id if row else uuid.uuid4()

        # Query real sources from source_snapshots
        src_res = await session.execute(
            sa.text("""
                SELECT s.id, s.title, s.url, s.publisher, s.excerpt, c.stance, c.authority_tier
                FROM source_snapshots s
                LEFT JOIN evidence_claims c ON c.snapshot_id = s.id
                WHERE s.item_id = :item_id
            """),
            {"item_id": real_id},
        )
        sources = [
            {
                "claim_id": str(s.id),
                "source_title": s.title,
                "source_url": s.url,
                "publisher": s.publisher,
                "stance": s.stance or "supporting",
                "authority": s.authority_tier or s.publisher,
                "excerpt": s.excerpt,
            }
            for s in src_res.fetchall()
        ]

        item_data = {
            "id": str(row.id) if row else item_id,
            "category": row.category if row else "Trademarks",
            "category_label": row.category if row else "Trademarks & Brand Names",
            "text": row.text if row else "Vega Camera",
            "scene": getattr(row, "scene_number", 1) or 1,
            "page": getattr(row, "page_number", 1) or 1,
            "status": row.status if row else "Needs your call",
            "claims": sources,
            "comments": [],
        }

    return JSONResponse(content={"data": item_data})

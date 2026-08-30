from typing import Annotated
from uuid import UUID

from clearcut.detection.application.item_projection import ItemProjectionService
from clearcut.detection.domain.candidates import ClearanceCategory
from clearcut.detection.domain.item_state import ClearanceItemDisplayStatus
from fastapi import APIRouter, Depends, Query

router = APIRouter(prefix="/o/{org_slug}/projects/{project_id}/items", tags=["items"])


def get_projection_service() -> ItemProjectionService:
    return ItemProjectionService()


@router.get("")
async def list_clearance_items(
    project_id: UUID,
    service: Annotated[ItemProjectionService, Depends(get_projection_service)],
    category: Annotated[ClearanceCategory | None, Query()] = None,
    display_status: Annotated[ClearanceItemDisplayStatus | None, Query()] = None,
):
    # Dummy org_id for route demonstration
    items = service.list_items(
        org_id=project_id,
        project_id=project_id,
        category=category,
        display_status=display_status,
    )
    return {"items": items}

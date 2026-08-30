import uuid6
from clearcut.detection.application.item_projection import ItemProjectionService
from clearcut.detection.domain.candidates import ClearanceCategory
from clearcut.detection.domain.item_state import (
    ClearanceItemDisplayStatus,
    DispositionStatus,
    ItemProjection,
    ResearchStatus,
    WorkflowStatus,
)


def test_item_list_filters_by_category_and_display_status():
    service = ItemProjectionService()
    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    script_id = uuid6.uuid7()
    version_id = uuid6.uuid7()

    item1 = ItemProjection(
        item_id=uuid6.uuid7(),
        org_id=org_id,
        project_id=project_id,
        script_id=script_id,
        version_id=version_id,
        element_id=uuid6.uuid7(),
        category=ClearanceCategory.PRODUCTS_AND_TRADEMARKS,
        text="Coca-Cola",
        scene_number=1,
        research_status=ResearchStatus.COMPLETED,
        workflow_status=WorkflowStatus.OPEN,
        disposition_status=DispositionStatus.UNDISPOSED,
        display_status=ClearanceItemDisplayStatus.NEEDS_REVIEW,
        assigned_to_user_id=None,
        flags_count=1,
        claims_count=2,
        conflicts_count=0,
    )
    item2 = ItemProjection(
        item_id=uuid6.uuid7(),
        org_id=org_id,
        project_id=project_id,
        script_id=script_id,
        version_id=version_id,
        element_id=uuid6.uuid7(),
        category=ClearanceCategory.REAL_PERSONS_LIVING,
        text="Tom Cruise",
        scene_number=2,
        research_status=ResearchStatus.COMPLETED,
        workflow_status=WorkflowStatus.RESOLVED,
        disposition_status=DispositionStatus.APPROVED_AS_IS,
        display_status=ClearanceItemDisplayStatus.CLEARED,
        assigned_to_user_id=None,
        flags_count=0,
        claims_count=3,
        conflicts_count=0,
    )
    service.register_item(item1)
    service.register_item(item2)

    # Filter by category
    prod_items = service.list_items(
        org_id,
        project_id,
        category=ClearanceCategory.PRODUCTS_AND_TRADEMARKS,
    )
    assert len(prod_items) == 1
    assert prod_items[0].text == "Coca-Cola"

    # Filter by display_status
    cleared_items = service.list_items(
        org_id,
        project_id,
        display_status=ClearanceItemDisplayStatus.CLEARED,
    )
    assert len(cleared_items) == 1
    assert cleared_items[0].text == "Tom Cruise"

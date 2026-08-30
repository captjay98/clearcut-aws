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


def test_project_summary_counts_match_item_list():
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
    service.register_item(item1)

    summary = service.get_project_summary(org_id, project_id)
    assert summary.total_items == 1
    assert summary.needs_review_count == 1

    items = service.list_items(org_id, project_id)
    assert len(items) == summary.total_items

import pytest
import uuid6
from clearcut.detection.domain.candidates import ClearanceCategory
from clearcut.detection.domain.item_state import (
    ClearanceItemDisplayStatus,
    DispositionStatus,
    ItemProjection,
    ResearchStatus,
    WorkflowStatus,
)
from clearcut.research.application.selective_rescan import SelectiveRescanService
from clearcut.scripts.domain.diff import ChangeClassification, ElementDiff, ScriptDiff


@pytest.mark.asyncio
async def test_selective_rescan_calls_only_affected_items():
    service = SelectiveRescanService()
    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    v1_id = uuid6.uuid7()
    v2_id = uuid6.uuid7()

    affected_elem_id = uuid6.uuid7()
    unaffected_elem_id = uuid6.uuid7()

    diff = ScriptDiff(
        before_version_id=v1_id,
        after_version_id=v2_id,
        element_diffs=[
            ElementDiff(
                affected_elem_id, "Old Text", "New Text", ChangeClassification.MODIFIED
            ),
            ElementDiff(
                unaffected_elem_id, "Unchanged", "Unchanged", ChangeClassification.UNCHANGED
            ),
        ],
        affected_element_ids={affected_elem_id},
        unaffected_element_ids={unaffected_elem_id},
    )

    item_affected = ItemProjection(
        item_id=uuid6.uuid7(),
        org_id=org_id,
        project_id=project_id,
        script_id=uuid6.uuid7(),
        version_id=v1_id,
        element_id=affected_elem_id,
        category=ClearanceCategory.PRODUCTS_AND_TRADEMARKS,
        text="Old Text",
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

    item_unaffected = ItemProjection(
        item_id=uuid6.uuid7(),
        org_id=org_id,
        project_id=project_id,
        script_id=uuid6.uuid7(),
        version_id=v1_id,
        element_id=unaffected_elem_id,
        category=ClearanceCategory.REAL_PERSONS_LIVING,
        text="Unchanged",
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

    result = await service.execute_rescan(
        org_id=org_id,
        project_id=project_id,
        before_version_id=v1_id,
        after_version_id=v2_id,
        diff=diff,
        items=[item_affected, item_unaffected],
    )

    assert result.affected_items_count == 1
    assert result.saved_calls_count == 1
    assert item_affected.item_id in result.rescanned_item_ids
    assert item_unaffected.item_id not in result.rescanned_item_ids

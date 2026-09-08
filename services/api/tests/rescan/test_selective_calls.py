from uuid import UUID

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
from clearcut.scripts.domain.diff import (
    MATCHING_ALGORITHM_VERSION,
    ChangeClassification,
    ElementDiff,
    LineageConfidence,
    ScriptDiff,
)


def _item(
    *,
    org_id,
    project_id,
    version_id,
    element_id,
    text: str,
) -> ItemProjection:
    return ItemProjection(
        item_id=uuid6.uuid7(),
        org_id=org_id,
        project_id=project_id,
        script_id=uuid6.uuid7(),
        version_id=version_id,
        element_id=element_id,
        category=ClearanceCategory.PRODUCTS_AND_TRADEMARKS,
        text=text,
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


def _diff_with_distinct_lineage_ids() -> tuple[ScriptDiff, dict[str, UUID]]:
    ids = {
        "modified_before": uuid6.uuid7(),
        "modified_after": uuid6.uuid7(),
        "unchanged_before": uuid6.uuid7(),
        "unchanged_after": uuid6.uuid7(),
        "removed_before": uuid6.uuid7(),
    }
    before_version_id = uuid6.uuid7()
    after_version_id = uuid6.uuid7()
    diff = ScriptDiff(
        before_version_id=before_version_id,
        after_version_id=after_version_id,
        algorithm_version=MATCHING_ALGORITHM_VERSION,
        element_diffs=(
            ElementDiff(
                before_element_id=ids["modified_before"],
                after_element_id=ids["modified_after"],
                before_ordinal=1,
                after_ordinal=1,
                before_text="Old Text",
                after_text="New Text",
                classification=ChangeClassification.MODIFIED,
                confidence=LineageConfidence.SIMILAR,
            ),
            ElementDiff(
                before_element_id=ids["unchanged_before"],
                after_element_id=ids["unchanged_after"],
                before_ordinal=2,
                after_ordinal=2,
                before_text="Unchanged",
                after_text="Unchanged",
                classification=ChangeClassification.UNCHANGED,
                confidence=LineageConfidence.EXACT,
            ),
            ElementDiff(
                before_element_id=ids["removed_before"],
                after_element_id=None,
                before_ordinal=3,
                after_ordinal=None,
                before_text="Removed",
                after_text=None,
                classification=ChangeClassification.REMOVED,
                confidence=None,
            ),
        ),
        rescan_element_ids=(ids["modified_after"],),
        carry_forward_element_ids=(ids["unchanged_after"],),
        removed_element_ids=(ids["removed_before"],),
        affected_element_ids={ids["modified_after"], ids["removed_before"]},
        unaffected_element_ids={ids["unchanged_after"]},
    )
    return diff, {
        **ids,
        "before_version_id": before_version_id,
        "after_version_id": after_version_id,
    }


def test_script_diff_exposes_side_specific_affected_ids():
    diff, ids = _diff_with_distinct_lineage_ids()

    assert diff.affected_before_element_ids == (
        ids["modified_before"],
        ids["removed_before"],
    )
    assert diff.affected_after_element_ids == (ids["modified_after"],)


@pytest.mark.asyncio
async def test_selective_rescan_uses_prior_lineage_and_excludes_removed_items():
    service = SelectiveRescanService()
    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    diff, ids = _diff_with_distinct_lineage_ids()

    modified_item = _item(
        org_id=org_id,
        project_id=project_id,
        version_id=ids["before_version_id"],
        element_id=ids["modified_before"],
        text="Old Text",
    )
    unchanged_item = _item(
        org_id=org_id,
        project_id=project_id,
        version_id=ids["before_version_id"],
        element_id=ids["unchanged_before"],
        text="Unchanged",
    )
    removed_item = _item(
        org_id=org_id,
        project_id=project_id,
        version_id=ids["before_version_id"],
        element_id=ids["removed_before"],
        text="Removed",
    )

    result = await service.execute_rescan(
        org_id=org_id,
        project_id=project_id,
        before_version_id=ids["before_version_id"],
        after_version_id=ids["after_version_id"],
        diff=diff,
        items=[modified_item, unchanged_item, removed_item],
    )

    assert result.affected_items_count == 1
    assert result.saved_calls_count == 1
    assert result.rescanned_item_ids == {modified_item.item_id}
    assert unchanged_item.item_id not in result.rescanned_item_ids
    assert removed_item.item_id not in result.rescanned_item_ids
    assert ids["removed_before"] not in diff.rescan_element_ids

import pytest
import uuid6
from clearcut.scripts.application.materialize_revision import MaterializeRevisionService
from clearcut.scripts.domain.diff import ChangeClassification, compute_script_diff
from clearcut.scripts.domain.elements import ElementType, ScriptElement


def _element(text: str, ordinal: int) -> ScriptElement:
    return ScriptElement.create(
        element_id=uuid6.uuid7(),
        ordinal=ordinal,
        element_type=ElementType.ACTION,
        text=text,
        scene_number=1,
    )


@pytest.mark.asyncio
async def test_materialize_revision_uses_the_pure_lineage_matcher():
    service = MaterializeRevisionService()
    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    script_id = uuid6.uuid7()
    v1_id = uuid6.uuid7()
    unchanged_before = _element("Original Action", 1)
    modified_before = _element("The long corridor is empty.", 2)
    unchanged_after = _element("Original Action", 1)
    modified_after = _element("The long corridor sits empty.", 2)

    v2, diff = await service.materialize_version(
        org_id=org_id,
        project_id=project_id,
        script_id=script_id,
        before_version_id=v1_id,
        ordinal=2,
        elements=[unchanged_after, modified_after],
        before_elements=[unchanged_before, modified_before],
    )
    direct_diff = compute_script_diff(
        before_version_id=v1_id,
        after_version_id=v2.version_id,
        before_elements=[unchanged_before, modified_before],
        after_elements=[unchanged_after, modified_after],
    )

    assert v2.ordinal == 2
    assert v2.elements == (unchanged_after, modified_after)
    assert diff == direct_diff
    assert diff.algorithm_version == "element-lineage-v1"
    assert [row.classification for row in diff.elements] == [
        ChangeClassification.UNCHANGED,
        ChangeClassification.MODIFIED,
    ]
    assert diff.carry_forward_element_ids == (unchanged_after.element_id,)
    assert diff.rescan_element_ids == (modified_after.element_id,)
    assert diff.removed_element_ids == ()

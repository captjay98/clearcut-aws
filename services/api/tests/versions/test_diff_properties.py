import uuid6
from clearcut.scripts.domain.diff import compute_script_diff
from clearcut.scripts.domain.elements import ElementType, ScriptElement


def test_compute_script_diff_detects_modified_and_unchanged_elements():
    element1_id = uuid6.uuid7()
    element2_id = uuid6.uuid7()

    before_elem1 = ScriptElement.create(
        element_id=element1_id,
        ordinal=1,
        element_type=ElementType.ACTION,
        text="He drinks a can of Coca-Cola.",
        scene_number=1,
    )
    before_elem2 = ScriptElement.create(
        element_id=element2_id,
        ordinal=2,
        element_type=ElementType.DIALOGUE,
        text="Nice weather today.",
        scene_number=1,
    )

    # After: element 1 is modified (Coca-Cola -> Sparkling Soda), element 2 is unchanged
    after_elem1 = ScriptElement.create(
        element_id=element1_id,
        ordinal=1,
        element_type=ElementType.ACTION,
        text="He drinks a can of Sparkling Soda.",
        scene_number=1,
    )
    after_elem2 = ScriptElement.create(
        element_id=element2_id,
        ordinal=2,
        element_type=ElementType.DIALOGUE,
        text="Nice weather today.",
        scene_number=1,
    )

    v1_id = uuid6.uuid7()
    v2_id = uuid6.uuid7()

    diff = compute_script_diff(
        before_version_id=v1_id,
        after_version_id=v2_id,
        before_elements=[before_elem1, before_elem2],
        after_elements=[after_elem1, after_elem2],
    )

    assert element1_id in diff.affected_element_ids
    assert element2_id in diff.unaffected_element_ids
    assert len(diff.element_diffs) == 2

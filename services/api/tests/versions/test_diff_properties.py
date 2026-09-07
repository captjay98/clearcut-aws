import uuid6
from clearcut.scripts.domain import diff as diff_domain
from clearcut.scripts.domain.diff import ChangeClassification, compute_script_diff
from clearcut.scripts.domain.elements import ElementType, ScriptElement


def _element(
    text: str,
    ordinal: int,
    element_type: ElementType = ElementType.ACTION,
) -> ScriptElement:
    return ScriptElement.create(
        element_id=uuid6.uuid7(),
        ordinal=ordinal,
        element_type=element_type,
        text=text,
        scene_number=1,
    )


def _compute(
    before_elements: list[ScriptElement],
    after_elements: list[ScriptElement],
):
    return compute_script_diff(
        before_version_id=uuid6.uuid7(),
        after_version_id=uuid6.uuid7(),
        before_elements=before_elements,
        after_elements=after_elements,
    )


def test_compute_script_diff_classifies_all_outcomes_with_distinct_ids():
    unchanged_before = _element("Rain streaks the window.", 1)
    moved_before = _element("The brass clock strikes midnight.", 2)
    anchor_before = _element("Mara closes the ledger.", 3)
    modified_before = _element("Jon opens the heavy wooden door.", 4)
    removed_before = _element("A telephone rings upstairs.", 5)

    unchanged_after = _element("Rain streaks the window.", 1)
    anchor_after = _element("Mara closes the ledger.", 2)
    modified_after = _element("Jon opens the heavy wood door.", 3)
    added_after = _element("Footsteps cross the empty hall.", 4)
    moved_after = _element("The brass clock strikes midnight.", 5)

    diff = _compute(
        [
            unchanged_before,
            moved_before,
            anchor_before,
            modified_before,
            removed_before,
        ],
        [
            unchanged_after,
            anchor_after,
            modified_after,
            added_after,
            moved_after,
        ],
    )

    assert diff.algorithm_version == diff_domain.MATCHING_ALGORITHM_VERSION
    assert diff.algorithm_version == "element-lineage-v1"
    assert {row.classification for row in diff.elements} == set(ChangeClassification)

    by_after_id = {row.after_element_id: row for row in diff.elements}
    unchanged = by_after_id[unchanged_after.element_id]
    moved = by_after_id[moved_after.element_id]
    modified = by_after_id[modified_after.element_id]
    added = by_after_id[added_after.element_id]
    removed = next(
        row
        for row in diff.elements
        if row.before_element_id == removed_before.element_id
    )

    assert (unchanged.before_element_id, unchanged.after_element_id) == (
        unchanged_before.element_id,
        unchanged_after.element_id,
    )
    assert (moved.before_element_id, moved.after_element_id) == (
        moved_before.element_id,
        moved_after.element_id,
    )
    assert (modified.before_element_id, modified.after_element_id) == (
        modified_before.element_id,
        modified_after.element_id,
    )
    assert (added.before_element_id, added.after_element_id) == (
        None,
        added_after.element_id,
    )
    assert (removed.before_element_id, removed.after_element_id) == (
        removed_before.element_id,
        None,
    )
    assert (unchanged.before_ordinal, unchanged.after_ordinal) == (1, 1)
    assert (moved.before_ordinal, moved.after_ordinal) == (2, 5)
    assert modified.confidence.value == "similar"
    assert added.confidence is None
    assert removed.confidence is None

    assert diff.rescan_element_ids == (
        modified_after.element_id,
        added_after.element_id,
    )
    assert diff.carry_forward_element_ids == (
        unchanged_after.element_id,
        anchor_after.element_id,
        moved_after.element_id,
    )
    assert diff.removed_element_ids == (removed_before.element_id,)
    assert diff.affected_element_ids == {
        modified_after.element_id,
        added_after.element_id,
        removed_before.element_id,
    }
    assert diff.unaffected_element_ids == {
        unchanged_after.element_id,
        anchor_after.element_id,
        moved_after.element_id,
    }


def test_exact_duplicate_text_is_disambiguated_by_neighbor_context():
    before = [
        _element("Kitchen", 1, ElementType.SCENE_HEADING),
        _element("Yes.", 2, ElementType.DIALOGUE),
        _element("Hallway", 3, ElementType.SCENE_HEADING),
        _element("Yes.", 4, ElementType.DIALOGUE),
        _element("Garden", 5, ElementType.SCENE_HEADING),
    ]
    after = [
        _element("Kitchen", 1, ElementType.SCENE_HEADING),
        _element("Yes.", 2, ElementType.DIALOGUE),
        _element("Hallway", 3, ElementType.SCENE_HEADING),
        _element("Yes.", 4, ElementType.DIALOGUE),
        _element("Garden", 5, ElementType.SCENE_HEADING),
    ]

    diff = _compute(before, after)
    dialogue_rows = [
        row
        for row in diff.elements
        if row.after_element_id in {after[1].element_id, after[3].element_id}
    ]

    assert [row.classification for row in dialogue_rows] == [
        ChangeClassification.UNCHANGED,
        ChangeClassification.UNCHANGED,
    ]
    assert [row.confidence.value for row in dialogue_rows] == [
        "contextual",
        "contextual",
    ]
    assert [row.before_element_id for row in dialogue_rows] == [
        before[1].element_id,
        before[3].element_id,
    ]


def test_normalized_exact_matching_requires_the_same_element_type():
    exact_before = _element("Cafe\u0301   noir\nwaits.", 1, ElementType.ACTION)
    wrong_type_before = _element("A shared line", 2, ElementType.ACTION)
    exact_after = _element("Café noir waits.", 1, ElementType.ACTION)
    wrong_type_after = _element("A shared line", 2, ElementType.DIALOGUE)

    diff = _compute([exact_before, wrong_type_before], [exact_after, wrong_type_after])

    exact_row = next(row for row in diff.elements if row.after_element_id == exact_after.element_id)
    assert exact_row.classification is ChangeClassification.UNCHANGED
    assert exact_row.confidence.value == "exact"
    assert exact_row.before_element_id == exact_before.element_id

    wrong_type_rows = [
        row
        for row in diff.elements
        if row.before_element_id == wrong_type_before.element_id
        or row.after_element_id == wrong_type_after.element_id
    ]
    assert [row.classification for row in wrong_type_rows] == [
        ChangeClassification.ADDED,
        ChangeClassification.REMOVED,
    ]


def test_conservative_same_type_similarity_is_modified_not_carryable():
    before = _element("Jon opens the heavy wooden door.", 1, ElementType.ACTION)
    after = _element("Jon opens the heavy wood door.", 1, ElementType.ACTION)

    diff = _compute([before], [after])

    assert len(diff.elements) == 1
    row = diff.elements[0]
    assert row.classification is ChangeClassification.MODIFIED
    assert row.confidence.value == "similar"
    assert row.before_element_id == before.element_id
    assert row.after_element_id == after.element_id
    assert diff.rescan_element_ids == (after.element_id,)
    assert diff.carry_forward_element_ids == ()


def test_ambiguous_exact_duplicates_fail_safe_as_removed_and_added():
    before = [
        _element("Anchor", 1, ElementType.ACTION),
        _element("Repeated", 2, ElementType.DIALOGUE),
        _element("Boundary", 3, ElementType.ACTION),
        _element("Anchor", 4, ElementType.ACTION),
        _element("Repeated", 5, ElementType.DIALOGUE),
        _element("Boundary", 6, ElementType.ACTION),
    ]
    after = [
        _element("Anchor", 1, ElementType.ACTION),
        _element("Repeated", 2, ElementType.DIALOGUE),
        _element("Boundary", 3, ElementType.ACTION),
        _element("Anchor", 4, ElementType.ACTION),
        _element("Repeated", 5, ElementType.DIALOGUE),
        _element("Boundary", 6, ElementType.ACTION),
    ]

    diff = _compute(before, after)
    repeated_before_ids = {before[1].element_id, before[4].element_id}
    repeated_after_ids = {after[1].element_id, after[4].element_id}
    repeated_rows = [
        row
        for row in diff.elements
        if row.before_element_id in repeated_before_ids
        or row.after_element_id in repeated_after_ids
    ]

    assert [row.classification for row in repeated_rows] == [
        ChangeClassification.ADDED,
        ChangeClassification.ADDED,
        ChangeClassification.REMOVED,
        ChangeClassification.REMOVED,
    ]
    assert repeated_after_ids <= set(diff.rescan_element_ids)
    assert repeated_before_ids <= set(diff.removed_element_ids)
    assert repeated_after_ids.isdisjoint(diff.carry_forward_element_ids)


def test_insertion_does_not_mark_following_exact_elements_as_moved():
    before = [
        _element("First", 1),
        _element("Second", 2),
        _element("Third", 3),
    ]
    inserted = _element("Inserted", 1)
    after = [
        inserted,
        _element("First", 2),
        _element("Second", 3),
        _element("Third", 4),
    ]

    diff = _compute(before, after)

    assert [row.classification for row in diff.elements] == [
        ChangeClassification.ADDED,
        ChangeClassification.UNCHANGED,
        ChangeClassification.UNCHANGED,
        ChangeClassification.UNCHANGED,
    ]
    assert diff.rescan_element_ids == (inserted.element_id,)


def test_output_order_and_repeated_calls_are_deterministic():
    before = [
        _element("Removed late", 9),
        _element("Stable", 4),
        _element("Removed early", 2),
    ]
    after = [
        _element("Added second", 7),
        _element("Stable", 5),
        _element("Added first", 1),
    ]
    before_version_id = uuid6.uuid7()
    after_version_id = uuid6.uuid7()

    first = compute_script_diff(
        before_version_id=before_version_id,
        after_version_id=after_version_id,
        before_elements=before,
        after_elements=after,
    )
    second = compute_script_diff(
        before_version_id=before_version_id,
        after_version_id=after_version_id,
        before_elements=before,
        after_elements=after,
    )

    assert first == second
    assert [
        (row.after_ordinal, row.before_ordinal)
        for row in first.elements
    ] == [
        (1, None),
        (5, 4),
        (7, None),
        (None, 2),
        (None, 9),
    ]



def test_crossing_exact_matches_keep_the_earliest_after_line_stable():
    before = [_element("First", 1), _element("Second", 2)]
    after = [_element("Second", 1), _element("First", 2)]

    diff = _compute(before, after)
    by_after_id = {row.after_element_id: row for row in diff.elements}

    assert by_after_id[after[0].element_id].classification is ChangeClassification.UNCHANGED
    assert by_after_id[after[1].element_id].classification is ChangeClassification.MOVED


def test_similarity_comparisons_are_unique_and_bounded_for_screenplay_scale(
    monkeypatch,
):
    line_count = 500
    before = [
        _element(
            f"Character {index:03d} studies package {index:03d} by the north window.",
            index + 1,
            ElementType.DIALOGUE,
        )
        for index in range(line_count)
    ]
    after = [
        _element(
            f"Character {index:03d} studies package {index:03d} by the south window.",
            index + 1,
            ElementType.DIALOGUE,
        )
        for index in range(line_count)
    ]
    original_similarity = diff_domain._similarity
    comparison_count = 0
    compared_pairs: set[frozenset[int]] = set()

    def counted_similarity(before_element, after_element):
        nonlocal comparison_count
        comparison_count += 1
        compared_pairs.add(frozenset((id(before_element), id(after_element))))
        return original_similarity(before_element, after_element)

    monkeypatch.setattr(diff_domain, "_similarity", counted_similarity)

    diff = _compute(before, after)

    assert len(diff.elements) == line_count * 2
    assert comparison_count == len(compared_pairs)
    assert comparison_count <= 40_000

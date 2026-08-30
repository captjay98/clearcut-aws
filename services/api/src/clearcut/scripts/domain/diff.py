from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from clearcut.scripts.domain.elements import ScriptElement


class ChangeClassification(StrEnum):
    UNCHANGED = "unchanged"
    MODIFIED = "modified"
    ADDED = "added"
    REMOVED = "removed"
    MOVED = "moved"


@dataclass(frozen=True)
class ElementDiff:
    element_id: UUID
    before_text: str | None
    after_text: str | None
    classification: ChangeClassification


@dataclass(frozen=True)
class ScriptDiff:
    before_version_id: UUID
    after_version_id: UUID
    element_diffs: list[ElementDiff]
    affected_element_ids: set[UUID]
    unaffected_element_ids: set[UUID]


def compute_script_diff(
    before_version_id: UUID,
    after_version_id: UUID,
    before_elements: list[ScriptElement],
    after_elements: list[ScriptElement],
) -> ScriptDiff:
    before_map = {e.element_id: e for e in before_elements}
    after_map = {e.element_id: e for e in after_elements}

    all_ids = set(before_map.keys()) | set(after_map.keys())
    diffs: list[ElementDiff] = []
    affected: set[UUID] = set()
    unaffected: set[UUID] = set()

    for eid in all_ids:
        b = before_map.get(eid)
        a = after_map.get(eid)

        if b is not None and a is not None:
            if b.text == a.text:
                classification = ChangeClassification.UNCHANGED
                unaffected.add(eid)
            else:
                classification = ChangeClassification.MODIFIED
                affected.add(eid)
            diffs.append(ElementDiff(eid, b.text, a.text, classification))
        elif b is not None and a is None:
            classification = ChangeClassification.REMOVED
            affected.add(eid)
            diffs.append(ElementDiff(eid, b.text, None, classification))
        elif b is None and a is not None:
            classification = ChangeClassification.ADDED
            affected.add(eid)
            diffs.append(ElementDiff(eid, None, a.text, classification))

    return ScriptDiff(
        before_version_id=before_version_id,
        after_version_id=after_version_id,
        element_diffs=diffs,
        affected_element_ids=affected,
        unaffected_element_ids=unaffected,
    )

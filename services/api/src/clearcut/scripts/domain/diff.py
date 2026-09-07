import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import StrEnum
from typing import Final
from uuid import UUID

from clearcut.scripts.domain.elements import ElementType, ScriptElement

MATCHING_ALGORITHM_VERSION: Final = "element-lineage-v1"
_SIMILARITY_THRESHOLD: Final = 0.9
_SIMILARITY_RUNNER_UP_MARGIN: Final = 0.05


class ChangeClassification(StrEnum):
    UNCHANGED = "unchanged"
    MODIFIED = "modified"
    ADDED = "added"
    REMOVED = "removed"
    MOVED = "moved"


class LineageConfidence(StrEnum):
    EXACT = "exact"
    CONTEXTUAL = "contextual"
    SIMILAR = "similar"


@dataclass(frozen=True)
class ElementDiff:
    before_element_id: UUID | None
    after_element_id: UUID | None
    before_ordinal: int | None
    after_ordinal: int | None
    before_text: str | None
    after_text: str | None
    classification: ChangeClassification
    confidence: LineageConfidence | None

    @property
    def element_id(self) -> UUID:
        element_id = self.after_element_id or self.before_element_id
        if element_id is None:
            raise ValueError("an element diff must have a before or after element ID")
        return element_id


@dataclass(frozen=True)
class ScriptDiff:
    before_version_id: UUID
    after_version_id: UUID
    algorithm_version: str
    element_diffs: tuple[ElementDiff, ...]
    rescan_element_ids: tuple[UUID, ...]
    carry_forward_element_ids: tuple[UUID, ...]
    removed_element_ids: tuple[UUID, ...]
    affected_element_ids: set[UUID]
    unaffected_element_ids: set[UUID]

    @property
    def elements(self) -> tuple[ElementDiff, ...]:
        return self.element_diffs


@dataclass(frozen=True)
class _LineageMatch:
    before_index: int
    after_index: int
    confidence: LineageConfidence


_ElementKey = tuple[ElementType, str]
_ContextKey = tuple[_ElementKey | None, _ElementKey | None]


def _normalize_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).split())


def _element_key(element: ScriptElement) -> _ElementKey:
    return element.element_type, _normalize_text(element.text)


def _group_indexes(elements: list[ScriptElement]) -> dict[_ElementKey, list[int]]:
    grouped: dict[_ElementKey, list[int]] = defaultdict(list)
    for index, element in enumerate(elements):
        grouped[_element_key(element)].append(index)
    return grouped


def _context_key(elements: list[ScriptElement], index: int) -> _ContextKey:
    previous = _element_key(elements[index - 1]) if index > 0 else None
    following = _element_key(elements[index + 1]) if index + 1 < len(elements) else None
    return previous, following


def _unique_exact_matches(
    before_elements: list[ScriptElement],
    after_elements: list[ScriptElement],
) -> list[_LineageMatch]:
    before_groups = _group_indexes(before_elements)
    after_groups = _group_indexes(after_elements)
    matches: list[_LineageMatch] = []

    for key, before_indexes in before_groups.items():
        after_indexes = after_groups.get(key, [])
        if len(before_indexes) == len(after_indexes) == 1:
            matches.append(
                _LineageMatch(
                    before_index=before_indexes[0],
                    after_index=after_indexes[0],
                    confidence=LineageConfidence.EXACT,
                )
            )

    return matches


def _contextual_exact_matches(
    before_elements: list[ScriptElement],
    after_elements: list[ScriptElement],
    matched_before: set[int],
    matched_after: set[int],
) -> list[_LineageMatch]:
    before_groups = _group_indexes(before_elements)
    after_groups = _group_indexes(after_elements)
    matches: list[_LineageMatch] = []

    for key, all_before_indexes in before_groups.items():
        before_indexes = [index for index in all_before_indexes if index not in matched_before]
        after_indexes = [
            index
            for index in after_groups.get(key, [])
            if index not in matched_after
        ]
        if not before_indexes or not after_indexes:
            continue

        before_contexts = {
            index: _context_key(before_elements, index) for index in before_indexes
        }
        after_contexts = {
            index: _context_key(after_elements, index) for index in after_indexes
        }
        before_counts = Counter(before_contexts.values())
        after_counts = Counter(after_contexts.values())
        after_by_context = {
            context: index for index, context in after_contexts.items()
        }

        for before_index in before_indexes:
            context = before_contexts[before_index]
            if before_counts[context] != 1 or after_counts[context] != 1:
                continue
            after_index = after_by_context[context]
            matches.append(
                _LineageMatch(
                    before_index=before_index,
                    after_index=after_index,
                    confidence=LineageConfidence.CONTEXTUAL,
                )
            )
            matched_before.add(before_index)
            matched_after.add(after_index)

    return matches


def _similarity(
    before_element: ScriptElement,
    after_element: ScriptElement,
) -> float:
    if before_element.element_type is not after_element.element_type:
        return 0.0
    before_text = _normalize_text(before_element.text)
    after_text = _normalize_text(after_element.text)
    if before_text == after_text:
        return 0.0
    return SequenceMatcher(None, before_text, after_text, autojunk=False).ratio()


def _unique_best_candidates(
    source_indexes: set[int],
    target_indexes: set[int],
    source_elements: list[ScriptElement],
    target_elements: list[ScriptElement],
) -> dict[int, int]:
    best_candidates: dict[int, int] = {}
    for source_index in sorted(source_indexes):
        candidates = sorted(
            (
                (
                    _similarity(
                        source_elements[source_index],
                        target_elements[target_index],
                    ),
                    target_index,
                )
                for target_index in target_indexes
            ),
            key=lambda candidate: (-candidate[0], candidate[1]),
        )
        if not candidates:
            continue
        best_score, best_target = candidates[0]
        runner_up_score = candidates[1][0] if len(candidates) > 1 else 0.0
        if (
            best_score > _SIMILARITY_THRESHOLD
            and best_score - runner_up_score > _SIMILARITY_RUNNER_UP_MARGIN
        ):
            best_candidates[source_index] = best_target
    return best_candidates


def _similar_matches(
    before_elements: list[ScriptElement],
    after_elements: list[ScriptElement],
    matched_before: set[int],
    matched_after: set[int],
) -> list[_LineageMatch]:
    unmatched_before = set(range(len(before_elements))) - matched_before
    unmatched_after = set(range(len(after_elements))) - matched_after
    best_after = _unique_best_candidates(
        unmatched_before,
        unmatched_after,
        before_elements,
        after_elements,
    )
    best_before = _unique_best_candidates(
        unmatched_after,
        unmatched_before,
        after_elements,
        before_elements,
    )

    matches: list[_LineageMatch] = []
    for before_index, after_index in sorted(best_after.items()):
        if best_before.get(after_index) != before_index:
            continue
        matches.append(
            _LineageMatch(
                before_index=before_index,
                after_index=after_index,
                confidence=LineageConfidence.SIMILAR,
            )
        )
        matched_before.add(before_index)
        matched_after.add(after_index)
    return matches


def _stable_exact_pairs(matches: list[_LineageMatch]) -> set[tuple[int, int]]:
    exact_matches = sorted(
        (
            match
            for match in matches
            if match.confidence
            in {LineageConfidence.EXACT, LineageConfidence.CONTEXTUAL}
        ),
        key=lambda match: (match.after_index, match.before_index),
    )
    if not exact_matches:
        return set()

    lengths = [1] * len(exact_matches)
    previous: list[int | None] = [None] * len(exact_matches)
    for current_index, current in enumerate(exact_matches):
        for candidate_index in range(current_index):
            candidate = exact_matches[candidate_index]
            if candidate.before_index >= current.before_index:
                continue
            candidate_length = lengths[candidate_index] + 1
            if candidate_length > lengths[current_index]:
                lengths[current_index] = candidate_length
                previous[current_index] = candidate_index

    end_index = max(range(len(exact_matches)), key=lengths.__getitem__)
    stable: set[tuple[int, int]] = set()
    while end_index is not None:
        match = exact_matches[end_index]
        stable.add((match.before_index, match.after_index))
        end_index = previous[end_index]
    return stable


def _matched_element_diff(
    match: _LineageMatch,
    before_element: ScriptElement,
    after_element: ScriptElement,
    stable_exact_pairs: set[tuple[int, int]],
) -> ElementDiff:
    if match.confidence is LineageConfidence.SIMILAR:
        classification = ChangeClassification.MODIFIED
    elif (match.before_index, match.after_index) in stable_exact_pairs:
        classification = ChangeClassification.UNCHANGED
    else:
        classification = ChangeClassification.MOVED

    return ElementDiff(
        before_element_id=before_element.element_id,
        after_element_id=after_element.element_id,
        before_ordinal=before_element.ordinal,
        after_ordinal=after_element.ordinal,
        before_text=before_element.text,
        after_text=after_element.text,
        classification=classification,
        confidence=match.confidence,
    )


def _element_diff_sort_key(
    element_diff: ElementDiff,
) -> tuple[bool, int, int, str, str]:
    return (
        element_diff.after_ordinal is None,
        element_diff.after_ordinal or 0,
        element_diff.before_ordinal or 0,
        str(element_diff.after_element_id or ""),
        str(element_diff.before_element_id or ""),
    )


def compute_script_diff(
    before_version_id: UUID,
    after_version_id: UUID,
    before_elements: list[ScriptElement],
    after_elements: list[ScriptElement],
) -> ScriptDiff:
    matches = _unique_exact_matches(before_elements, after_elements)
    matched_before = {match.before_index for match in matches}
    matched_after = {match.after_index for match in matches}
    matches.extend(
        _contextual_exact_matches(
            before_elements,
            after_elements,
            matched_before,
            matched_after,
        )
    )
    matches.extend(
        _similar_matches(
            before_elements,
            after_elements,
            matched_before,
            matched_after,
        )
    )

    stable_exact_pairs = _stable_exact_pairs(matches)
    element_diffs = [
        _matched_element_diff(
            match,
            before_elements[match.before_index],
            after_elements[match.after_index],
            stable_exact_pairs,
        )
        for match in matches
    ]
    element_diffs.extend(
        ElementDiff(
            before_element_id=before_elements[index].element_id,
            after_element_id=None,
            before_ordinal=before_elements[index].ordinal,
            after_ordinal=None,
            before_text=before_elements[index].text,
            after_text=None,
            classification=ChangeClassification.REMOVED,
            confidence=None,
        )
        for index in range(len(before_elements))
        if index not in matched_before
    )
    element_diffs.extend(
        ElementDiff(
            before_element_id=None,
            after_element_id=after_elements[index].element_id,
            before_ordinal=None,
            after_ordinal=after_elements[index].ordinal,
            before_text=None,
            after_text=after_elements[index].text,
            classification=ChangeClassification.ADDED,
            confidence=None,
        )
        for index in range(len(after_elements))
        if index not in matched_after
    )
    element_diffs.sort(key=_element_diff_sort_key)
    ordered_diffs = tuple(element_diffs)

    rescan_element_ids = tuple(
        element_diff.after_element_id
        for element_diff in ordered_diffs
        if element_diff.classification
        in {ChangeClassification.MODIFIED, ChangeClassification.ADDED}
        and element_diff.after_element_id is not None
    )
    carry_forward_element_ids = tuple(
        element_diff.after_element_id
        for element_diff in ordered_diffs
        if element_diff.classification
        in {ChangeClassification.UNCHANGED, ChangeClassification.MOVED}
        and element_diff.confidence
        in {LineageConfidence.EXACT, LineageConfidence.CONTEXTUAL}
        and element_diff.after_element_id is not None
    )
    removed_element_ids = tuple(
        element_diff.before_element_id
        for element_diff in ordered_diffs
        if element_diff.classification is ChangeClassification.REMOVED
        and element_diff.before_element_id is not None
    )

    return ScriptDiff(
        before_version_id=before_version_id,
        after_version_id=after_version_id,
        algorithm_version=MATCHING_ALGORITHM_VERSION,
        element_diffs=ordered_diffs,
        rescan_element_ids=rescan_element_ids,
        carry_forward_element_ids=carry_forward_element_ids,
        removed_element_ids=removed_element_ids,
        affected_element_ids=set(rescan_element_ids) | set(removed_element_ids),
        unaffected_element_ids=set(carry_forward_element_ids),
    )

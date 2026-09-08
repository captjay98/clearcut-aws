import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import StrEnum
from typing import Final
from uuid import UUID

from clearcut.scripts.domain.elements import ElementType, ScriptElement

MATCHING_ALGORITHM_VERSION: Final = "element-lineage-v1"
# Fuzzy scoring is synchronous. Before candidate filtering or scoring, enforce
# the same-type pair count, a worst-case single-pair character-work ceiling,
# and a conservative raw Cartesian character-work estimate. The separate
# 50-million per-pair ceiling rejects pathological individual comparisons;
# the 150-million aggregate ceiling still permits 9,801 typical screenplay-line
# pairs while rejecting large Cartesian inputs. Exceeding any preflight budget
# skips the entire fuzzy phase rather than creating arbitrary partial lineage.
MAX_SIMILARITY_PAIR_EVALUATIONS: Final = 10_000
MAX_SIMILARITY_PAIR_CHARACTER_WORK: Final = 50_000_000
MAX_SIMILARITY_CHARACTER_WORK: Final = 150_000_000
_SIMILARITY_THRESHOLD: Final = 0.9
_SIMILARITY_RUNNER_UP_MARGIN: Final = 0.05
_SIMILARITY_AMBIGUITY_FLOOR: Final = (
    _SIMILARITY_THRESHOLD - _SIMILARITY_RUNNER_UP_MARGIN
)


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

    @property
    def affected_before_element_ids(self) -> tuple[UUID, ...]:
        return tuple(
            element_diff.before_element_id
            for element_diff in self.element_diffs
            if element_diff.classification
            in {ChangeClassification.MODIFIED, ChangeClassification.REMOVED}
            and element_diff.before_element_id is not None
        )

    @property
    def affected_after_element_ids(self) -> tuple[UUID, ...]:
        return self.rescan_element_ids

    @property
    def rescan_before_element_ids(self) -> tuple[UUID, ...]:
        return tuple(
            element_diff.before_element_id
            for element_diff in self.element_diffs
            if element_diff.classification is ChangeClassification.MODIFIED
            and element_diff.before_element_id is not None
        )

    @property
    def carry_forward_before_element_ids(self) -> tuple[UUID, ...]:
        return tuple(
            element_diff.before_element_id
            for element_diff in self.element_diffs
            if element_diff.classification
            in {ChangeClassification.UNCHANGED, ChangeClassification.MOVED}
            and element_diff.confidence
            in {LineageConfidence.EXACT, LineageConfidence.CONTEXTUAL}
            and element_diff.before_element_id is not None
        )


@dataclass(frozen=True)
class _LineageMatch:
    before_index: int
    after_index: int
    confidence: LineageConfidence


_ElementKey = tuple[ElementType, str]
_ContextKey = tuple[_ElementKey | None, _ElementKey | None]
_Candidate = tuple[float, int]
_TopCandidates = tuple[_Candidate | None, _Candidate | None]
_SubsequenceEndpoint = tuple[int, int]


@dataclass(frozen=True)
class _PreparedElement:
    element: ScriptElement
    element_type: ElementType
    normalized_text: str
    text_length: int
    character_counts: Counter[str]
    key: _ElementKey


def _normalize_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).split())


def _prepare_elements(elements: list[ScriptElement]) -> tuple[_PreparedElement, ...]:
    prepared: list[_PreparedElement] = []
    for element in elements:
        normalized_text = _normalize_text(element.text)
        prepared.append(
            _PreparedElement(
                element=element,
                element_type=element.element_type,
                normalized_text=normalized_text,
                text_length=len(normalized_text),
                character_counts=Counter(normalized_text),
                key=(element.element_type, normalized_text),
            )
        )
    return tuple(prepared)


def _group_indexes(
    elements: tuple[_PreparedElement, ...],
) -> dict[_ElementKey, list[int]]:
    grouped: dict[_ElementKey, list[int]] = defaultdict(list)
    for index, element in enumerate(elements):
        grouped[element.key].append(index)
    return grouped


def _context_key(
    elements: tuple[_PreparedElement, ...],
    index: int,
) -> _ContextKey:
    previous = elements[index - 1].key if index > 0 else None
    following = elements[index + 1].key if index + 1 < len(elements) else None
    return previous, following


def _unique_exact_matches(
    before_elements: tuple[_PreparedElement, ...],
    after_elements: tuple[_PreparedElement, ...],
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
    before_elements: tuple[_PreparedElement, ...],
    after_elements: tuple[_PreparedElement, ...],
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
    before_element: _PreparedElement,
    after_element: _PreparedElement,
) -> float:
    if before_element.element_type is not after_element.element_type:
        return 0.0
    if before_element.normalized_text == after_element.normalized_text:
        return 0.0
    return SequenceMatcher(
        None,
        before_element.normalized_text,
        after_element.normalized_text,
        autojunk=False,
    ).ratio()


def _indexes_by_type(
    indexes: set[int],
    elements: tuple[_PreparedElement, ...],
) -> dict[ElementType, list[int]]:
    indexes_by_type: dict[ElementType, list[int]] = defaultdict(list)
    for index in sorted(indexes):
        indexes_by_type[elements[index].element_type].append(index)
    return indexes_by_type


def _character_multiset_similarity_upper_bound(
    source_element: _PreparedElement,
    target_element: _PreparedElement,
) -> float:
    combined_length = source_element.text_length + target_element.text_length
    if combined_length == 0:
        return 0.0
    source_counts = source_element.character_counts
    target_counts = target_element.character_counts
    if len(source_counts) > len(target_counts):
        source_counts, target_counts = target_counts, source_counts
    shared_characters = sum(
        min(count, target_counts.get(character, 0))
        for character, count in source_counts.items()
    )
    return (2 * shared_characters) / combined_length


def _can_affect_similarity_choice(
    source_element: _PreparedElement,
    target_element: _PreparedElement,
) -> bool:
    if source_element.normalized_text == target_element.normalized_text:
        return False
    combined_length = source_element.text_length + target_element.text_length
    if combined_length == 0:
        return False
    length_ratio_upper_bound = (
        2 * min(source_element.text_length, target_element.text_length)
    ) / combined_length
    if length_ratio_upper_bound <= _SIMILARITY_AMBIGUITY_FLOOR:
        return False
    return (
        _character_multiset_similarity_upper_bound(source_element, target_element)
        > _SIMILARITY_AMBIGUITY_FLOOR
    )


def _similarity_candidate_pairs(
    unmatched_before: set[int],
    unmatched_after: set[int],
    before_elements: tuple[_PreparedElement, ...],
    after_elements: tuple[_PreparedElement, ...],
) -> Iterator[tuple[int, int]]:
    after_by_type = _indexes_by_type(unmatched_after, after_elements)

    for before_index in sorted(unmatched_before):
        before_element = before_elements[before_index]
        for after_index in after_by_type.get(before_element.element_type, []):
            if _can_affect_similarity_choice(
                before_element,
                after_elements[after_index],
            ):
                yield before_index, after_index


def _candidate_is_better(candidate: _Candidate, incumbent: _Candidate) -> bool:
    return candidate[0] > incumbent[0] or (
        candidate[0] == incumbent[0] and candidate[1] < incumbent[1]
    )


def _record_candidate(
    top_candidates: dict[int, _TopCandidates],
    source_index: int,
    target_index: int,
    score: float,
) -> None:
    candidate = (score, target_index)
    best, runner_up = top_candidates.get(source_index, (None, None))
    if best is None or _candidate_is_better(candidate, best):
        top_candidates[source_index] = (candidate, best)
        return
    if runner_up is None or _candidate_is_better(candidate, runner_up):
        top_candidates[source_index] = (best, candidate)


def _unique_best_candidates(
    top_candidates: dict[int, _TopCandidates],
) -> dict[int, int]:
    best_candidates: dict[int, int] = {}
    for source_index in sorted(top_candidates):
        best, runner_up = top_candidates[source_index]
        if best is None:
            continue
        best_score, best_target = best
        runner_up_score = runner_up[0] if runner_up is not None else 0.0
        if (
            best_score > _SIMILARITY_THRESHOLD
            and best_score - runner_up_score > _SIMILARITY_RUNNER_UP_MARGIN
        ):
            best_candidates[source_index] = best_target
    return best_candidates


def _similar_matches(
    before_elements: tuple[_PreparedElement, ...],
    after_elements: tuple[_PreparedElement, ...],
    matched_before: set[int],
    matched_after: set[int],
) -> list[_LineageMatch]:
    unmatched_before = set(range(len(before_elements))) - matched_before
    unmatched_after = set(range(len(after_elements))) - matched_after
    before_by_type = _indexes_by_type(unmatched_before, before_elements)
    after_by_type = _indexes_by_type(unmatched_after, after_elements)
    pair_evaluations = sum(
        len(before_indexes) * len(after_by_type.get(element_type, ()))
        for element_type, before_indexes in before_by_type.items()
    )
    if pair_evaluations > MAX_SIMILARITY_PAIR_EVALUATIONS:
        return []

    max_before_length_by_type = {
        element_type: max(
            before_elements[index].text_length for index in before_indexes
        )
        for element_type, before_indexes in before_by_type.items()
    }
    max_after_length_by_type = {
        element_type: max(
            after_elements[index].text_length for index in after_indexes
        )
        for element_type, after_indexes in after_by_type.items()
    }
    if any(
        max_before_length
        * max_after_length_by_type.get(element_type, 0)
        > MAX_SIMILARITY_PAIR_CHARACTER_WORK
        for element_type, max_before_length in max_before_length_by_type.items()
    ):
        return []

    before_length_by_type = {
        element_type: sum(
            before_elements[index].text_length for index in before_indexes
        )
        for element_type, before_indexes in before_by_type.items()
    }
    after_length_by_type = {
        element_type: sum(
            after_elements[index].text_length for index in after_indexes
        )
        for element_type, after_indexes in after_by_type.items()
    }
    raw_character_work = sum(
        before_length * after_length_by_type.get(element_type, 0)
        for element_type, before_length in before_length_by_type.items()
    )
    if raw_character_work > MAX_SIMILARITY_CHARACTER_WORK:
        return []

    candidate_pairs = tuple(
        _similarity_candidate_pairs(
            unmatched_before,
            unmatched_after,
            before_elements,
            after_elements,
        )
    )
    eligible_character_work = sum(
        before_elements[before_index].text_length
        * after_elements[after_index].text_length
        for before_index, after_index in candidate_pairs
    )
    if eligible_character_work > MAX_SIMILARITY_CHARACTER_WORK:
        return []

    before_candidates: dict[int, _TopCandidates] = {}
    after_candidates: dict[int, _TopCandidates] = {}

    for before_index, after_index in candidate_pairs:
        score = _similarity(
            before_elements[before_index],
            after_elements[after_index],
        )
        _record_candidate(before_candidates, before_index, after_index, score)
        _record_candidate(after_candidates, after_index, before_index, score)

    best_after = _unique_best_candidates(before_candidates)
    best_before = _unique_best_candidates(after_candidates)
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


def _preferred_endpoint(
    candidate: _SubsequenceEndpoint,
    incumbent: _SubsequenceEndpoint | None,
) -> _SubsequenceEndpoint:
    if incumbent is None:
        return candidate
    if candidate[0] != incumbent[0]:
        return candidate if candidate[0] > incumbent[0] else incumbent
    return candidate if candidate[1] < incumbent[1] else incumbent


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

    tree: list[_SubsequenceEndpoint | None] = [
        None
    ] * (max(match.before_index for match in exact_matches) + 2)
    previous: list[int | None] = [None] * len(exact_matches)
    best_endpoint: _SubsequenceEndpoint | None = None

    for current_index, current in enumerate(exact_matches):
        query_index = current.before_index
        predecessor: _SubsequenceEndpoint | None = None
        while query_index > 0:
            endpoint = tree[query_index]
            if endpoint is not None:
                predecessor = _preferred_endpoint(endpoint, predecessor)
            query_index -= query_index & -query_index

        current_length = 1 if predecessor is None else predecessor[0] + 1
        if predecessor is not None:
            previous[current_index] = predecessor[1]
        current_endpoint = (current_length, current_index)
        best_endpoint = _preferred_endpoint(current_endpoint, best_endpoint)

        update_index = current.before_index + 1
        while update_index < len(tree):
            tree[update_index] = _preferred_endpoint(
                current_endpoint,
                tree[update_index],
            )
            update_index += update_index & -update_index

    if best_endpoint is None:
        return set()
    end_index: int | None = best_endpoint[1]
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
    prepared_before = _prepare_elements(before_elements)
    prepared_after = _prepare_elements(after_elements)
    matches = _unique_exact_matches(prepared_before, prepared_after)
    matched_before = {match.before_index for match in matches}
    matched_after = {match.after_index for match in matches}
    matches.extend(
        _contextual_exact_matches(
            prepared_before,
            prepared_after,
            matched_before,
            matched_after,
        )
    )
    matches.extend(
        _similar_matches(
            prepared_before,
            prepared_after,
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

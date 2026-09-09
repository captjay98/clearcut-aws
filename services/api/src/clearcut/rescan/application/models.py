"""Shared frozen DTOs and typed errors for selective-rescan carry-forward.

This module is the shared vocabulary the rescan orchestration layer and the
owning-module adapters exchange across the typed ports. It imports only
standard-library types: no SQLAlchemy, no FastAPI, and no other module's
adapters. Every value that crosses a rescan port boundary is an immutable
dataclass or a typed error defined here; no booleans, ``None`` sentinels, or raw
dictionaries encode outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

# Identifier aliases keep signatures self-documenting without leaking any
# persistence type. They are plain ``UUID`` values at runtime.
OrgId = UUID
ProjectId = UUID
ScriptId = UUID
VersionId = UUID
ElementId = UUID
ItemId = UUID
ClaimId = UUID
SnapshotId = UUID
RunId = UUID
QueryId = UUID
ProviderAttemptId = UUID


class RescanStage(StrEnum):
    """The selective-rescan stages, in workflow order: the initial ``QUEUED``
    state plus the six processed stages the durable processor advances through.

    The values are aligned exactly with the ``selective_rescan_checkpoints``
    stage check constraint so a stage never drifts from the persisted contract.
    """

    QUEUED = "queued"
    MATERIALIZING_LINEAGE = "materializing_lineage"
    CARRYING_EVIDENCE = "carrying_evidence"
    DETECTING_AFFECTED_PASSAGES = "detecting_affected_passages"
    RESEARCHING_AFFECTED_ITEMS = "researching_affected_items"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    COMPLETED = "completed"


class LineageKind(StrEnum):
    """How a successor clearance item is bound to its predecessor.

    ``CARRIED_FORWARD`` items require accountable human confirmation before any
    prior evidence is treated as current; ``RESCANNED`` items are re-detected on
    the after version and require no carry-forward confirmation.
    """

    CARRIED_FORWARD = "carried_forward"
    RESCANNED = "rescanned"


class RescanSafeError(Exception):
    """A typed, safe rescan error crossing a port boundary.

    ``code`` is a stable machine token; ``message`` is human-readable and never
    leaks tenant data; ``retryable`` tells the caller whether a later attempt may
    succeed. A missing tenant/project scope surfaces as this error, never as a
    raw ``None`` or a leaked persistence exception.

    This is a plain (non-frozen) :class:`Exception` on purpose: Python assigns
    ``__traceback__`` on an exception as it unwinds through a context manager's
    ``__aexit__`` (e.g. ``async with session_scope()``). A frozen dataclass
    rejects that assignment with ``FrozenInstanceError``, which would replace the
    typed error and mask it as an opaque failure. It still behaves as a typed
    value: its public attributes and constructor signature are stable, and two
    errors with the same ``code``/``message``/``retryable`` compare equal.
    """

    __slots__ = ()

    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.retryable = retryable

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(code={self.code!r}, "
            f"message={self.message!r}, retryable={self.retryable!r})"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RescanSafeError):
            return NotImplemented
        return (
            self.code == other.code
            and self.message == other.message
            and self.retryable == other.retryable
        )

    def __hash__(self) -> int:
        return hash((type(self), self.code, self.message, self.retryable))


@dataclass(frozen=True)
class CarryableElementPair:
    """One after-version element that is eligible to carry forward.

    Element-level projection sourced purely from the scripts module's adjacent
    diff: an exact/contextual unchanged or moved element. It carries no item,
    category, or evidence identity — the rescan orchestration joins it with the
    predecessor clearance item to build a :class:`CarryableElement`.
    """

    before_element_id: ElementId
    after_element_id: ElementId
    before_text: str
    after_text: str


@dataclass(frozen=True)
class CarryableElement:
    """One after-version element that carries forward from a predecessor item.

    A carryable element is an exact/contextual unchanged or moved element whose
    predecessor version held a clearance item. The rescan orchestration pairs the
    revision plan's carryable elements with the predecessor items so the item
    lineage port can materialize a new, unresolved successor item.
    """

    before_element_id: ElementId
    after_element_id: ElementId
    predecessor_item_id: ItemId
    category: str
    text: str


@dataclass(frozen=True)
class RevisionPlan:
    """A scoped, immutable adjacent-revision plan.

    Sourced from the scripts module's persisted adjacent diff. ``carryable_elements``
    are the exact/contextual unchanged or moved elements eligible for
    carry-forward; ``affected_element_ids`` are the BEFORE-version elements whose
    predecessor items require fresh detection/research (modified);
    ``added_after_element_ids`` are the AFTER-version elements with no predecessor
    that require fresh detection producing brand-new unresolved items;
    ``removed_element_ids`` are before-version elements that stay historical only.
    """

    org_id: OrgId
    project_id: ProjectId
    script_id: ScriptId
    before_version_id: VersionId
    after_version_id: VersionId
    algorithm_version: str
    carryable_elements: tuple[CarryableElementPair, ...]
    affected_element_ids: frozenset[ElementId]
    removed_element_ids: frozenset[ElementId]
    added_after_element_ids: frozenset[ElementId] = frozenset()


@dataclass(frozen=True)
class CarriedItemMapping:
    """The mapping from a predecessor item to its new carried successor item."""

    predecessor_item_id: ItemId
    new_item_id: ItemId
    after_version_id: VersionId
    after_element_id: ElementId


@dataclass(frozen=True)
class RestoredRescanProgress:
    """The replayable outputs of the stages a prior attempt already completed.

    A resumed selective rescan skips the side effects of a stage that already
    succeeded, but the *outputs* of that stage are still the inputs of the next
    one: the carried item mappings feed evidence carry-forward, and the affected
    item ids feed research. Restoring them is what keeps a resumed run correct
    instead of silently running later stages against empty inputs.

    ``unrecoverable_stages`` names any stage recorded as ``succeeded`` whose
    persisted output cannot be restored (for example a checkpoint written before
    outputs were persisted). Such a stage is never silently treated as empty: the
    processor fails the job closed with a typed error so the gap is visible.
    """

    completed_stages: frozenset[RescanStage] = frozenset()
    unrecoverable_stages: frozenset[RescanStage] = frozenset()
    carried_mappings: tuple[CarriedItemMapping, ...] = ()
    carried_evidence_edge_count: int = 0
    affected_item_ids: tuple[ItemId, ...] = ()
    added_item_ids: tuple[ItemId, ...] = ()


# Checkpoint-result keys for the replayable stage outputs. The processor encodes
# them when it records a succeeded stage and the repository adapter decodes them
# on resume, so both sides share one definition of the persisted shape.
CARRIED_MAPPINGS_KEY = "carriedMappings"
CARRIED_EVIDENCE_EDGE_COUNT_KEY = "carriedEvidenceEdgeCount"
AFFECTED_ITEM_IDS_KEY = "affectedItemIds"
ADDED_ITEM_IDS_KEY = "addedItemIds"

_UNRESTORABLE = "unrestorable_rescan_checkpoint"


def _unrestorable(detail: str) -> RescanSafeError:
    return RescanSafeError(
        code=_UNRESTORABLE,
        message=f"A completed selective-rescan stage cannot be restored: {detail}.",
        retryable=False,
    )


def encode_carried_mappings(mappings: tuple[CarriedItemMapping, ...]) -> list[dict[str, str]]:
    """Encode carried item mappings for a stage checkpoint result."""
    return [
        {
            "predecessorItemId": str(mapping.predecessor_item_id),
            "newItemId": str(mapping.new_item_id),
            "afterVersionId": str(mapping.after_version_id),
            "afterElementId": str(mapping.after_element_id),
        }
        for mapping in mappings
    ]


def decode_carried_mappings(raw: object) -> tuple[CarriedItemMapping, ...]:
    """Restore carried item mappings persisted by a completed lineage stage.

    Raises a typed :class:`RescanSafeError` when the persisted output is absent
    or malformed; an empty list is a legitimate result (a revision can have no
    carryable item) and restores to an empty tuple.
    """
    if not isinstance(raw, list):
        raise _unrestorable("carried item mappings are missing")
    mappings: list[CarriedItemMapping] = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise _unrestorable("a carried item mapping is malformed")
        try:
            mappings.append(
                CarriedItemMapping(
                    predecessor_item_id=UUID(str(entry["predecessorItemId"])),
                    new_item_id=UUID(str(entry["newItemId"])),
                    after_version_id=UUID(str(entry["afterVersionId"])),
                    after_element_id=UUID(str(entry["afterElementId"])),
                )
            )
        except (KeyError, ValueError, TypeError) as error:
            raise _unrestorable("a carried item mapping is malformed") from error
    return tuple(mappings)


def encode_item_ids(item_ids: tuple[ItemId, ...]) -> list[str]:
    """Encode an ordered item-id output for a stage checkpoint result."""
    return [str(item_id) for item_id in item_ids]


def decode_item_ids(raw: object, *, detail: str) -> tuple[ItemId, ...]:
    """Restore an ordered item-id output persisted by a completed stage."""
    if not isinstance(raw, list):
        raise _unrestorable(f"{detail} are missing")
    try:
        return tuple(UUID(str(item_id)) for item_id in raw)
    except (ValueError, TypeError) as error:
        raise _unrestorable(f"{detail} are malformed") from error


def decode_edge_count(raw: object) -> int:
    """Restore the carried-evidence edge count of a completed evidence stage."""
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
        raise _unrestorable("the carried evidence edge count is missing")
    return raw


@dataclass(frozen=True)
class CarriedEvidenceProvenance:
    """Read projection of one carried claim's original source provenance.

    Carry-forward never clones snapshot content, alters retrieval time, or
    invents provider identity: every field references the ORIGINAL claim,
    snapshot, run, query, and provider attempt verbatim.
    """

    original_claim_id: ClaimId
    snapshot_id: SnapshotId
    run_id: RunId
    query_id: QueryId
    provider_attempt_id: ProviderAttemptId


@dataclass(frozen=True)
class CarriedEvidenceEdge:
    """One persisted carried-evidence edge for a new item.

    Records the new item and its source item alongside the original claim
    provenance. This is the write-side result of :meth:`carry_forward`; it never
    represents a direct evidence claim for the new item.
    """

    new_item_id: ItemId
    source_item_id: ItemId
    original_claim_id: ClaimId
    snapshot_id: SnapshotId
    run_id: RunId
    query_id: QueryId
    provider_attempt_id: ProviderAttemptId


__all__ = [
    "OrgId",
    "ProjectId",
    "ScriptId",
    "VersionId",
    "ElementId",
    "ItemId",
    "ClaimId",
    "SnapshotId",
    "RunId",
    "QueryId",
    "ProviderAttemptId",
    "RescanStage",
    "LineageKind",
    "RescanSafeError",
    "CarryableElement",
    "CarryableElementPair",
    "RevisionPlan",
    "CarriedItemMapping",
    "CarriedEvidenceProvenance",
    "CarriedEvidenceEdge",
    "RestoredRescanProgress",
    "CARRIED_MAPPINGS_KEY",
    "CARRIED_EVIDENCE_EDGE_COUNT_KEY",
    "AFFECTED_ITEM_IDS_KEY",
    "ADDED_ITEM_IDS_KEY",
    "encode_carried_mappings",
    "decode_carried_mappings",
    "encode_item_ids",
    "decode_item_ids",
    "decode_edge_count",
]

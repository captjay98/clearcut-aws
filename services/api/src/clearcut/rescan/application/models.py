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
    """The seven approved selective-rescan stages, in workflow order.

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


@dataclass(frozen=True)
class RescanSafeError(Exception):
    """A typed, safe rescan error crossing a port boundary.

    ``code`` is a stable machine token; ``message`` is human-readable and never
    leaks tenant data; ``retryable`` tells the caller whether a later attempt may
    succeed. A missing tenant/project scope surfaces as this error, never as a
    raw ``None`` or a leaked persistence exception.
    """

    code: str
    message: str
    retryable: bool = False

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


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
]

"""Typed port for materializing and reading carried clearance-item lineage.

The detection module owns clearance-item storage and implements this port. It
creates a NEW clearance item for each carryable element, bound to the after
version/element with a predecessor edge, ``carried_forward`` lineage, and a
status that requires accountable human confirmation before any prior evidence is
treated as current. Modified/added elements receive no carried item and removed
elements stay historical only. Materialization is replay-idempotent: a repeat
returns the same predecessor-to-successor mapping without duplicate rows.
"""

from __future__ import annotations

from typing import Protocol

from clearcut.rescan.application.models import (
    CarriedItemMapping,
    CarryableElement,
    ItemId,
    OrgId,
    ProjectId,
    ScriptId,
    VersionId,
)


class ItemLineagePort(Protocol):
    """Materializes carried successor items and lists affected predecessors."""

    async def materialize_carried_items(
        self,
        *,
        org_id: OrgId,
        project_id: ProjectId,
        script_id: ScriptId,
        before_version_id: VersionId,
        after_version_id: VersionId,
        carryable_elements: tuple[CarryableElement, ...],
    ) -> tuple[CarriedItemMapping, ...]:
        """Create carried successor items for the carryable elements.

        Each new item is bound to the after version/element with a
        ``carried_forward`` predecessor edge and a status requiring human
        confirmation, with no assignee, disposition, decision, or detection
        provenance. Prior human decisions are never copied — they remain visible
        only on the predecessor item. The operation is idempotent on replay:
        repeating it returns the same mapping and writes no duplicate rows.
        Raises :class:`~clearcut.rescan.application.models.RescanSafeError` on a
        scope violation.
        """
        ...

    async def list_affected_items(
        self,
        *,
        org_id: OrgId,
        project_id: ProjectId,
        before_version_id: VersionId,
        affected_element_ids: tuple[ItemId, ...],
    ) -> tuple[ItemId, ...]:
        """List predecessor items whose elements were modified/removed.

        These items back affected passages that require fresh detection or
        research on the after version; they are never carried forward. Scope is
        enforced before any access.
        """
        ...


__all__ = ["ItemLineagePort"]

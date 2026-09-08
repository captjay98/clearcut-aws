"""Detection application service coordinating carried item materialization.

This service is the detection module's entry point for the rescan carry-forward
workflow. It owns no storage of its own; it delegates the write to the
detection-owned :class:`ItemLineagePort` adapter, which creates the new,
unresolved, confirmation-required successor items. Keeping this seam as a service
mirrors the module's other application services (e.g. ``RunDetectionJobService``)
and lets the rescan orchestration depend on a typed port rather than a concrete
adapter.
"""

from __future__ import annotations

from clearcut.rescan.application.models import (
    CarriedItemMapping,
    CarryableElement,
    OrgId,
    ProjectId,
    ScriptId,
    VersionId,
)
from clearcut.rescan.ports.item_lineage import ItemLineagePort


class MaterializeItemLineageService:
    """Materializes carried successor items through the typed lineage port."""

    def __init__(self, lineage: ItemLineagePort) -> None:
        self._lineage = lineage

    async def materialize(
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

        The write is idempotent on replay and never copies prior human
        decisions; those stay bound to the predecessor item. Modified/added
        elements are excluded by the caller (they are not carryable), and removed
        elements stay historical only.
        """
        return await self._lineage.materialize_carried_items(
            org_id=org_id,
            project_id=project_id,
            script_id=script_id,
            before_version_id=before_version_id,
            after_version_id=after_version_id,
            carryable_elements=carryable_elements,
        )


__all__ = ["MaterializeItemLineageService"]

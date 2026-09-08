"""Research application service coordinating evidence carry-forward.

This service is the research module's entry point for the rescan carry-forward
workflow. It owns no storage; it delegates to the research-owned
:class:`EvidenceLineagePort` adapter, which inserts carried-evidence edges that
reference the original claim provenance and never a direct evidence claim for the
new item. Zero source claims carry zero evidence, keeping the new item
unresolved.
"""

from __future__ import annotations

from clearcut.rescan.application.models import (
    CarriedEvidenceEdge,
    ItemId,
    OrgId,
    ProjectId,
)
from clearcut.rescan.ports.evidence_lineage import EvidenceLineagePort


class CarryForwardEvidenceService:
    """Carries a predecessor item's evidence forward through the typed port."""

    def __init__(self, evidence_lineage: EvidenceLineagePort) -> None:
        self._evidence_lineage = evidence_lineage

    async def carry_forward(
        self,
        *,
        org_id: OrgId,
        project_id: ProjectId,
        new_item_id: ItemId,
        source_item_id: ItemId,
    ) -> tuple[CarriedEvidenceEdge, ...]:
        """Carry every fully provenanced source claim to the new item.

        The carried edges reference the original claim/snapshot/run/query/
        provider-attempt provenance. Because no direct evidence claim is written
        for the new item, the governed accept/verify gate stays blocked until a
        future confirmation records direct evidence. Idempotent on replay.
        """
        return await self._evidence_lineage.carry_forward(
            org_id=org_id,
            project_id=project_id,
            new_item_id=new_item_id,
            source_item_id=source_item_id,
        )


__all__ = ["CarryForwardEvidenceService"]

"""Typed port for carrying evidence lineage forward to a new item.

The research module owns evidence storage and implements this port. For each
carried item, it inserts one carried-evidence edge per predecessor source claim
that references the ORIGINAL claim, snapshot, run, query, and provider-attempt
provenance. It never clones snapshot content, alters retrieval time, invents
query/provider identity, or inserts a direct evidence claim for the new item.
When the predecessor has zero source claims, zero edges are carried and the new
item stays unresolved. Carry-forward is replay-idempotent per new-item/source
claim.
"""

from __future__ import annotations

from typing import Protocol

from clearcut.rescan.application.models import (
    CarriedEvidenceEdge,
    CarriedEvidenceProvenance,
    ItemId,
    OrgId,
    ProjectId,
)


class EvidenceLineagePort(Protocol):
    """Carries evidence lineage forward and reads carried provenance."""

    async def carry_forward(
        self,
        *,
        org_id: OrgId,
        project_id: ProjectId,
        new_item_id: ItemId,
        source_item_id: ItemId,
    ) -> tuple[CarriedEvidenceEdge, ...]:
        """Carry every source claim of ``source_item_id`` to ``new_item_id``.

        Inserts one carried-evidence edge per original source claim, referencing
        the original claim/snapshot/run/query/provider-attempt provenance and
        never a direct evidence claim for the new item. Zero source claims carry
        zero edges. The write is idempotent per new-item/source-claim pair, so a
        replay writes no duplicate rows. Raises
        :class:`~clearcut.rescan.application.models.RescanSafeError` on a scope
        violation.
        """
        ...

    async def list_carried_provenance(
        self,
        *,
        org_id: OrgId,
        project_id: ProjectId,
        new_item_id: ItemId,
    ) -> tuple[CarriedEvidenceProvenance, ...]:
        """Return the carried source claim/snapshot provenance for a new item.

        Each entry preserves the original claim, snapshot, run, query, and
        provider-attempt identity verbatim. Scope is enforced before any access.
        """
        ...


__all__ = ["EvidenceLineagePort"]

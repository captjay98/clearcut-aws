"""Research-owned adapter that carries evidence lineage to a new item.

The research module is the sole owner of evidence storage. This adapter
implements the rescan :class:`EvidenceLineagePort` by inserting one
``evidence_carry_forwards`` row per predecessor source claim, referencing the
ORIGINAL claim, snapshot, run, query, and provider-attempt provenance.

Governance invariants enforced here:

* carried evidence is never written as a direct ``evidence_claims`` row for the
  new item, so the new item's direct cited-claim count stays zero and the
  governed accept/verify gate remains blocked until a future confirmation;
* snapshot content and retrieval time are never cloned or altered, and no
  query/provider identity is invented — the carried row references the original
  provenance tuple verbatim through a composite foreign key;
* a predecessor with zero source claims carries zero edges (the new item stays
  unresolved);
* the write is idempotent per new-item/source-claim pair via the carry-forward
  unique constraint;
* tenant/project scope is applied to every read and write.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
import uuid6
from clearcut.database import session_scope
from clearcut.rescan.application.models import (
    CarriedEvidenceEdge,
    CarriedEvidenceProvenance,
    ItemId,
    OrgId,
    ProjectId,
    RescanSafeError,
)
from clearcut.rescan.ports.evidence_lineage import EvidenceLineagePort
from sqlalchemy.exc import IntegrityError


class SqlEvidenceLineageAdapter(EvidenceLineagePort):
    """Carries source-claim provenance forward in the research-owned storage."""

    async def carry_forward(
        self,
        *,
        org_id: OrgId,
        project_id: ProjectId,
        new_item_id: ItemId,
        source_item_id: ItemId,
    ) -> tuple[CarriedEvidenceEdge, ...]:
        now = datetime.now(UTC)
        try:
            async with session_scope() as session:
                # Only fully provenanced source claims can be carried: the
                # carry-forward foreign key binds the original claim's full
                # provenance tuple, so a claim missing run/query/provider
                # identity is not eligible. Scope is applied to the read.
                claims = (
                    (
                        await session.execute(
                            sa.text(
                                "SELECT id, snapshot_id, run_id, query_id, provider_attempt_id "
                                "FROM evidence_claims "
                                "WHERE org_id = :org_id AND project_id = :project_id "
                                "AND item_id = :source_item_id "
                                "AND run_id IS NOT NULL AND query_id IS NOT NULL "
                                "AND provider_attempt_id IS NOT NULL "
                                "ORDER BY created_at, id"
                            ),
                            {
                                "org_id": str(org_id),
                                "project_id": str(project_id),
                                "source_item_id": str(source_item_id),
                            },
                        )
                    )
                    .mappings()
                    .all()
                )
                if not claims:
                    return ()

                edges: list[CarriedEvidenceEdge] = []
                for claim in claims:
                    original_claim_id = UUID(str(claim["id"]))
                    snapshot_id = UUID(str(claim["snapshot_id"]))
                    run_id = UUID(str(claim["run_id"]))
                    query_id = UUID(str(claim["query_id"]))
                    provider_attempt_id = UUID(str(claim["provider_attempt_id"]))
                    await session.execute(
                        sa.text(
                            """
                            INSERT INTO evidence_carry_forwards (
                                id, org_id, project_id, new_item_id, source_item_id,
                                original_claim_id, snapshot_id, run_id, query_id,
                                provider_attempt_id, created_at
                            ) VALUES (
                                :id, :org_id, :project_id, :new_item_id, :source_item_id,
                                :original_claim_id, :snapshot_id, :run_id, :query_id,
                                :provider_attempt_id, :created_at
                            )
                            ON CONFLICT (org_id, project_id, new_item_id, original_claim_id)
                            DO NOTHING
                            """
                        ),
                        {
                            "id": str(uuid6.uuid7()),
                            "org_id": str(org_id),
                            "project_id": str(project_id),
                            "new_item_id": str(new_item_id),
                            "source_item_id": str(source_item_id),
                            "original_claim_id": str(original_claim_id),
                            "snapshot_id": str(snapshot_id),
                            "run_id": str(run_id),
                            "query_id": str(query_id),
                            "provider_attempt_id": str(provider_attempt_id),
                            "created_at": now,
                        },
                    )
                    edges.append(
                        CarriedEvidenceEdge(
                            new_item_id=new_item_id,
                            source_item_id=source_item_id,
                            original_claim_id=original_claim_id,
                            snapshot_id=snapshot_id,
                            run_id=run_id,
                            query_id=query_id,
                            provider_attempt_id=provider_attempt_id,
                        )
                    )
        except IntegrityError as error:
            raise RescanSafeError(
                code="carry_forward_conflict",
                message="Carried evidence conflicts with scoped item or claim provenance.",
                retryable=False,
            ) from error
        return tuple(edges)

    async def list_carried_provenance(
        self,
        *,
        org_id: OrgId,
        project_id: ProjectId,
        new_item_id: ItemId,
    ) -> tuple[CarriedEvidenceProvenance, ...]:
        async with session_scope() as session:
            rows = (
                (
                    await session.execute(
                        sa.text(
                            "SELECT original_claim_id, snapshot_id, run_id, query_id, "
                            "provider_attempt_id FROM evidence_carry_forwards "
                            "WHERE org_id = :org_id AND project_id = :project_id "
                            "AND new_item_id = :new_item_id "
                            "ORDER BY created_at, id"
                        ),
                        {
                            "org_id": str(org_id),
                            "project_id": str(project_id),
                            "new_item_id": str(new_item_id),
                        },
                    )
                )
                .mappings()
                .all()
            )
        return tuple(
            CarriedEvidenceProvenance(
                original_claim_id=UUID(str(row["original_claim_id"])),
                snapshot_id=UUID(str(row["snapshot_id"])),
                run_id=UUID(str(row["run_id"])),
                query_id=UUID(str(row["query_id"])),
                provider_attempt_id=UUID(str(row["provider_attempt_id"])),
            )
            for row in rows
        )


__all__ = ["SqlEvidenceLineageAdapter"]

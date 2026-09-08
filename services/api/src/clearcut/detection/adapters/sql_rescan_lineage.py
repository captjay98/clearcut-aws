"""Detection-owned adapter that materializes carried clearance-item lineage.

The detection module is the sole owner of ``clearance_items`` storage. This
adapter implements the rescan :class:`ItemLineagePort` by creating a NEW
clearance item for each carryable element, bound to the after version/element
with a ``carried_forward`` predecessor edge and a status that requires
accountable human confirmation before any prior evidence is treated as current.

Governance invariants enforced here:

* the new item carries no assignee, disposition, decision, or detection
  provenance (detection candidate/run/fingerprint are all null), satisfying the
  ``ck_clearance_items_detection_candidate_binding`` and lineage-state checks;
* prior human decisions are never copied — governed decision records stay bound
  to the predecessor item only;
* materialization is replay-idempotent via the successor-projection unique
  constraint, so a repeat returns the same mapping and writes no duplicate rows;
* tenant/project scope is verified against the predecessor item before any
  write, and an out-of-scope predecessor raises a typed
  :class:`~clearcut.rescan.application.models.RescanSafeError`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
import uuid6
from clearcut.database import session_scope
from clearcut.rescan.application.models import (
    CarriedItemMapping,
    CarryableElement,
    ItemId,
    LineageKind,
    OrgId,
    ProjectId,
    RescanSafeError,
    ScriptId,
    VersionId,
)
from clearcut.rescan.ports.item_lineage import ItemLineagePort
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

_CARRIED_STATUS = "unresolved"
_CARRIED_WORKFLOW_STATUS = "open"
_CARRIED_RESEARCH_STATUS = "not_started"
_CARRIED_DISPOSITION_STATUS = "undisposed"


class SqlItemLineageAdapter(ItemLineagePort):
    """Creates carried successor items in the detection-owned storage."""

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
        if not carryable_elements:
            return ()
        now = datetime.now(UTC)
        mappings: list[CarriedItemMapping] = []
        try:
            async with session_scope() as session:
                for element in carryable_elements:
                    predecessor = await self._require_scoped_predecessor(
                        session,
                        org_id=org_id,
                        project_id=project_id,
                        script_id=script_id,
                        predecessor_item_id=element.predecessor_item_id,
                        before_version_id=before_version_id,
                    )
                    new_item_id = await self._insert_carried_item(
                        session,
                        org_id=org_id,
                        project_id=project_id,
                        script_id=script_id,
                        after_version_id=after_version_id,
                        after_element_id=element.after_element_id,
                        predecessor_item_id=element.predecessor_item_id,
                        predecessor_version_id=before_version_id,
                        category=predecessor["category"],
                        text=predecessor["text"],
                        created_at=now,
                    )
                    mappings.append(
                        CarriedItemMapping(
                            predecessor_item_id=element.predecessor_item_id,
                            new_item_id=new_item_id,
                            after_version_id=after_version_id,
                            after_element_id=element.after_element_id,
                        )
                    )
        except IntegrityError as error:
            raise RescanSafeError(
                code="carried_item_conflict",
                message="Carried item projection conflicts with scoped item lineage.",
                retryable=False,
            ) from error
        return tuple(mappings)

    async def list_affected_items(
        self,
        *,
        org_id: OrgId,
        project_id: ProjectId,
        before_version_id: VersionId,
        affected_element_ids: tuple[ItemId, ...],
    ) -> tuple[ItemId, ...]:
        if not affected_element_ids:
            return ()
        async with session_scope() as session:
            rows = (
                await session.execute(
                    sa.text(
                        "SELECT id FROM clearance_items "
                        "WHERE org_id = :org_id AND project_id = :project_id "
                        "AND version_id = :version_id "
                        "AND element_id IN :element_ids "
                        "ORDER BY created_at, id"
                    ).bindparams(sa.bindparam("element_ids", expanding=True)),
                    {
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                        "version_id": str(before_version_id),
                        "element_ids": [str(element_id) for element_id in affected_element_ids],
                    },
                )
            ).scalars()
            return tuple(UUID(str(item_id)) for item_id in rows)

    async def _require_scoped_predecessor(
        self,
        session: AsyncSession,
        *,
        org_id: OrgId,
        project_id: ProjectId,
        script_id: ScriptId,
        predecessor_item_id: ItemId,
        before_version_id: VersionId,
    ) -> sa.RowMapping:
        # Scope is enforced before any write: the predecessor item must exist in
        # the authenticated org/project/script scope and be bound to the before
        # version, which is the predecessor edge target the lineage FK requires.
        row = (
            (
                await session.execute(
                    sa.text(
                        "SELECT category, text FROM clearance_items "
                        "WHERE id = :item_id AND org_id = :org_id AND project_id = :project_id "
                        "AND script_id = :script_id AND version_id = :version_id"
                    ),
                    {
                        "item_id": str(predecessor_item_id),
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                        "script_id": str(script_id),
                        "version_id": str(before_version_id),
                    },
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise RescanSafeError(
                code="predecessor_item_not_found",
                message="The predecessor clearance item is not visible in the requested scope.",
                retryable=False,
            )
        return row

    async def _insert_carried_item(
        self,
        session: AsyncSession,
        *,
        org_id: OrgId,
        project_id: ProjectId,
        script_id: ScriptId,
        after_version_id: VersionId,
        after_element_id: ItemId,
        predecessor_item_id: ItemId,
        predecessor_version_id: VersionId,
        category: str,
        text: str,
        created_at: datetime,
    ) -> ItemId:
        new_item_id = uuid6.uuid7()
        # A carried item is bound to the after version/element with a
        # ``carried_forward`` predecessor edge that names both the predecessor
        # item and its before version, satisfying ``ck_clearance_items_lineage_state``.
        # It has no assignee, disposition, decision, or detection provenance
        # (candidate/run/fingerprint all null), and its confirmation flag is true
        # so a governed human step must confirm before prior evidence is treated
        # as current. The insert is idempotent on the successor-projection unique
        # constraint.
        await session.execute(
            sa.text(
                """
                INSERT INTO clearance_items (
                    id, org_id, project_id, script_id, version_id, element_id,
                    category, text, status, research_status, workflow_status,
                    disposition_status, created_at, version,
                    predecessor_item_id, predecessor_version_id, lineage_kind,
                    carried_forward_confirmation_required
                ) VALUES (
                    :id, :org_id, :project_id, :script_id, :version_id, :element_id,
                    :category, :text, :status, :research_status, :workflow_status,
                    :disposition_status, :created_at, 1,
                    :predecessor_item_id, :predecessor_version_id, :lineage_kind,
                    :confirmation_required
                )
                ON CONFLICT (org_id, project_id, predecessor_item_id, version_id)
                DO NOTHING
                """
            ),
            {
                "id": str(new_item_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "script_id": str(script_id),
                "version_id": str(after_version_id),
                "element_id": str(after_element_id),
                "category": category,
                "text": text,
                "status": _CARRIED_STATUS,
                "research_status": _CARRIED_RESEARCH_STATUS,
                "workflow_status": _CARRIED_WORKFLOW_STATUS,
                "disposition_status": _CARRIED_DISPOSITION_STATUS,
                "created_at": created_at,
                "predecessor_item_id": str(predecessor_item_id),
                "predecessor_version_id": str(predecessor_version_id),
                "lineage_kind": LineageKind.CARRIED_FORWARD.value,
                "confirmation_required": True,
            },
        )
        # Re-read the canonical successor id so a replay returns the same mapping
        # rather than the freshly generated (and discarded) id.
        existing = (
            await session.execute(
                sa.text(
                    "SELECT id FROM clearance_items "
                    "WHERE org_id = :org_id AND project_id = :project_id "
                    "AND predecessor_item_id = :predecessor_item_id "
                    "AND version_id = :version_id"
                ),
                {
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                    "predecessor_item_id": str(predecessor_item_id),
                    "version_id": str(after_version_id),
                },
            )
        ).scalar_one()
        return UUID(str(existing))


__all__ = ["SqlItemLineageAdapter"]

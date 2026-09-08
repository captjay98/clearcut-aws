"""Scripts-owned adapter that projects a scoped adjacent-revision plan.

The scripts module is the sole owner of screenplay version and diff storage. This
adapter implements the rescan :class:`RevisionPlanPort` by reusing the module's
own persisted adjacent diff (``get_adjacent_diff``); no other module reads the
scripts tables. Tenant/project scope is enforced by the underlying repository
query, and an out-of-scope or missing revision surfaces as a typed
:class:`~clearcut.rescan.application.models.RescanSafeError`, never a raw ``None``.
"""

from __future__ import annotations

from clearcut.rescan.application.models import (
    CarryableElementPair,
    OrgId,
    ProjectId,
    RescanSafeError,
    RevisionPlan,
    VersionId,
)
from clearcut.rescan.ports.revision_plan import RevisionPlanPort
from clearcut.scripts.adapters.sql_import_repository import SqlImportRepository

# Element classifications eligible to carry forward, matching the persisted
# ``script_element_lineage`` vocabulary. An unchanged or moved element is
# carryable only when its lineage confidence is exact or contextual; a similar
# (fuzzy) match is treated as modified and re-detected instead.
_CARRYABLE_CHANGE_KINDS = frozenset({"unchanged", "moved"})
_CARRYABLE_CONFIDENCES = frozenset({"exact", "contextual"})
# Affected elements require fresh detection on the after version.
_AFFECTED_CHANGE_KINDS = frozenset({"modified", "added"})


class SqlRevisionPlanAdapter(RevisionPlanPort):
    """Reads the scoped adjacent-revision plan from the scripts repository."""

    def __init__(self, repository: SqlImportRepository) -> None:
        self._repository = repository

    async def load_revision_plan(
        self,
        *,
        org_id: OrgId,
        project_id: ProjectId,
        after_version_id: VersionId,
    ) -> RevisionPlan:
        record = await self._repository.get_adjacent_diff(
            org_id,
            project_id,
            after_version_id,
        )
        if record is None:
            # Absence and cross-tenant access present the same neutral typed
            # failure: the caller never learns whether the revision exists in
            # another scope.
            raise RescanSafeError(
                code="revision_plan_not_found",
                message="No adjacent revision plan is visible in the requested scope.",
                retryable=False,
            )

        carryable: list[CarryableElementPair] = []
        affected: set = set()
        removed: set = set()
        for change in record.changes:
            change_kind = change.change_kind
            if (
                change_kind in _CARRYABLE_CHANGE_KINDS
                and change.confidence in _CARRYABLE_CONFIDENCES
                and change.before_element_id is not None
                and change.after_element_id is not None
            ):
                carryable.append(
                    CarryableElementPair(
                        before_element_id=change.before_element_id,
                        after_element_id=change.after_element_id,
                        before_text=change.before_text or "",
                        after_text=change.after_text or "",
                    )
                )
            elif change_kind in _AFFECTED_CHANGE_KINDS and change.after_element_id is not None:
                affected.add(change.after_element_id)
            elif change_kind == "removed" and change.before_element_id is not None:
                removed.add(change.before_element_id)

        return RevisionPlan(
            org_id=org_id,
            project_id=project_id,
            script_id=record.script_id,
            before_version_id=record.before_version_id,
            after_version_id=record.after_version_id,
            algorithm_version=record.algorithm_version,
            carryable_elements=tuple(carryable),
            affected_element_ids=frozenset(affected),
            removed_element_ids=frozenset(removed),
        )


__all__ = ["SqlRevisionPlanAdapter"]

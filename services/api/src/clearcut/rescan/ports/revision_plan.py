"""Typed port for reading a scoped, immutable adjacent-revision plan.

The revision plan is sourced from the scripts module, which is the sole owner of
version and diff storage. Other modules never read scripts tables; they read the
plan through this port. Implementations must enforce tenant/project scope before
any data access and raise a typed
:class:`~clearcut.rescan.application.models.RescanSafeError` when the revision is
not visible in the authenticated scope, never a raw ``None``.
"""

from __future__ import annotations

from typing import Protocol

from clearcut.rescan.application.models import (
    OrgId,
    ProjectId,
    RevisionPlan,
    VersionId,
)


class RevisionPlanPort(Protocol):
    """Reads the scoped adjacent-revision plan for an after version."""

    async def load_revision_plan(
        self,
        *,
        org_id: OrgId,
        project_id: ProjectId,
        after_version_id: VersionId,
    ) -> RevisionPlan:
        """Return the scoped revision plan for ``after_version_id``.

        Raises :class:`~clearcut.rescan.application.models.RescanSafeError` when
        no adjacent diff is visible in the authenticated organization-and-project
        scope, so absence and cross-tenant access present the same neutral typed
        failure rather than a leaked persistence detail.
        """
        ...


__all__ = ["RevisionPlanPort"]

"""Accountable durable selective-rescan start.

:class:`StartSelectiveRescanService` turns an accountable, already-scoped request
into exactly one durable ``selective_rescan`` job plus its immutable start audit,
committed together by the job repository. It never accepts a client-supplied item
scope: the durable payload is the server-derived after-version target only.

Ordering of checks (each a typed outcome, never a raw ``None`` or leaked
persistence error):

1. the adjacent revision plan must be visible in the authenticated scope
   (absence or cross-tenant access is a neutral not-found);
2. the paid provider must be enabled — checked WITHOUT calling any provider;
3. an active organization policy must exist;
4. the job is enqueued under the idempotency key ``selective_rescan:{after_version_id}``.

Dispatch is the caller's responsibility and must happen only when the enqueue
newly created the job and only after the enqueue transaction commits, so a
dispatch failure leaves a durable queued job for reconciliation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol
from uuid import UUID

from clearcut.operations.ports.job_repository import EnqueueJob, EnqueueResult
from clearcut.rescan.application.models import RescanSafeError
from clearcut.rescan.ports.revision_plan import RevisionPlanPort


class StartRescanRejection(Enum):
    """Typed reasons an accountable start request is refused before enqueue."""

    REVISION_PLAN_NOT_FOUND = "revision_plan_not_found"
    PROVIDER_DISABLED = "provider_disabled"
    POLICY_INACTIVE = "policy_inactive"


@dataclass(frozen=True)
class StartRescanRejected:
    """A refused start request carrying a typed, safe reason."""

    reason: StartRescanRejection
    message: str


@dataclass(frozen=True)
class StartRescanAccepted:
    """An accepted start request with its durable enqueue result."""

    enqueue: EnqueueResult


class _ProviderGate(Protocol):
    """Minimal structural type for the paid-provider enablement check."""

    def is_enabled(self, provider: str) -> bool: ...


class _ActivePolicyGate(Protocol):
    """Minimal structural type for the active-policy check.

    The SQL implementation lives in the composition root; the application layer
    stays free of persistence imports and reads policy through this port.
    """

    async def is_active(self, org_id: UUID) -> bool: ...


class StartSelectiveRescanService:
    """Starts a durable selective rescan for an accountable, scoped request."""

    _RESEARCH_PROVIDER = "parallel"

    def __init__(
        self,
        *,
        revision_plan: RevisionPlanPort,
        provider_gate: _ProviderGate,
        active_policy: _ActivePolicyGate,
        job_repository,
    ) -> None:
        self._revision_plan = revision_plan
        self._provider_gate = provider_gate
        self._active_policy = active_policy
        self._job_repository = job_repository

    async def start(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        actor_id: UUID,
        after_version_id: UUID,
    ) -> StartRescanAccepted | StartRescanRejected:
        # 1. The adjacent revision plan must be visible in the requested scope.
        try:
            await self._revision_plan.load_revision_plan(
                org_id=org_id,
                project_id=project_id,
                after_version_id=after_version_id,
            )
        except RescanSafeError as error:
            return StartRescanRejected(
                reason=StartRescanRejection.REVISION_PLAN_NOT_FOUND,
                message=error.message,
            )

        # 2. The paid research provider must be enabled — never call a provider.
        if not self._provider_gate.is_enabled(self._RESEARCH_PROVIDER):
            return StartRescanRejected(
                reason=StartRescanRejection.PROVIDER_DISABLED,
                message="Selective rescan research capability is not currently available.",
            )

        # 3. An active organization policy must govern the rescan.
        if not await self._active_policy.is_active(org_id):
            return StartRescanRejected(
                reason=StartRescanRejection.POLICY_INACTIVE,
                message="An active organization policy is required to start a selective rescan.",
            )

        # 4. Enqueue exactly one durable job under the version idempotency key.
        enqueue = await self._job_repository.enqueue(
            EnqueueJob(
                org_id=org_id,
                project_id=project_id,
                actor_id=actor_id,
                job_type="selective_rescan",
                idempotency_key=f"selective_rescan:{after_version_id}",
                payload={
                    "schemaVersion": 1,
                    "target": {"type": "script_version", "id": str(after_version_id)},
                },
                audit_action="selective_rescan.started",
                target_type="script_version",
                target_id=after_version_id,
            )
        )
        return StartRescanAccepted(enqueue=enqueue)


__all__ = [
    "StartSelectiveRescanService",
    "StartRescanAccepted",
    "StartRescanRejected",
    "StartRescanRejection",
]

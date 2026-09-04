"""Typed persistence port for the governed evidence-decision slice.

The port is the single boundary the application service uses to load the exact
scoped clearance item, count its cited evidence claims, and commit the decision
together with the item version advance. Every value that crosses the boundary is
a typed dataclass or a typed error from the governed-command kernel; no booleans,
``None`` sentinels, or raw rows encode outcomes. A clearance item that is not
visible in the authenticated organization-and-project scope surfaces as a typed
:class:`~clearcut.commanding.errors.CommandNotFoundError`, never a raw ``None``.

Implementations run every statement inside the caller's unit of work so the
decision record, the item version/status advance, the idempotency receipt, and
the authoritative audit event all commit or roll back atomically.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from clearcut.commanding.domain import CommandEnvelope, PriorReceipt
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class ScopedItem:
    """A clearance item resolved within an exact tenant-and-project scope.

    ``version`` is the current optimistic-concurrency version used to guard the
    decision write. ``cited_claim_count`` is the number of evidence claims that
    are cited within the same organization-and-project scope, used to enforce the
    zero-evidence protection for clearance-like outcomes.
    """

    item_id: UUID
    org_id: UUID
    project_id: UUID
    version_id: UUID | None
    category: str
    entity_name: str
    status: str
    disposition_status: str | None
    assigned_to_user_id: UUID | None
    context_text: str | None
    version: int
    cited_claim_count: int


@dataclass(frozen=True)
class PersistedDecision:
    """The committed decision plus the item's resulting projection.

    The service maps this typed result onto the canonical ``ClearanceItem``
    response; the delivery layer never re-reads storage to build the response.
    """

    decision_id: UUID
    item_id: UUID
    org_id: UUID
    project_id: UUID
    version_id: UUID | None
    category: str
    entity_name: str
    status: str
    disposition_status: str | None
    assigned_to_user_id: UUID | None
    context_text: str | None
    resulting_version: int
    cited_claim_count: int


class DecisionRepositoryPort(Protocol):
    """Session-bound persistence operations for governed evidence decisions."""

    async def load_scoped_item(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
    ) -> ScopedItem:
        """Load the exact scoped item with its version and cited-claim count.

        Raises :class:`~clearcut.commanding.errors.CommandNotFoundError` when the
        item is not visible in the authenticated organization-and-project scope,
        presenting the same neutral shape whether the item is absent or belongs
        to another tenant.
        """
        ...

    async def commit_decision(
        self,
        session: AsyncSession,
        *,
        decision_id: UUID,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        actor_id: UUID,
        decision_value: str,
        rationale: str,
        expected_version: int,
        resulting_version: int,
        next_status: str,
        occurred_at: datetime,
    ) -> None:
        """Insert the immutable decision and advance the item version/status.

        The item update is a version-guarded compare-and-swap on
        ``expected_version``; the caller has already classified the command as a
        fresh write at that version. All statements run inside the caller's
        transaction. A zero-row compare-and-swap means the row moved
        concurrently and is classified exactly as :meth:`classify_cas_miss`
        documents (still-present item -> stale-version 409; absent/foreign item
        -> neutral not-found 404).
        """
        ...

    async def commit_disposition(
        self,
        session: AsyncSession,
        *,
        decision_id: UUID,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        actor_id: UUID,
        disposition_value: str,
        rationale: str,
        expected_version: int,
        resulting_version: int,
        occurred_at: datetime,
    ) -> None:
        """Insert the immutable disposition record and advance the item.

        Records a ``decision_kind = 'disposition'`` row and advances the item's
        ``version`` and ``disposition_status`` with a single version-guarded
        compare-and-swap on ``expected_version``. A disposition is a workflow
        signal only: the item's clearance ``status`` is never mutated, so the
        write can never assert a legal conclusion. All statements run inside the
        caller's transaction. A zero-row compare-and-swap means the row moved
        concurrently and is classified exactly as :meth:`classify_cas_miss`
        documents (still-present item -> stale-version 409; absent/foreign item
        -> neutral not-found 404).
        """
        ...

    async def classify_cas_miss(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
    ) -> None:
        """Classify a version-guarded compare-and-swap miss by scoped existence.

        Never returns normally: raises
        :class:`~clearcut.commanding.errors.StaleVersionConflictError` when the
        item is still present in scope (its version advanced concurrently) and
        :class:`~clearcut.commanding.errors.CommandNotFoundError` when it is
        absent or foreign, so a concurrent version change is a 409 while genuine
        not-found stays a neutral 404.
        """
        ...

    async def persist_receipt_idempotent(
        self,
        session: AsyncSession,
        envelope: CommandEnvelope,
        *,
        item_id: UUID,
        resulting_version: int,
        result_id: UUID,
        occurred_at: datetime,
    ) -> PriorReceipt | None:
        """Persist the idempotency receipt, reconciling a concurrent duplicate.

        Returns ``None`` when the fresh receipt was persisted, or the typed
        prior :class:`~clearcut.commanding.domain.PriorReceipt` when a concurrent
        writer already committed the receipt for this exact scope — following the
        kernel's documented caller re-read contract so the losing race replays
        the original idempotent result rather than surfacing a raw integrity
        error. Runs inside the caller's transaction using a savepoint so a losing
        race does not poison the outer unit of work.
        """
        ...


__all__ = [
    "ScopedItem",
    "PersistedDecision",
    "DecisionRepositoryPort",
]

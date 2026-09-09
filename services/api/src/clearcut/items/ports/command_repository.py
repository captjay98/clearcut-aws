"""Typed persistence port for the governed clearance-item assignment slice.

The port is the single boundary the assignment application service uses to load
the exact scoped clearance item, confirm the proposed assignee is an active
authorized member of the same scope, and commit the assignment together with
the item version advance. Every value that crosses the boundary is a typed
dataclass or a typed error from the governed-command kernel; no booleans,
``None`` sentinels, or raw rows encode outcomes. A clearance item that is not
visible in the authenticated organization-and-project scope surfaces as a typed
:class:`~clearcut.commanding.errors.CommandNotFoundError`, never a raw ``None``,
and so does a proposed assignee that is not an active member of the scope — so a
caller can never probe for the existence of a foreign or inactive user through a
distinguishing response.

Implementations run every statement inside the caller's unit of work so the
item version advance, the idempotency receipt, and the authoritative audit event
all commit or roll back atomically.
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
    assignment write. The remaining fields are the projection the service maps
    onto the canonical ``ClearanceItem`` response without re-reading storage.
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
class PersistedAssignment:
    """The committed assignment plus the item's resulting projection.

    ``assigned_to_user_id`` is the resulting assignee (``None`` for an
    unassignment). The service maps this typed result onto the canonical
    ``ClearanceItem`` response; the delivery layer never re-reads storage to
    build the response.
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
    resulting_version: int
    cited_claim_count: int


class ItemCommandRepositoryPort(Protocol):
    """Session-bound persistence operations for governed item assignments."""

    async def load_scoped_item(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
    ) -> ScopedItem:
        """Load the exact scoped item with its current version.

        Raises :class:`~clearcut.commanding.errors.CommandNotFoundError` when the
        item is not visible in the authenticated organization-and-project scope,
        presenting the same neutral shape whether the item is absent or belongs
        to another tenant.
        """
        ...

    async def is_active_member(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        user_id: UUID,
    ) -> bool:
        """Report whether ``user_id`` is an active member of ``org_id``.

        The assignment target must be an active authorized member of the scope;
        an inactive or foreign user is not a valid assignee. The service maps a
        negative result to a neutral not-found so a caller cannot distinguish a
        foreign user from an inactive one.
        """
        ...

    async def commit_assignment(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        assigned_to_user_id: UUID | None,
        due_at: datetime | None,
        expected_version: int,
        resulting_version: int,
    ) -> None:
        """Advance the item version and set the assignee via compare-and-swap.

        The item update is a version-guarded compare-and-swap on
        ``expected_version``; the caller has already classified the command as a
        fresh write at that version. ``due_at`` is persisted onto the same row in
        the same statement (``None`` clears it). All statements run inside the caller's
        transaction. When the compare-and-swap affects zero rows the row moved
        concurrently: a still-present item raises a typed
        :class:`~clearcut.commanding.errors.StaleVersionConflictError`, while a
        genuinely absent/foreign item keeps neutral
        :class:`~clearcut.commanding.errors.CommandNotFoundError` parity.
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
    "PersistedAssignment",
    "ItemCommandRepositoryPort",
]

"""Typed persistence port for the governed specialist-referral slice.

The port is the single boundary the referral application services use to load
the exact tenant-and-project-scoped clearance item and referral, persist the
draft/submit/acknowledge transitions together with the item version advance,
confirm an active authorized target actor, persist the accountable idempotency
receipt, and stage the schema-versioned, deduplicated outbox event. Every value
that crosses the boundary is a typed dataclass or a typed error from the
governed-command kernel; no booleans (except the explicit membership predicate),
``None`` sentinels, or raw rows encode outcomes. A clearance item or referral
that is not visible in the authenticated organization-and-project scope surfaces
as a typed :class:`~clearcut.commanding.errors.CommandNotFoundError`, never a raw
``None`` or a distinguishing error.

Implementations run every statement inside the caller's unit of work so the
referral state transition, the item version advance, the idempotency receipt,
the authoritative audit event, and the outbox event all commit or roll back
atomically.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from clearcut.commanding.domain import CommandEnvelope, PriorReceipt
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class ScopedItem:
    """A clearance item resolved within an exact tenant-and-project scope.

    ``version`` is the current optimistic-concurrency version used to guard the
    referral write.
    """

    item_id: UUID
    org_id: UUID
    project_id: UUID
    version_id: UUID | None
    category: str
    entity_name: str
    status: str
    workflow_status: str
    disposition_status: str | None
    assigned_to_user_id: UUID | None
    context_text: str | None
    version: int


@dataclass(frozen=True)
class ScopedReferral:
    """A referral resolved within an exact tenant-and-project scope.

    ``item_version`` is the referred item's current optimistic-concurrency
    version, used to guard the acknowledge write. ``target_role`` is the role
    the referral was addressed to; acknowledgement requires an active actor whose
    role matches it.
    """

    referral_id: UUID
    org_id: UUID
    project_id: UUID
    item_id: UUID
    target_role: str
    question: str
    notes: str | None
    status: str
    submitted_by_actor_id: UUID
    acknowledged_by_actor_id: UUID | None
    response: str | None
    item_version: int


@dataclass(frozen=True)
class ScopedComment:
    """A comment resolved within an exact tenant-and-project scope.

    ``reply_depth`` is ``0`` for a root comment and ``1`` for a one-level reply;
    the database enforces that no deeper reply can exist. ``parent_comment_id``
    is the immutable parent identity fixed at creation. ``latest_ordinal`` is the
    highest revision ordinal currently persisted for the comment, so the next
    revision can append at ``latest_ordinal + 1``.
    """

    comment_id: UUID
    org_id: UUID
    project_id: UUID
    item_id: UUID
    author_id: UUID
    parent_comment_id: UUID | None
    reply_depth: int
    latest_ordinal: int


@dataclass(frozen=True)
class PersistedComment:
    """A typed comment command result projected directly to HTTP."""

    comment_id: UUID
    org_id: UUID
    project_id: UUID
    item_id: UUID
    author_id: UUID
    parent_comment_id: UUID | None
    reply_depth: int
    ordinal: int
    recipient_user_ids: tuple[UUID, ...]
    body: str
    resulting_item_version: int
    created_at: datetime


@dataclass(frozen=True)
class ActiveMember:
    """An active organization member authorized for the requested scope."""

    user_id: UUID
    role: str


@dataclass(frozen=True)
class PendingOutboxEvent:
    """Typed outbox event staged atomically with a collaboration command."""

    org_id: UUID
    project_id: UUID
    event_type: str
    schema_version: int
    dedupe_key: str
    payload: Mapping[str, Any]
    occurred_at: datetime


@dataclass(frozen=True)
class PersistedReferral:
    """The committed referral transition plus the item's resulting version.

    The service maps this typed result onto the canonical ``Referral`` response;
    the delivery layer never re-reads storage to build the response.
    """

    referral_id: UUID
    item_id: UUID
    org_id: UUID
    project_id: UUID
    target_role: str
    question: str
    status: str
    response: str | None
    resulting_item_version: int


class CollaborationRepositoryPort(Protocol):
    """Session-bound persistence operations for governed referrals."""

    async def load_scoped_item(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
    ) -> ScopedItem:
        """Load the exact scoped item with its optimistic-concurrency version.

        Raises :class:`~clearcut.commanding.errors.CommandNotFoundError` when the
        item is not visible in the authenticated organization-and-project scope,
        presenting the same neutral shape whether the item is absent or belongs
        to another tenant.
        """
        ...

    async def load_scoped_referral(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        referral_id: UUID,
    ) -> ScopedReferral:
        """Load the exact scoped referral joined to its item's current version.

        Raises :class:`~clearcut.commanding.errors.CommandNotFoundError` when the
        referral is not visible in the authenticated organization-and-project
        scope (or is attached to a different item), with neutral parity whether
        absent or foreign.
        """
        ...

    async def load_active_member_with_role(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        user_id: UUID,
        role: str,
    ) -> ActiveMember:
        """Load an active member with the required role or raise forbidden."""
        ...

    async def insert_draft_referral(
        self,
        session: AsyncSession,
        *,
        referral_id: UUID,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        target_role: str,
        question: str,
        notes: str | None,
        submitted_by_actor_id: UUID,
        idempotency_key: str,
        occurred_at: datetime,
    ) -> ScopedReferral | None:
        """Insert a ``draft`` referral row within the caller's transaction.

        A draft never advances the item version and never transitions to the
        submitted state; it captures the brief for later governed submission.
        The insert is savepoint-guarded so a losing
        ``uq_governed_referrals_idempotency`` race is reconciled: on a duplicate
        key the prior draft is re-read and returned as a typed
        :class:`ScopedReferral` so the caller replays the original draft instead
        of surfacing a raw integrity error. Returns ``None`` on a fresh insert.
        """
        ...

    async def insert_submitted_referral(
        self,
        session: AsyncSession,
        *,
        referral_id: UUID,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        target_role: str,
        question: str,
        notes: str | None,
        submitted_by_actor_id: UUID,
        idempotency_key: str,
        expected_version: int,
        resulting_version: int,
        occurred_at: datetime,
    ) -> None:
        """Insert a ``submitted`` referral and advance the item version.

        Records the referral row and advances the item's ``version`` and
        ``workflow_status`` to ``referred`` with a single version-guarded
        compare-and-swap on ``expected_version``. All statements run inside the
        caller's transaction. The compare-and-swap runs first as the
        authoritative concurrency serializer; a zero-row compare-and-swap is
        disambiguated by scoped idempotency: a genuinely concurrent same-key
        retry that lost the version race returns so the receipt guard replays it
        idempotently, while any other miss is classified exactly as
        :meth:`classify_cas_miss` documents (still-present item -> stale-version
        409; absent/foreign item -> neutral not-found 404). A zero-row write is
        never reported as a success, and a concurrent duplicate never surfaces a
        raw integrity error.
        """
        ...

    async def acknowledge_referral(
        self,
        session: AsyncSession,
        *,
        referral_id: UUID,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        acknowledged_by_actor_id: UUID,
        response: str,
        expected_version: int,
        resulting_version: int,
        occurred_at: datetime,
    ) -> None:
        """Transition a submitted referral to ``acknowledged`` and advance the item.

        Sets the referral ``status`` to ``acknowledged`` with the acknowledging
        actor, response, and time (guarded so only a currently ``submitted``
        referral transitions), and advances the item's ``version`` and
        ``workflow_status`` to ``referral_acknowledged`` with a version-guarded
        compare-and-swap on ``expected_version``. All statements run inside the
        caller's transaction. A zero-row item compare-and-swap is classified by
        :meth:`classify_cas_miss`.
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

        Returns ``None`` when the fresh receipt was persisted, or the typed prior
        :class:`~clearcut.commanding.domain.PriorReceipt` when a concurrent writer
        already committed the receipt for this exact scope — following the
        kernel's documented caller re-read contract so the losing race replays
        the original idempotent result rather than surfacing a raw integrity
        error. Runs inside the caller's transaction using a savepoint so a losing
        race does not poison the outer unit of work.
        """
        ...

    async def load_active_project_member(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        user_id: UUID,
    ) -> ActiveMember:
        """Load an active project-authorized member or raise forbidden."""
        ...

    async def load_scoped_comment(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        comment_id: UUID,
    ) -> ScopedComment:
        """Load the exact scoped comment with its reply depth and latest ordinal.

        Raises :class:`~clearcut.commanding.errors.CommandNotFoundError` when the
        comment is not visible in the authenticated organization-and-project
        scope, with neutral parity whether the comment is absent or foreign.
        """
        ...

    async def load_persisted_comment_result(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        comment_id: UUID,
        resulting_item_version: int,
    ) -> PersistedComment:
        """Load the immutable ordinal-1 result for an add/reply receipt."""
        ...

    async def load_persisted_revision_result(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        revision_id: UUID,
        resulting_item_version: int,
    ) -> PersistedComment:
        """Load the exact immutable revision identified by a revise receipt."""
        ...

    async def filter_active_member_recipients(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        candidate_user_ids: tuple[UUID, ...],
    ) -> frozenset[UUID]:
        """Return the subset of ``candidate_user_ids`` that are active members.

        The recipient set for mentions must resolve to active authorized project
        members only; a foreign or deactivated candidate is simply absent from
        the returned set. The service compares this against the requested
        recipients to reject any unauthorized recipient as a typed validation
        error rather than silently dropping it.
        """
        ...

    async def insert_comment(
        self,
        session: AsyncSession,
        *,
        comment_id: UUID,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        author_id: UUID,
        parent_comment_id: UUID | None,
        parent_reply_depth: int | None,
        reply_depth: int,
        body: str,
        recipient_user_ids: tuple[UUID, ...],
        expected_version: int,
        resulting_version: int,
        occurred_at: datetime,
    ) -> None:
        """Insert one comment (root or reply), its first revision, and mentions.

        Every statement runs in the caller's transaction so the comment row, the
        ordinal-1 revision, and any mention rows commit atomically with the
        authoritative audit event and the outbox event. A reply carries
        ``reply_depth = 1`` and ``parent_reply_depth = 0``; the database's
        composite parent foreign key and single-reply-level check reject a
        reply-to-reply, which this method surfaces as a typed
        :class:`~clearcut.commanding.errors.CommandValidationError` (never a raw
        integrity error). ``recipient_user_ids`` are already resolved,
        deduplicated, and actor-excluded by the service; they are persisted as
        mention rows.
        """
        ...

    async def append_comment_revision(
        self,
        session: AsyncSession,
        *,
        revision_id: UUID,
        comment_id: UUID,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        author_id: UUID,
        ordinal: int,
        body: str,
        recipient_user_ids: tuple[UUID, ...],
        expected_version: int,
        resulting_version: int,
        occurred_at: datetime,
    ) -> None:
        """Append one immutable revision at ``ordinal`` within the caller's transaction.

        Revisions are append-only: this inserts a new row and never updates or
        deletes an existing one, so the full attributable history is preserved.
        The ``(org_id, project_id, comment_id, ordinal)`` uniqueness and the
        positive-ordinal check are enforced by the database.
        """
        ...

    async def stage_outbox_event(
        self,
        session: AsyncSession,
        event: PendingOutboxEvent,
    ) -> None:
        """Persist one typed schema-versioned, deduplicated outbox event."""
        ...


__all__ = [
    "ActiveMember",
    "PendingOutboxEvent",
    "ScopedItem",
    "ScopedReferral",
    "ScopedComment",
    "PersistedComment",
    "PersistedReferral",
    "CollaborationRepositoryPort",
]

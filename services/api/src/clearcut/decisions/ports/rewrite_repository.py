"""Typed persistence port for the governed rewrite-proposal lifecycle.

The port is the only boundary the rewrite application service uses to read the
authorized server-side source of a rewrite (the item, its bound script version,
its element, and that element's actual text), to persist a proposal, to move a
proposal through its lifecycle, and to list the proposals raised against an
item. Client-supplied provenance never reaches storage: the service reads
``original_text``, ``element_id``, and ``source_version_id`` from
:class:`RewriteSource`, never from a request body.

Every value crossing the boundary is a typed dataclass or a typed
governed-command error. A proposal or item that is not visible in the
authenticated organization-and-project scope surfaces as a typed
:class:`~clearcut.commanding.errors.CommandNotFoundError` with the same neutral
shape whether it is absent or foreign, so a caller cannot probe another tenant.

Implementations run every statement inside the caller's unit of work, so the
proposal write, the item version advance, the idempotency receipt, and the
authoritative audit event commit or roll back together.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from clearcut.commanding.domain import CommandEnvelope, PriorReceipt
from clearcut.decisions.domain.rewrites import (
    RewriteProposal,
    RewriteProposalStatus,
)
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class RewriteSource:
    """The authorized server-side record a new proposal is derived from.

    ``source_version_id`` is the script version the clearance item is currently
    bound to and ``original_text`` is the real text of ``element_id`` in that
    version, both read from storage. ``current_version_id`` is the newest
    committed version of the item's script, carried so the projected proposal can
    report source-versus-current identity truthfully. ``item_version`` is the
    item's optimistic concurrency version, used as the governed command's
    expected version because the canonical contract for these operations carries
    no client-supplied expected version.
    """

    item_id: UUID
    org_id: UUID
    project_id: UUID
    source_version_id: UUID
    element_id: UUID
    original_text: str
    item_version: int
    current_version_id: UUID | None


@dataclass(frozen=True)
class ScopedRewriteProposal:
    """A persisted proposal resolved within an exact tenant-and-project scope.

    ``item_version`` is the *item's* current optimistic version, joined at load
    time, and is the governed command's expected version.

    ``current_version_id`` is the newest committed script version of the
    proposal's script. A proposal whose ``source_version_id`` is no longer that
    version was written against a draft the project has moved past, so approving
    it would ship text that was reviewed against different surroundings. It is
    refused as a visible conflict rather than silently rebased.

    ``proposer_email`` is included because the collaboration surface already
    exposes an author's email on comments; no other personal data is carried.
    """

    proposal_id: UUID
    org_id: UUID
    project_id: UUID
    item_id: UUID
    source_version_id: UUID
    element_id: UUID
    proposer_id: UUID
    proposer_email: str | None
    original_text: str
    proposed_text: str
    rationale: str
    status: RewriteProposalStatus
    approver_id: UUID | None
    rejection_reason: str | None
    resulting_version_id: UUID | None
    created_at: datetime
    updated_at: datetime
    item_version: int
    current_version_id: UUID | None


class RewriteRepositoryPort(Protocol):
    """Session-bound persistence operations for governed rewrite proposals."""

    async def load_rewrite_source(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
    ) -> RewriteSource:
        """Load the authorized source record for a new proposal on ``item_id``.

        Raises :class:`~clearcut.commanding.errors.CommandNotFoundError` when the
        item is not visible in the authenticated scope, and
        :class:`~clearcut.commanding.errors.CommandValidationError` when the item
        is not bound to a script version and element whose text can be read, so
        a proposal can never be recorded against invented original text.
        """
        ...

    async def load_scoped_proposal(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        proposal_id: UUID,
    ) -> ScopedRewriteProposal:
        """Load one proposal with its item's current version, or raise not-found."""
        ...

    async def list_proposals(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
    ) -> tuple[ScopedRewriteProposal, ...]:
        """Return the item's proposals oldest-first, after verifying item scope.

        Raises :class:`~clearcut.commanding.errors.CommandNotFoundError` when the
        item itself is not visible in scope, so an empty list always means "this
        item genuinely has no proposals" rather than "this item is not yours".
        """
        ...

    async def insert_proposal(
        self,
        session: AsyncSession,
        *,
        proposal: RewriteProposal,
        expected_version: int,
        resulting_version: int,
    ) -> None:
        """Insert the proposal and advance the item version in one guarded step.

        The item update is a version-guarded compare-and-swap on
        ``expected_version``. A zero-row swap means the row moved concurrently
        and is classified exactly as :meth:`classify_cas_miss` documents.
        """
        ...

    async def apply_transition(
        self,
        session: AsyncSession,
        *,
        proposal_id: UUID,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        from_status: RewriteProposalStatus,
        to_status: RewriteProposalStatus,
        approver_id: UUID | None,
        rejection_reason: str | None,
        expected_version: int,
        resulting_version: int,
        occurred_at: datetime,
    ) -> None:
        """Move the proposal and advance the item version in one guarded step.

        The proposal update is guarded on ``from_status`` and the item update on
        ``expected_version``, so two concurrent transitions cannot both win:
        the loser raises
        :class:`~clearcut.commanding.errors.StaleVersionConflictError` rather
        than overwriting a committed decision.
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
        """Classify a compare-and-swap miss by scoped existence; never returns."""
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
        receipt when a concurrent writer already committed this exact scope, so
        the losing race replays the original result instead of surfacing a raw
        integrity error.
        """
        ...


__all__ = [
    "RewriteRepositoryPort",
    "RewriteSource",
    "ScopedRewriteProposal",
]

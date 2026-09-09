"""Session-bound SQL adapter for the governed rewrite-proposal port.

Every statement runs on the caller-provided
:class:`~sqlalchemy.ext.asyncio.AsyncSession` and never opens, commits, or rolls
back its own transaction, so the proposal write, the item version advance, the
idempotency receipt, and the authoritative audit event share one atomic unit of
work.

All reads and writes are constrained by the full ``(org_id, project_id)`` scope
tuple, and the source read additionally joins the element through the item's own
bound ``version_id``, so the original text a proposal records is the text of the
exact element in the exact authorized version -- not a client's claim about it.

Two concurrency branches are handled here because only genuine interleaving can
produce them:

* A version-guarded item compare-and-swap that affects zero rows means the item
  moved between load and write: a still-present item is a typed
  :class:`~clearcut.commanding.errors.StaleVersionConflictError`, an absent or
  foreign one keeps the neutral
  :class:`~clearcut.commanding.errors.CommandNotFoundError` parity.
* A status-guarded proposal update that affects zero rows means another
  transition committed first, which is a stale-version conflict: the caller
  already validated the transition against the status it read.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import sqlalchemy as sa
from clearcut.commanding.domain import CommandEnvelope, PriorReceipt
from clearcut.commanding.errors import (
    CommandNotFoundError,
    CommandValidationError,
    StaleVersionConflictError,
)
from clearcut.commanding.sql import insert_command_receipt, lookup_command_receipt
from clearcut.decisions.domain.rewrites import RewriteProposal, RewriteProposalStatus
from clearcut.decisions.ports.rewrite_repository import (
    RewriteSource,
    ScopedRewriteProposal,
)
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

# The element is joined through the item's own version binding, so the original
# text can only come from the element as it exists in the version the item was
# detected in.
_LOAD_SOURCE = sa.text(
    """
    SELECT i.id, i.version_id, i.element_id, i.version, e.text AS original_text,
           (SELECT newest.id FROM script_versions newest
             WHERE newest.script_id = i.script_id
               AND newest.org_id = i.org_id
               AND newest.project_id = i.project_id
             ORDER BY newest.ordinal DESC
             LIMIT 1) AS current_version_id
    FROM clearance_items i
    LEFT JOIN script_elements e
           ON e.id = i.element_id AND e.version_id = i.version_id
    WHERE i.id = :item_id AND i.org_id = :org_id AND i.project_id = :project_id
    """
)

_ITEM_EXISTS_IN_SCOPE = sa.text(
    """
    SELECT version FROM clearance_items
    WHERE id = :item_id AND org_id = :org_id AND project_id = :project_id
    """
)

_PROPOSAL_COLUMNS = """
    p.id, p.org_id, p.project_id, p.item_id, p.source_version_id, p.element_id,
    p.proposer_id, p.original_text, p.proposed_text, p.rationale, p.status,
    p.approver_id, p.rejection_reason, p.resulting_version_id,
    p.created_at, p.updated_at,
    i.version AS item_version,
    u.email AS proposer_email,
    (SELECT newest.id FROM script_versions newest
      WHERE newest.script_id = sv.script_id
        AND newest.org_id = p.org_id
        AND newest.project_id = p.project_id
      ORDER BY newest.ordinal DESC
      LIMIT 1) AS current_version_id
"""

_PROPOSAL_FROM = """
    FROM rewrite_proposals p
    JOIN clearance_items i
      ON i.id = p.item_id AND i.org_id = p.org_id AND i.project_id = p.project_id
    JOIN script_versions sv
      ON sv.id = p.source_version_id AND sv.org_id = p.org_id AND sv.project_id = p.project_id
    LEFT JOIN users u ON u.id = p.proposer_id
"""

_LOAD_PROPOSAL = sa.text(
    f"""
    SELECT {_PROPOSAL_COLUMNS}
    {_PROPOSAL_FROM}
    WHERE p.id = :proposal_id AND p.org_id = :org_id AND p.project_id = :project_id
    """
)

_LIST_PROPOSALS = sa.text(
    f"""
    SELECT {_PROPOSAL_COLUMNS}
    {_PROPOSAL_FROM}
    WHERE p.item_id = :item_id AND p.org_id = :org_id AND p.project_id = :project_id
    ORDER BY p.created_at, p.id
    """
)

_INSERT_PROPOSAL = sa.text(
    """
    INSERT INTO rewrite_proposals (
        id, org_id, project_id, item_id, source_version_id, proposer_id, element_id,
        original_text, proposed_text, rationale, status, approver_id,
        rejection_reason, resulting_version_id, created_at, updated_at
    ) VALUES (
        :id, :org_id, :project_id, :item_id, :source_version_id, :proposer_id, :element_id,
        :original_text, :proposed_text, :rationale, :status, NULL,
        NULL, NULL, :created_at, :updated_at
    )
    """
)

# Guarded on the status the caller validated against: a concurrent transition
# that already moved the proposal makes this affect zero rows.
_TRANSITION_PROPOSAL = sa.text(
    """
    UPDATE rewrite_proposals
    SET status = :to_status,
        approver_id = :approver_id,
        rejection_reason = :rejection_reason,
        updated_at = :updated_at
    WHERE id = :proposal_id AND org_id = :org_id AND project_id = :project_id
      AND status = :from_status
    """
)

# The rewrite lifecycle advances the item's optimistic version only. It never
# touches ``status``, so no rewrite action can imply a clearance conclusion.
_ADVANCE_ITEM = sa.text(
    """
    UPDATE clearance_items
    SET version = :resulting_version
    WHERE id = :item_id AND org_id = :org_id AND project_id = :project_id
      AND version = :expected_version
    """
)


class SqlRewriteRepository:
    """SQL implementation of :class:`RewriteRepositoryPort`."""

    async def load_rewrite_source(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
    ) -> RewriteSource:
        row = (
            (
                await session.execute(
                    _LOAD_SOURCE,
                    {
                        "item_id": str(item_id),
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                    },
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise CommandNotFoundError()
        version_id = _as_optional_uuid(row["version_id"])
        element_id = _as_optional_uuid(row["element_id"])
        original_text = row["original_text"]
        if version_id is None or element_id is None or original_text is None:
            # Without a readable element in the item's own version there is no
            # authorized original text, and inventing one would put unverified
            # provenance into a governed record.
            raise CommandValidationError(
                "This item is not bound to a readable script passage, so a rewrite "
                "cannot be proposed against it."
            )
        return RewriteSource(
            item_id=_as_uuid(row["id"]),
            org_id=org_id,
            project_id=project_id,
            source_version_id=version_id,
            element_id=element_id,
            original_text=str(original_text),
            item_version=int(row["version"]),
            current_version_id=_as_optional_uuid(row["current_version_id"]),
        )

    async def load_scoped_proposal(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        proposal_id: UUID,
    ) -> ScopedRewriteProposal:
        row = (
            (
                await session.execute(
                    _LOAD_PROPOSAL,
                    {
                        "proposal_id": str(proposal_id),
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                    },
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise CommandNotFoundError()
        return _project_row(row)

    async def list_proposals(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
    ) -> tuple[ScopedRewriteProposal, ...]:
        exists = (
            await session.execute(
                _ITEM_EXISTS_IN_SCOPE,
                {
                    "item_id": str(item_id),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                },
            )
        ).first()
        if exists is None:
            raise CommandNotFoundError()
        rows = (
            (
                await session.execute(
                    _LIST_PROPOSALS,
                    {
                        "item_id": str(item_id),
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                    },
                )
            )
            .mappings()
            .all()
        )
        return tuple(_project_row(row) for row in rows)

    async def insert_proposal(
        self,
        session: AsyncSession,
        *,
        proposal: RewriteProposal,
        expected_version: int,
        resulting_version: int,
    ) -> None:
        await session.execute(
            _INSERT_PROPOSAL,
            {
                "id": str(proposal.proposal_id),
                "org_id": str(proposal.org_id),
                "project_id": str(proposal.project_id),
                "item_id": str(proposal.item_id),
                "source_version_id": str(proposal.source_version_id),
                "proposer_id": str(proposal.proposer_id),
                "element_id": str(proposal.element_id),
                "original_text": proposal.original_text,
                "proposed_text": proposal.proposed_text,
                "rationale": proposal.rationale,
                "status": proposal.status.value,
                "created_at": proposal.created_at,
                "updated_at": proposal.updated_at,
            },
        )
        await self._advance_item(
            session,
            org_id=proposal.org_id,
            project_id=proposal.project_id,
            item_id=proposal.item_id,
            expected_version=expected_version,
            resulting_version=resulting_version,
        )

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
        result = await session.execute(
            _TRANSITION_PROPOSAL,
            {
                "proposal_id": str(proposal_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "from_status": from_status.value,
                "to_status": to_status.value,
                "approver_id": str(approver_id) if approver_id is not None else None,
                "rejection_reason": rejection_reason,
                "updated_at": occurred_at,
            },
        )
        if cast(CursorResult[Any], result).rowcount != 1:
            # The caller validated the transition against the status it read, so a
            # miss means a concurrent transition committed first. That is a
            # conflict to surface, never a decision to overwrite.
            raise StaleVersionConflictError()
        await self._advance_item(
            session,
            org_id=org_id,
            project_id=project_id,
            item_id=item_id,
            expected_version=expected_version,
            resulting_version=resulting_version,
        )

    async def classify_cas_miss(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
    ) -> None:
        exists = (
            await session.execute(
                _ITEM_EXISTS_IN_SCOPE,
                {
                    "item_id": str(item_id),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                },
            )
        ).first()
        if exists is not None:
            raise StaleVersionConflictError()
        raise CommandNotFoundError()

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
        try:
            async with session.begin_nested():
                await insert_command_receipt(
                    session,
                    envelope,
                    item_id=item_id,
                    resulting_version=resulting_version,
                    result_id=result_id,
                    occurred_at=occurred_at,
                )
        except IntegrityError:
            prior = await lookup_command_receipt(session, envelope)
            if prior is None:
                # Not the idempotency scope we own: do not mask an unexpected
                # integrity failure as a replay.
                raise
            return prior
        return None

    async def _advance_item(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        expected_version: int,
        resulting_version: int,
    ) -> None:
        result = await session.execute(
            _ADVANCE_ITEM,
            {
                "resulting_version": resulting_version,
                "item_id": str(item_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "expected_version": expected_version,
            },
        )
        if cast(CursorResult[Any], result).rowcount != 1:
            await self.classify_cas_miss(
                session,
                org_id=org_id,
                project_id=project_id,
                item_id=item_id,
            )


def _project_row(row: Any) -> ScopedRewriteProposal:
    return ScopedRewriteProposal(
        proposal_id=_as_uuid(row["id"]),
        org_id=_as_uuid(row["org_id"]),
        project_id=_as_uuid(row["project_id"]),
        item_id=_as_uuid(row["item_id"]),
        source_version_id=_as_uuid(row["source_version_id"]),
        element_id=_as_uuid(row["element_id"]),
        proposer_id=_as_uuid(row["proposer_id"]),
        proposer_email=(str(row["proposer_email"]) if row["proposer_email"] is not None else None),
        original_text=str(row["original_text"]),
        proposed_text=str(row["proposed_text"]),
        rationale=str(row["rationale"]),
        status=RewriteProposalStatus(str(row["status"])),
        approver_id=_as_optional_uuid(row["approver_id"]),
        rejection_reason=(
            str(row["rejection_reason"]) if row["rejection_reason"] is not None else None
        ),
        resulting_version_id=_as_optional_uuid(row["resulting_version_id"]),
        created_at=_as_datetime(row["created_at"]),
        updated_at=_as_datetime(row["updated_at"]),
        item_version=int(row["item_version"]),
        current_version_id=_as_optional_uuid(row["current_version_id"]),
    )


def _as_uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _as_optional_uuid(value: Any) -> UUID | None:
    if value is None:
        return None
    return _as_uuid(value)


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


__all__ = ["SqlRewriteRepository"]

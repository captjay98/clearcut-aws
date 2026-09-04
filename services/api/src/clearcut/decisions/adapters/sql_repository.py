"""Session-bound SQL adapter for the governed evidence-decision port.

Every statement here runs on the caller-provided
:class:`~sqlalchemy.ext.asyncio.AsyncSession` and never opens, commits, or rolls
back its own transaction, so the decision record, item version advance,
idempotency receipt, and authoritative audit event share one atomic unit of
work. All reads and writes are constrained by the full
``(item_id, org_id, project_id)`` scope tuple, so an item is never loaded or
mutated outside the authenticated organization-and-project scope. A missing or
foreign item surfaces as a typed
:class:`~clearcut.commanding.errors.CommandNotFoundError` with the same neutral
shape, never a raw ``None`` or a distinguishing error.

Two concurrency branches are handled here, because they only fire under genuine
interleaving that the caller's sequential classification cannot pre-empt:

* When the version-guarded compare-and-swap affects zero rows, the row moved
  between load and update. The adapter re-checks scoped existence: a still
  present item is a typed
  :class:`~clearcut.commanding.errors.StaleVersionConflictError` (the version
  advanced under us), while a genuinely absent/foreign item keeps the neutral
  :class:`~clearcut.commanding.errors.CommandNotFoundError` parity.
* When the idempotency-receipt insert loses a unique-constraint race, the
  adapter rolls the failed insert back to a savepoint, re-reads the prior
  receipt under the kernel's documented caller re-read contract, and returns it
  so the caller replays the original idempotent result instead of surfacing a
  raw integrity error.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast
from uuid import UUID

import sqlalchemy as sa
from clearcut.commanding.domain import CommandEnvelope, PriorReceipt
from clearcut.commanding.errors import CommandNotFoundError, StaleVersionConflictError
from clearcut.commanding.sql import insert_command_receipt, lookup_command_receipt
from clearcut.decisions.ports.repository import ScopedItem
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

_LOAD_SCOPED_ITEM = sa.text(
    """
    SELECT i.id, i.version_id, i.category, i.text, i.status,
           i.disposition_status, i.assigned_to_user_id, i.version,
           e.text AS context_text,
           (SELECT count(*) FROM evidence_claims c
            WHERE c.item_id = i.id
              AND c.org_id = i.org_id
              AND c.project_id = i.project_id) AS cited_claim_count
    FROM clearance_items i
    LEFT JOIN script_elements e ON e.id = i.element_id
    WHERE i.id = :item_id AND i.org_id = :org_id AND i.project_id = :project_id
    """
)

_ITEM_EXISTS_IN_SCOPE = sa.text(
    """
    SELECT 1 FROM clearance_items
    WHERE id = :item_id AND org_id = :org_id AND project_id = :project_id
    """
)

_INSERT_DECISION = sa.text(
    """
    INSERT INTO governed_decision_records (
        id, org_id, project_id, item_id, actor_id, decision_kind, decision_value,
        rationale, expected_version, resulting_version, created_at
    ) VALUES (
        :id, :org_id, :project_id, :item_id, :actor_id, 'evidence', :decision_value,
        :rationale, :expected_version, :resulting_version, :created_at
    )
    """
)

_ADVANCE_ITEM = sa.text(
    """
    UPDATE clearance_items
    SET version = :resulting_version, status = :next_status
    WHERE id = :item_id AND org_id = :org_id AND project_id = :project_id
      AND version = :expected_version
    """
)

_INSERT_DISPOSITION = sa.text(
    """
    INSERT INTO governed_decision_records (
        id, org_id, project_id, item_id, actor_id, decision_kind, decision_value,
        rationale, expected_version, resulting_version, created_at
    ) VALUES (
        :id, :org_id, :project_id, :item_id, :actor_id, 'disposition', :decision_value,
        :rationale, :expected_version, :resulting_version, :created_at
    )
    """
)

# A disposition advances the optimistic version and sets disposition_status only;
# the clearance ``status`` column is deliberately left untouched so the write can
# never assert a legal conclusion.
_ADVANCE_ITEM_DISPOSITION = sa.text(
    """
    UPDATE clearance_items
    SET version = :resulting_version, disposition_status = :disposition_value
    WHERE id = :item_id AND org_id = :org_id AND project_id = :project_id
      AND version = :expected_version
    """
)


class SqlDecisionRepository:
    """SQL implementation of :class:`DecisionRepositoryPort`."""

    async def load_scoped_item(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
    ) -> ScopedItem:
        row = (
            (
                await session.execute(
                    _LOAD_SCOPED_ITEM,
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
        return ScopedItem(
            item_id=_as_uuid(row["id"]),
            org_id=org_id,
            project_id=project_id,
            version_id=_as_optional_uuid(row["version_id"]),
            category=str(row["category"]),
            entity_name=str(row["text"]),
            status=str(row["status"]),
            disposition_status=(
                str(row["disposition_status"]) if row["disposition_status"] is not None else None
            ),
            assigned_to_user_id=_as_optional_uuid(row["assigned_to_user_id"]),
            context_text=(str(row["context_text"]) if row["context_text"] is not None else None),
            version=int(row["version"]),
            cited_claim_count=int(row["cited_claim_count"]),
        )

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
        if not isinstance(occurred_at, datetime):
            raise TypeError("occurred_at must be a datetime.")
        await session.execute(
            _INSERT_DECISION,
            {
                "id": str(decision_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "item_id": str(item_id),
                "actor_id": str(actor_id),
                "decision_value": decision_value,
                "rationale": rationale,
                "expected_version": expected_version,
                "resulting_version": resulting_version,
                "created_at": occurred_at,
            },
        )
        result = await session.execute(
            _ADVANCE_ITEM,
            {
                "resulting_version": resulting_version,
                "next_status": next_status,
                "item_id": str(item_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "expected_version": expected_version,
            },
        )
        # The version-guarded compare-and-swap must match exactly one row. A zero
        # rowcount means the row moved between load and update: classify the miss
        # by scoped existence so a still-present item is a stale-version conflict
        # (409) while a genuinely absent/foreign item keeps neutral not-found
        # parity (404). The caller's transaction must not commit a decision
        # against a version that changed under it.
        if cast(CursorResult[Any], result).rowcount != 1:
            await self.classify_cas_miss(
                session,
                org_id=org_id,
                project_id=project_id,
                item_id=item_id,
            )

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
        if not isinstance(occurred_at, datetime):
            raise TypeError("occurred_at must be a datetime.")
        await session.execute(
            _INSERT_DISPOSITION,
            {
                "id": str(decision_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "item_id": str(item_id),
                "actor_id": str(actor_id),
                "decision_value": disposition_value,
                "rationale": rationale,
                "expected_version": expected_version,
                "resulting_version": resulting_version,
                "created_at": occurred_at,
            },
        )
        result = await session.execute(
            _ADVANCE_ITEM_DISPOSITION,
            {
                "resulting_version": resulting_version,
                "disposition_value": disposition_value,
                "item_id": str(item_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "expected_version": expected_version,
            },
        )
        # The version-guarded compare-and-swap must match exactly one row. A zero
        # rowcount means the row moved between load and update: classify the miss
        # by scoped existence so a still-present item is a stale-version conflict
        # (409) while a genuinely absent/foreign item keeps neutral not-found
        # parity (404). The caller's transaction must not commit a disposition
        # against a version that changed under it.
        if cast(CursorResult[Any], result).rowcount != 1:
            await self.classify_cas_miss(
                session,
                org_id=org_id,
                project_id=project_id,
                item_id=item_id,
            )

    async def classify_cas_miss(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
    ) -> None:
        """Classify a version-guarded CAS miss by scoped item existence.

        Raises :class:`~clearcut.commanding.errors.StaleVersionConflictError`
        when the item is still present in the ``(org, project)`` scope (its
        version advanced concurrently) and
        :class:`~clearcut.commanding.errors.CommandNotFoundError` when the item
        is absent or foreign, preserving neutral not-found parity. This method
        never returns normally: a CAS miss is always one of the two typed
        conflicts.
        """
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
        """Persist the idempotency receipt, reconciling a concurrent duplicate.

        The kernel's :func:`~clearcut.commanding.sql.insert_command_receipt`
        performs the insert only; the durable idempotency guard is the unique
        scope constraint, and the kernel documents that the caller reacts to a
        unique-violation race by re-reading. This adapter runs the insert inside
        a savepoint so a losing race can be rolled back without poisoning the
        caller's outer transaction, then re-reads the prior receipt and returns
        it for the caller to replay. When there is no conflict the receipt is
        persisted and ``None`` is returned so the caller proceeds with the fresh
        result.
        """
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
            # A concurrent writer committed the receipt for this exact scope
            # first. The savepoint rollback above discarded our losing insert
            # without aborting the outer transaction; re-read the prior receipt
            # so the caller replays the original idempotent result.
            prior = await lookup_command_receipt(session, envelope)
            if prior is None:
                # The unique violation was not the idempotency scope we own; do
                # not mask an unexpected integrity failure as a replay.
                raise
            return prior
        return None


def _as_uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _as_optional_uuid(value: Any) -> UUID | None:
    if value is None:
        return None
    return _as_uuid(value)


__all__ = ["SqlDecisionRepository"]

"""Session-bound SQL helpers for the governed-command kernel.

Every helper accepts an existing :class:`~sqlalchemy.ext.asyncio.AsyncSession`
and issues statements on it directly. None of them open a transaction, commit,
roll back, or start a nested savepoint: they run inside the caller's unit of
work so a governed feature can persist its own aggregate change, the scoped
idempotency receipt, and the authoritative audit event atomically. If the
caller's transaction fails, the kernel's writes are discarded with it.

The helpers touch only the kernel's own tables (``governed_command_receipts``)
and the shared authoritative audit ledger (``authoritative_audit_events``).
They never read or write another module's domain tables; the ``item_id`` and
``target_id`` they persist are supplied by the caller. Values crossing the
public boundary are typed (:class:`~clearcut.commanding.domain.PriorReceipt`) or
typed absence (``None`` return only from the lookup, which is a documented
optional), never raw rows.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
import uuid6
from sqlalchemy.ext.asyncio import AsyncSession

from clearcut.commanding.domain import AuditPayload, CommandEnvelope, PriorReceipt
from clearcut.commanding.errors import CommandValidationError

_RECEIPT_LOOKUP = sa.text(
    """
    SELECT item_id, intent_hash, expected_version, resulting_version, result_id, occurred_at
    FROM governed_command_receipts
    WHERE org_id = :org_id
      AND project_id = :project_id
      AND actor_id = :actor_id
      AND operation = :operation
      AND idempotency_key = :idempotency_key
    """
)

_RECEIPT_INSERT = sa.text(
    """
    INSERT INTO governed_command_receipts (
        id, org_id, project_id, item_id, actor_id, operation, idempotency_key,
        expected_version, resulting_version, intent_hash, result_id, occurred_at
    ) VALUES (
        :id, :org_id, :project_id, :item_id, :actor_id, :operation, :idempotency_key,
        :expected_version, :resulting_version, :intent_hash, :result_id, :occurred_at
    )
    """
)

_AUDIT_INSERT = sa.text(
    """
    INSERT INTO authoritative_audit_events (
        id, org_id, project_id, actor_id, action, target_type,
        target_id, payload_redacted, occurred_at, correlation_id
    ) VALUES (
        :id, :org_id, :project_id, :actor_id, :action, :target_type,
        :target_id, :payload, :occurred_at, :correlation_id
    )
    """
).bindparams(sa.bindparam("payload", type_=sa.JSON()))


async def lookup_command_receipt(
    session: AsyncSession,
    envelope: CommandEnvelope,
) -> PriorReceipt | None:
    """Return the prior receipt for this exact scope tuple, or ``None``.

    Scope is the full tenant-and-accountability key
    ``(org_id, project_id, actor_id, operation, idempotency_key)`` that matches
    the receipt table's uniqueness constraint, so a receipt is never visible
    across organizations, projects, or actors.
    """
    row = (
        (
            await session.execute(
                _RECEIPT_LOOKUP,
                {
                    "org_id": str(envelope.org_id),
                    "project_id": str(envelope.project_id),
                    "actor_id": str(envelope.actor_id),
                    "operation": envelope.operation,
                    "idempotency_key": envelope.idempotency_key,
                },
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    return PriorReceipt(
        item_id=_as_uuid(row["item_id"]),
        intent_hash=str(row["intent_hash"]),
        expected_version=int(row["expected_version"]),
        resulting_version=int(row["resulting_version"]),
        result_id=_as_uuid(row["result_id"]),
        occurred_at=_as_datetime(row["occurred_at"]),
    )


async def insert_command_receipt(
    session: AsyncSession,
    envelope: CommandEnvelope,
    *,
    item_id: UUID,
    resulting_version: int,
    result_id: UUID,
    occurred_at: datetime,
) -> None:
    """Persist the accountable idempotency receipt within the caller's transaction.

    The unique constraint on the scope tuple is the durable idempotency guard;
    this helper performs the insert only. The caller decides how to react to a
    unique-violation race (typically by re-reading via
    :func:`lookup_command_receipt`).
    """
    _require_aware(occurred_at)
    await session.execute(
        _RECEIPT_INSERT,
        {
            "id": str(uuid6.uuid7()),
            "org_id": str(envelope.org_id),
            "project_id": str(envelope.project_id),
            "item_id": str(item_id),
            "actor_id": str(envelope.actor_id),
            "operation": envelope.operation,
            "idempotency_key": envelope.idempotency_key,
            "expected_version": envelope.expected_version,
            "resulting_version": resulting_version,
            "intent_hash": envelope.intent_hash,
            "result_id": str(result_id),
            "occurred_at": occurred_at,
        },
    )


async def insert_authoritative_audit(
    session: AsyncSession,
    envelope: CommandEnvelope,
    *,
    action: str,
    target_type: str,
    target_id: UUID,
    payload: AuditPayload,
    correlation_id: UUID,
    occurred_at: datetime,
) -> None:
    """Append the authoritative audit event within the caller's transaction.

    The event records the accountable actor and tenant scope from the envelope
    and a caller-supplied correlation id, committing in the same transaction as
    the governed change it attests to. The payload crosses the boundary as a
    typed :class:`~clearcut.commanding.domain.AuditPayload`; its redacted
    mapping is what reaches ``payload_redacted``, never an arbitrary raw dict.
    """
    _require_aware(occurred_at)
    await session.execute(
        _AUDIT_INSERT,
        {
            "id": str(uuid6.uuid7()),
            "org_id": str(envelope.org_id),
            "project_id": str(envelope.project_id),
            "actor_id": str(envelope.actor_id),
            "action": action,
            "target_type": target_type,
            "target_id": str(target_id),
            "payload": dict(payload.as_redacted()),
            "occurred_at": occurred_at,
            "correlation_id": str(correlation_id),
        },
    )


def _require_aware(value: datetime) -> datetime:
    """Reject naive datetimes on the write path.

    The audit ledger and receipt table store timezone-aware instants; a naive
    datetime is ambiguous and must not be silently coerced to UTC. Callers must
    supply an aware datetime or receive a typed
    :class:`~clearcut.commanding.errors.CommandValidationError`.
    """
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise CommandValidationError("The occurred_at timestamp must be timezone-aware.")
    return value


def _as_uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


__all__ = [
    "lookup_command_receipt",
    "insert_command_receipt",
    "insert_authoritative_audit",
]

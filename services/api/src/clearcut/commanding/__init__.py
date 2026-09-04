"""Shared typed governed-command kernel.

Reusable, module-agnostic building block for governed actions: a validated
immutable :class:`CommandEnvelope`, deterministic replay/conflict
classification, typed safe errors, and session-bound SQL helpers that persist a
scoped idempotency receipt and an authoritative audit event inside a
caller-provided transaction. The kernel owns no domain tables and manages no
transaction of its own; features compose it with their own aggregate writes.
"""

from __future__ import annotations

from clearcut.commanding.domain import (
    AuditPayload,
    CommandClassification,
    CommandEnvelope,
    CurrentVersionUnknown,
    NewCommand,
    PriorReceipt,
    ReplayResult,
    classify_command,
)
from clearcut.commanding.errors import (
    CommandForbiddenError,
    CommandNotFoundError,
    CommandValidationError,
    GovernedCommandError,
    IdempotencyIntentConflictError,
    StaleVersionConflictError,
)
from clearcut.commanding.sql import (
    insert_authoritative_audit,
    insert_command_receipt,
    lookup_command_receipt,
)

__all__ = [
    "CommandEnvelope",
    "PriorReceipt",
    "AuditPayload",
    "CurrentVersionUnknown",
    "NewCommand",
    "ReplayResult",
    "CommandClassification",
    "classify_command",
    "GovernedCommandError",
    "CommandValidationError",
    "CommandForbiddenError",
    "CommandNotFoundError",
    "StaleVersionConflictError",
    "IdempotencyIntentConflictError",
    "lookup_command_receipt",
    "insert_command_receipt",
    "insert_authoritative_audit",
]

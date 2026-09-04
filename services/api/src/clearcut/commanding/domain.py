"""Immutable domain types and deterministic classification for governed commands.

This module is storage-agnostic and side-effect free. It defines the typed
:class:`CommandEnvelope` that every governed command carries (tenant scope,
accountable actor, operation, idempotency key, intent hash, and expected
version), and the pure :func:`classify_command` decision that maps an envelope
plus any prior persisted receipt into a typed outcome:

* no prior receipt and a fresh version  -> :class:`NewCommand`
* same key + same intent                -> :class:`ReplayResult` (prior identity)
* same key + different intent           -> :class:`IdempotencyIntentConflictError`
* stale expected version                -> :class:`StaleVersionConflictError`

Only typed results or typed errors cross the boundary; no booleans, ``None``
sentinels, or raw dicts encode decisions.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from clearcut.commanding.errors import (
    CommandValidationError,
    IdempotencyIntentConflictError,
    StaleVersionConflictError,
)

_MAX_OPERATION_LENGTH = 100
_MAX_IDEMPOTENCY_KEY_LENGTH = 255
_INTENT_HASH_PATTERN = re.compile(r"\A[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class CommandEnvelope:
    """A validated, immutable governed-command request.

    Construction is fail-closed: any malformed field raises
    :class:`CommandValidationError` before the envelope exists, so downstream
    code can trust every field. Validation never echoes the raw offending value
    back into the error message.
    """

    org_id: UUID
    project_id: UUID
    actor_id: UUID
    operation: str
    idempotency_key: str
    intent_hash: str
    expected_version: int

    def __post_init__(self) -> None:
        if not isinstance(self.operation, str) or not self.operation.strip():
            raise CommandValidationError("The command operation must be a non-empty name.")
        if len(self.operation) > _MAX_OPERATION_LENGTH:
            raise CommandValidationError("The command operation name is too long.")
        if not isinstance(self.idempotency_key, str) or not self.idempotency_key.strip():
            raise CommandValidationError("The idempotency key must be a non-empty value.")
        if len(self.idempotency_key) > _MAX_IDEMPOTENCY_KEY_LENGTH:
            raise CommandValidationError("The idempotency key is too long.")
        if not isinstance(self.intent_hash, str) or not _INTENT_HASH_PATTERN.match(
            self.intent_hash
        ):
            raise CommandValidationError(
                "The intent hash must be a 64-character lowercase hex digest."
            )
        if not isinstance(self.expected_version, int) or isinstance(self.expected_version, bool):
            raise CommandValidationError("The expected version must be an integer.")
        if self.expected_version < 1:
            raise CommandValidationError("The expected version must be a positive integer.")


@dataclass(frozen=True)
class PriorReceipt:
    """The persisted identity of a previously committed governed command.

    A replay returns this so the caller can reproduce the original result
    without re-executing side effects.
    """

    item_id: UUID
    intent_hash: str
    expected_version: int
    resulting_version: int
    result_id: UUID
    occurred_at: datetime


@dataclass(frozen=True)
class AuditPayload:
    """A typed seam for the authoritative audit payload.

    The authoritative ``payload_redacted`` column must never receive an
    arbitrary, unconstrained value straight from a caller. This value object is
    the single boundary the SQL helper accepts: it validates that the payload
    is a mapping at construction (fail-closed) and applies an optional
    ``redactor`` hook so secret-bearing keys can be stripped before the payload
    is persisted. Callers pass an :class:`AuditPayload`, never a raw dict.
    """

    raw: Mapping[str, Any]
    redactor: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = field(default=None)

    def __post_init__(self) -> None:
        if not isinstance(self.raw, Mapping):
            raise CommandValidationError("The audit payload must be a mapping.")

    def as_redacted(self) -> Mapping[str, Any]:
        """Return the redacted mapping to persist.

        When a ``redactor`` is supplied it is applied to the raw mapping and its
        result must also be a mapping; otherwise the raw mapping is returned
        unchanged. The result is what reaches ``payload_redacted``.
        """
        if self.redactor is None:
            return self.raw
        redacted = self.redactor(self.raw)
        if not isinstance(redacted, Mapping):
            raise CommandValidationError("The audit redactor must return a mapping.")
        return redacted


@dataclass(frozen=True)
class CurrentVersionUnknown:
    """Explicit typed sentinel that the current aggregate version is unknown.

    The stale-version guard in :func:`classify_command` is not opt-in: a caller
    that genuinely cannot supply the current version must say so with this
    sentinel. A plain missing value is a typed validation error, so a stale
    optimistic-concurrency guess can never silently skip detection.
    """


@dataclass(frozen=True)
class NewCommand:
    """The command has no prior receipt and may proceed to execution."""


@dataclass(frozen=True)
class ReplayResult:
    """The command is an idempotent replay of a prior committed receipt."""

    prior: PriorReceipt


CommandClassification = NewCommand | ReplayResult


def classify_command(
    envelope: CommandEnvelope,
    *,
    prior: PriorReceipt | None,
    current_version: int | CurrentVersionUnknown,
) -> CommandClassification:
    """Deterministically classify a governed command.

    The decision depends only on the envelope, the prior receipt (if any) for
    the same scope/operation/idempotency key, and the current aggregate version.
    ``current_version`` is required: a caller that cannot supply it must pass an
    explicit :class:`CurrentVersionUnknown` sentinel, so the stale-version guard
    can never be skipped by omission. Any other missing/untyped value is a typed
    :class:`CommandValidationError`. The function is pure and order-independent:
    identical inputs always yield the identical typed outcome or typed error.
    """
    if not isinstance(current_version, (int, CurrentVersionUnknown)) or isinstance(
        current_version, bool
    ):
        raise CommandValidationError(
            "The current version must be an integer or an explicit unknown sentinel."
        )

    if prior is not None:
        if prior.intent_hash == envelope.intent_hash:
            return ReplayResult(prior=prior)
        raise IdempotencyIntentConflictError()

    if isinstance(current_version, int) and current_version != envelope.expected_version:
        raise StaleVersionConflictError()

    return NewCommand()


__all__ = [
    "CommandEnvelope",
    "PriorReceipt",
    "AuditPayload",
    "CurrentVersionUnknown",
    "NewCommand",
    "ReplayResult",
    "CommandClassification",
    "classify_command",
]

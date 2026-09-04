"""Reusable choreography for governed aggregate commands.

Every governed command in a Task 10 feature (evidence decisions, dispositions,
and future referrals/comments) shares the identical transactional dance around
the typed :mod:`clearcut.commanding` kernel:

1. Build the typed :class:`~clearcut.commanding.domain.CommandEnvelope` from the
   caller's fields, so malformed intent/version is a typed
   :class:`~clearcut.commanding.errors.CommandValidationError` before any storage
   is touched. (The feature builds the envelope and passes it in.)
2. Load the exact tenant-and-project-scoped aggregate (typed not-found parity on
   absence/foreign) through an injected loader.
3. Derive capability from the server-provided role only, through an injected
   capability precheck.
4. Run any command-specific domain validation (for example the zero-evidence
   protection) through an injected hook, after the item is known.
5. Classify the command through the shared kernel: an idempotent replay of a
   prior receipt returns the original persisted result; a reused key with a
   different intent is a typed conflict; a stale expected version is a typed
   conflict.
6. For a fresh command, perform the provisional domain write through an injected
   callback, persist the accountable idempotency receipt (reconciling a
   concurrent duplicate key into an idempotent replay via rollback), and append
   the authoritative audit event through the typed
   :class:`~clearcut.commanding.domain.AuditPayload` seam — all in the caller's
   single transaction, so any failure rolls the whole command back.
7. Project the committed identity onto the feature's typed result.

The per-command specifics — operation name, capability, canonical value and
zero-evidence validation, the provisional write, the audit action and payload
shape, and the typed projection — are all injected. The template owns none of
them; it owns only the choreography and its safety invariants (the same-key
replay short-circuit, the reconcile-and-rollback-and-replay race handling, and
the P3 intent-hash tie assertion), so the invariants are proven once and reused.

The kernel SQL seams (receipt lookup, receipt insert, authoritative audit) are
also injected rather than imported here, so a feature keeps a single, patchable
reference to them in its own module — the same seam its behavioral tests rely on
to exercise the receipt-insert race and the audit-rollback path.

This module owns no domain tables and manages no transaction of its own: it runs
inside the caller's unit of work exactly as the SQL helpers do, so the feature
composes it with its own aggregate write.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import uuid6
from sqlalchemy.ext.asyncio import AsyncSession

from clearcut.commanding.domain import (
    AuditPayload,
    CommandEnvelope,
    CurrentVersionUnknown,
    NewCommand,
    PriorReceipt,
    ReplayResult,
    classify_command,
)
from clearcut.commanding.errors import StaleVersionConflictError


@dataclass(frozen=True)
class GovernedCommandContext[ItemT]:
    """The resolved inputs a fresh-command write, audit build, and projection use.

    Passed to the injected write, audit-payload, and projection hooks so each
    feature reads exactly the values it needs without the template guessing at
    per-command shapes. ``item`` is the loaded aggregate; ``resulting_version``
    is the aggregate's current version plus one; ``result_id`` and
    ``correlation_id`` are freshly minted identities; ``occurred_at`` is the
    single timezone-aware instant shared by the domain write, the receipt, and
    the audit event.
    """

    envelope: CommandEnvelope
    item: ItemT
    result_id: UUID
    correlation_id: UUID
    resulting_version: int
    occurred_at: datetime


@dataclass(frozen=True)
class GovernedAudit:
    """The authoritative audit event a fresh command appends.

    ``action`` and ``payload`` are the per-command audit shape; ``target_type``
    and ``target_id`` identify the governed aggregate. The payload is always the
    typed :class:`~clearcut.commanding.domain.AuditPayload` seam, never a raw
    dict, so ``payload_redacted`` can never receive string-interpolated input.
    """

    action: str
    target_type: str
    target_id: UUID
    payload: AuditPayload


# Injected seam signatures. Keeping these explicit documents the template's
# contract with each feature and keeps the type checker honest about the hooks.
type CurrentVersion[ItemT] = Callable[[ItemT], int]
type LoadItem[ItemT] = Callable[[AsyncSession, CommandEnvelope], Awaitable[ItemT]]
type CapabilityCheck = Callable[[], None]
type DomainValidation[ItemT] = Callable[[ItemT], None]
type LookupReceipt = Callable[[AsyncSession, CommandEnvelope], Awaitable[PriorReceipt | None]]
type ProvisionalWrite[ItemT] = Callable[
    [AsyncSession, GovernedCommandContext[ItemT]], Awaitable[None]
]
type PersistReceipt[ItemT] = Callable[
    [AsyncSession, CommandEnvelope, GovernedCommandContext[ItemT]],
    Awaitable[PriorReceipt | None],
]
type BuildAudit[ItemT] = Callable[[GovernedCommandContext[ItemT]], GovernedAudit]
type AppendAudit = Callable[
    [AsyncSession, CommandEnvelope, GovernedAudit, UUID, datetime],
    Awaitable[None],
]
type LoadReplayResult[ResultT] = Callable[
    [AsyncSession, CommandEnvelope, PriorReceipt], Awaitable[ResultT]
]
type ProjectResult[ItemT, ResultT] = Callable[[GovernedCommandContext[ItemT]], ResultT]


async def execute_governed_command[ItemT, ResultT](
    session: AsyncSession,
    envelope: CommandEnvelope,
    *,
    load_item: LoadItem[ItemT],
    check_capability: CapabilityCheck,
    validate_domain: DomainValidation[ItemT],
    current_version: CurrentVersion[ItemT],
    lookup_receipt: LookupReceipt,
    commit_provisional: ProvisionalWrite[ItemT],
    persist_receipt: PersistReceipt[ItemT],
    build_audit: BuildAudit[ItemT],
    append_audit: AppendAudit,
    load_replay_result: LoadReplayResult[ResultT],
    project_result: ProjectResult[ItemT, ResultT],
) -> ResultT:
    """Run one governed aggregate command inside the caller's transaction.

    The template performs the shared choreography and enforces its safety
    invariants; the injected hooks supply every per-command specific. It returns
    the feature's typed result or raises a typed governed-command error; no
    booleans, ``None`` sentinels, or raw dicts cross the boundary.

    ``load_item``, ``check_capability``, and ``validate_domain`` run in that
    order before classification, so a not-found aggregate, a forbidden actor, and
    a domain-rule violation are all resolved before any write is attempted. The
    capability check runs against a loaded item to preserve the
    not-found-before-forbidden parity a feature may rely on.
    """
    # 1) Load the exact scoped aggregate (typed not-found parity on absence).
    item = await load_item(session, envelope)

    # 2) Capability is derived from the server-provided role only.
    check_capability()

    # 3) Command-specific domain validation with the item known (e.g. the
    #    zero-evidence protection). Raises a typed validation error on failure.
    validate_domain(item)

    # 4) Classify against any prior receipt for this exact scope/operation/key.
    prior = await lookup_receipt(session, envelope)
    classification = classify_command(
        envelope,
        prior=prior,
        current_version=current_version(item),
    )

    if isinstance(classification, ReplayResult):
        # An idempotent replay reproduces the prior persisted result without
        # re-executing side effects. The aggregate already reflects the prior
        # resulting version and state, so project it directly.
        return await load_replay_result(session, envelope, classification.prior)

    assert isinstance(classification, NewCommand)  # noqa: S101 - typed exhaustiveness

    context: GovernedCommandContext[ItemT] = GovernedCommandContext(
        envelope=envelope,
        item=item,
        result_id=uuid6.uuid7(),
        correlation_id=uuid6.uuid7(),
        resulting_version=current_version(item) + 1,
        occurred_at=datetime.now(UTC),
    )

    # 5) Provisional domain write via a version-guarded compare-and-swap. This is
    #    the first write of the unit of work, so it establishes a real
    #    transaction the subsequent savepoint-guarded receipt insert nests
    #    inside. A concurrent writer at the same expected version loses the
    #    compare-and-swap here and receives a typed stale-version conflict before
    #    any receipt is attempted.
    try:
        await commit_provisional(session, context)
    except StaleVersionConflictError:
        # A same-key contender can commit its domain write and receipt between
        # our initial receipt lookup and compare-and-swap. Roll back the losing
        # transaction before re-reading durable state. Only a matching receipt
        # converts the stale CAS into replay; absence remains a real stale
        # conflict and a differing intent remains an idempotency conflict.
        await session.rollback()
        concurrent_receipt = await lookup_receipt(session, envelope)
        if concurrent_receipt is None:
            raise
        reconciliation = classify_command(
            envelope,
            prior=concurrent_receipt,
            current_version=CurrentVersionUnknown(),
        )
        assert isinstance(reconciliation, ReplayResult)  # noqa: S101
        return await load_replay_result(session, envelope, reconciliation.prior)

    # 6) Persist the accountable idempotency receipt in the same transaction,
    #    reconciling a concurrent duplicate. The unique scope constraint is the
    #    durable idempotency guard; if a concurrent writer committed this exact
    #    key first, the adapter returns that prior receipt instead of raising.
    prior_receipt = await persist_receipt(session, envelope, context)
    if prior_receipt is not None:
        # A concurrent duplicate committed the same idempotency key first.
        # Discard this transaction's provisional write before classifying the
        # durable winner. A matching intent replays its authoritative result;
        # a differing intent raises the typed idempotency conflict.
        await session.rollback()
        reconciliation = classify_command(
            envelope,
            prior=prior_receipt,
            current_version=CurrentVersionUnknown(),
        )
        assert isinstance(reconciliation, ReplayResult)  # noqa: S101
        return await load_replay_result(session, envelope, reconciliation.prior)

    # 7) Append the authoritative audit event in the same transaction. Any
    #    failure here rolls back the domain write, the version advance, and the
    #    receipt together. The payload is built through the typed AuditPayload
    #    seam from validated, structured values — never string-interpolated
    #    caller input.
    audit = build_audit(context)
    await append_audit(
        session,
        envelope,
        audit,
        context.correlation_id,
        context.occurred_at,
    )

    return project_result(context)


__all__ = [
    "GovernedCommandContext",
    "GovernedAudit",
    "execute_governed_command",
]

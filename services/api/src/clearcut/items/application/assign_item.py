"""Application service for the governed clearance-item assignment slice.

One accepted command assigns (or unassigns) exactly one tenant-and-project-
scoped clearance item to an accountable, active member of the same scope.
Assignment is *operational*: it routes work to a human, it never asserts a legal
conclusion and never changes the item's clearance status or disposition. The
service:

1. Loads the exact scoped item (typed not-found parity when it is not visible).
2. Derives capability from the server-provided role (never client-supplied);
   Owner, Admin, Editor, and Reviewer may assign per the Approval Policy.
3. When assigning to a user, validates that the proposed assignee is an active
   authorized member of the same scope (an inactive or foreign user is a neutral
   not-found, never a distinguishing error). Unassignment clears the assignee
   and requires no assignee validation.
4. Classifies the command through the shared kernel: an idempotent replay of a
   prior receipt returns the original persisted result; a reused key with a
   different intent is a typed conflict; a stale expected version is a typed
   conflict.
5. For a fresh command, advances the item version and sets the assignee with an
   optimistic compare-and-swap, writes the accountable idempotency receipt
   (reconciling a concurrent duplicate key into an idempotent replay), and
   appends the authoritative audit event — all in the caller's single
   transaction, so any failure rolls the whole assignment back.

Only typed results or typed governed-command errors cross the boundary; no
booleans, ``None`` sentinels, or raw dicts encode decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import uuid6
from clearcut.commanding.domain import (
    AuditPayload,
    CommandEnvelope,
    NewCommand,
    ReplayResult,
    classify_command,
)
from clearcut.commanding.errors import CommandForbiddenError, CommandNotFoundError
from clearcut.commanding.sql import insert_authoritative_audit, lookup_command_receipt
from clearcut.items.ports.command_repository import (
    ItemCommandRepositoryPort,
    PersistedAssignment,
    ScopedItem,
)
from clearcut.organizations.domain.capabilities import has_capability
from sqlalchemy.ext.asyncio import AsyncSession

# The governed operation name that scopes idempotency receipts for this command.
_OPERATION = "item.assignment.assign"
_ASSIGN_CAPABILITY = "item:assign"
_AUDIT_TARGET_TYPE = "clearance_item"
_AUDIT_ACTION = "item.assignment.assigned"


@dataclass(frozen=True)
class AssignItemCommand:
    """A validated request to assign (or unassign) one clearance item.

    ``actor_role`` is the server-derived membership role; capability is never
    taken from the client. ``assignee_id`` is the target member, or ``None`` to
    unassign. ``expected_version`` and ``intent_hash`` are the optimistic-
    concurrency and intent inputs the shared kernel validates.
    """

    org_id: UUID
    project_id: UUID
    item_id: UUID
    actor_id: UUID
    actor_role: str
    assignee_id: UUID | None
    expected_version: int
    intent_hash: str
    idempotency_key: str


class AssignItemService:
    """Coordinates one governed item assignment within a single transaction."""

    def __init__(self, repository: ItemCommandRepositoryPort) -> None:
        self._repository = repository

    async def assign(
        self,
        session: AsyncSession,
        command: AssignItemCommand,
    ) -> PersistedAssignment:
        # Build the typed envelope first; malformed intent/version is a typed
        # validation error before any storage is touched.
        envelope = CommandEnvelope(
            org_id=command.org_id,
            project_id=command.project_id,
            actor_id=command.actor_id,
            operation=_OPERATION,
            idempotency_key=command.idempotency_key,
            intent_hash=command.intent_hash,
            expected_version=command.expected_version,
        )

        # Load the exact scoped item (typed not-found parity on absence/foreign).
        item = await self._repository.load_scoped_item(
            session,
            org_id=command.org_id,
            project_id=command.project_id,
            item_id=command.item_id,
        )

        # Capability is derived from the server-provided role only.
        if not has_capability(command.actor_role, _ASSIGN_CAPABILITY):
            raise CommandForbiddenError()

        # When assigning to a user, the assignee must be an active authorized
        # member of the same scope. An inactive or foreign user is surfaced as a
        # neutral not-found so a caller cannot probe membership. Unassignment
        # (a None assignee) clears the field and needs no assignee validation.
        if command.assignee_id is not None:
            assignee_is_member = await self._repository.is_active_member(
                session,
                org_id=command.org_id,
                user_id=command.assignee_id,
            )
            if not assignee_is_member:
                raise CommandNotFoundError()

        prior = await lookup_command_receipt(session, envelope)
        classification = classify_command(
            envelope,
            prior=prior,
            current_version=item.version,
        )

        if isinstance(classification, ReplayResult):
            # An idempotent replay reproduces the prior persisted result without
            # re-executing side effects. The item already reflects the prior
            # resulting version and assignee, so project it directly.
            return _project(
                item,
                resulting_version=classification.prior.resulting_version,
                assigned_to_user_id=item.assigned_to_user_id,
            )

        assert isinstance(classification, NewCommand)  # noqa: S101 - typed exhaustiveness

        result_id = uuid6.uuid7()
        correlation_id = uuid6.uuid7()
        resulting_version = item.version + 1
        occurred_at = datetime.now(UTC)

        # Advance the item version and set the assignee via a version-guarded
        # compare-and-swap. This is the first write of the unit of work, so it
        # establishes a real transaction the subsequent savepoint-guarded receipt
        # insert nests inside. A concurrent writer at the same expected version
        # loses the compare-and-swap here and receives a typed stale-version
        # conflict before any receipt is attempted; a scoped item that does not
        # exist surfaces a neutral not-found rather than a false success.
        await self._repository.commit_assignment(
            session,
            org_id=command.org_id,
            project_id=command.project_id,
            item_id=command.item_id,
            assigned_to_user_id=command.assignee_id,
            expected_version=item.version,
            resulting_version=resulting_version,
        )

        # Persist the accountable idempotency receipt in the same transaction,
        # reconciling a concurrent duplicate. The unique scope constraint is the
        # durable idempotency guard; if a concurrent writer committed this exact
        # key first, the adapter returns that prior receipt instead of raising.
        prior_receipt = await self._repository.persist_receipt_idempotent(
            session,
            envelope,
            item_id=command.item_id,
            resulting_version=resulting_version,
            result_id=result_id,
            occurred_at=occurred_at,
        )
        if prior_receipt is not None:
            # A concurrent duplicate committed the same idempotency key first.
            # Discard this transaction's provisional version advance entirely and
            # replay the prior committed identity, so the reused key never assigns
            # twice; the concurrent winner's own transaction holds the
            # authoritative version and audit.
            #
            # The reconciled receipt is this command's own intent replayed, not a
            # stale value: the receipt scope is (org, project, actor, operation,
            # idempotency_key), and the kernel only treats a same-key receipt as a
            # replay when its intent hash matches (a differing intent on the same
            # key is a typed IdempotencyIntentConflictError, never a silent
            # reconcile). For assignment the intent hash is derived from the
            # target assignee, so equal intent means equal resulting assignee.
            # Projecting the pre-command ``item.assigned_to_user_id`` is therefore
            # the winner's assignee for this exact intent, not a misread stale
            # value. Assert the tie explicitly so the invariant is enforced, not
            # merely assumed.
            assert prior_receipt.intent_hash == envelope.intent_hash, (  # noqa: S101
                "A reconciled duplicate-key receipt must share this command's "
                "intent hash; a differing intent is an intent conflict, never a "
                "silent replay."
            )
            await session.rollback()
            return _project(
                item,
                resulting_version=prior_receipt.resulting_version,
                assigned_to_user_id=item.assigned_to_user_id,
            )

        # Append the authoritative audit event in the same transaction. Any
        # failure here rolls back the version advance and the receipt together.
        # The payload records the operational routing only; it never asserts a
        # legal conclusion.
        await insert_authoritative_audit(
            session,
            envelope,
            action=_AUDIT_ACTION,
            target_type=_AUDIT_TARGET_TYPE,
            target_id=command.item_id,
            payload=AuditPayload(
                {
                    "assigneeId": (
                        str(command.assignee_id) if command.assignee_id is not None else None
                    ),
                    "expectedVersion": item.version,
                    "resultingVersion": resulting_version,
                }
            ),
            correlation_id=correlation_id,
            occurred_at=occurred_at,
        )

        return _project(
            item,
            resulting_version=resulting_version,
            assigned_to_user_id=command.assignee_id,
        )


def _project(
    item: ScopedItem,
    *,
    resulting_version: int,
    assigned_to_user_id: UUID | None,
) -> PersistedAssignment:
    return PersistedAssignment(
        item_id=item.item_id,
        org_id=item.org_id,
        project_id=item.project_id,
        version_id=item.version_id,
        category=item.category,
        entity_name=item.entity_name,
        status=item.status,
        disposition_status=item.disposition_status,
        assigned_to_user_id=assigned_to_user_id,
        context_text=item.context_text,
        resulting_version=resulting_version,
        cited_claim_count=item.cited_claim_count,
    )


__all__ = [
    "AssignItemCommand",
    "AssignItemService",
]

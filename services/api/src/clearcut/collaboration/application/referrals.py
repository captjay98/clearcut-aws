"""Application services for the governed specialist-referral collaboration slice.

Three explicit, attributable transitions live here, each keeping submission and
acknowledgement independent per the Approval Policy and DG-03:

* **draft** — an Editor (or above) may save a referral brief. A draft never
  advances the item version and never enters the submitted state; it is the only
  transition an Editor may perform. Draft is a service-level transition and is
  not exposed as a governed HTTP command.
* **submit** — Owner, Admin, or Reviewer submits the referral to an authorized
  specialist role. Submission is governed: it advances the item version, sets the
  item workflow status to ``referred``, and persists the referral, the
  accountable idempotency receipt, the authoritative audit event, and a
  schema-versioned, deduplicated outbox event, all in one transaction.
* **acknowledge** — an *active authorized target actor* (an active member whose
  role matches the referral's target role) answers the referral. Acknowledgement
  is a separate governed transition: it advances the item version again, sets the
  item workflow status to ``referral_acknowledged``, transitions the referral to
  ``acknowledged`` with the acknowledging actor and response, and persists the
  receipt, audit event, and outbox event in one transaction.

The governed submit and acknowledge transitions reuse the shared
:func:`~clearcut.commanding.template.execute_governed_command` choreography; this
module supplies only the referral specifics (capability, active-target-actor
validation, the item write, and the audit/outbox/projection shapes) as injected
hooks. The module keeps its own ``lookup_command_receipt``,
``insert_authoritative_audit``, and ``insert_outbox_event`` references so the
kernel SQL seams and the outbox seam remain patchable at this boundary — the
same seams the behavioral rollback tests exercise.

A referral is a *workflow* signal only: it never asserts a legal conclusion,
never guarantees legal clearance, and never fabricates evidence. Only typed
results or typed governed-command errors cross the boundary; no booleans,
``None`` sentinels, or raw dicts encode decisions, and every audit/outbox payload
is built from validated, structured values rather than string interpolation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import uuid6
from clearcut.collaboration.ports.repository import (
    CollaborationRepositoryPort,
    PendingOutboxEvent,
    PersistedReferral,
    ScopedItem,
)
from clearcut.commanding.domain import AuditPayload, CommandEnvelope, PriorReceipt
from clearcut.commanding.errors import (
    CommandForbiddenError,
    CommandValidationError,
    StaleVersionConflictError,
)
from clearcut.commanding.sql import insert_authoritative_audit, lookup_command_receipt
from clearcut.commanding.template import (
    GovernedAudit,
    GovernedCommandContext,
    execute_governed_command,
)
from clearcut.organizations.domain.capabilities import has_capability
from sqlalchemy.ext.asyncio import AsyncSession

# The governed operation names that scope idempotency receipts for each command.
_SUBMIT_OPERATION = "referral.submit"
_ACKNOWLEDGE_OPERATION = "referral.acknowledge"
# A draft is a distinct transition from a submit: it must carry its own
# operation identity so a draft receipt/audit reflects the real operation and a
# draft can never share a receipt scope with a submit that reuses the same key.
_DRAFT_OPERATION = "referral.draft"

# Submitting a referral is a governed capability held by Owner, Admin, and
# Reviewer only (DG-03). Editor may draft but not submit.
_SUBMIT_CAPABILITY = "item:refer"
# Drafting a brief requires participation in the project. Every project role in
# the Role enum (Owner, Admin, Editor, Reviewer) holds ``project:read``. Draft is
# deliberately not gated on ``item:refer`` so an Editor (who lacks it) may still
# draft.
_DRAFT_CAPABILITY = "project:read"

_AUDIT_TARGET_TYPE = "referral"
_SUBMIT_AUDIT_ACTION = "referral.submitted"
_ACKNOWLEDGE_AUDIT_ACTION = "referral.acknowledged"

# Outbox event identity. The schema version lets downstream consumers evolve the
# payload shape without ambiguity; the dedupe key makes the staged event unique
# within the tenant so a transition can never enqueue twice.
_OUTBOX_SCHEMA_VERSION = 1
_SUBMIT_EVENT_TYPE = "referral_submitted.v1"
_ACKNOWLEDGE_EVENT_TYPE = "referral_acknowledged.v1"


async def insert_outbox_event(
    repository: CollaborationRepositoryPort,
    session: AsyncSession,
    *,
    org_id: UUID,
    project_id: UUID,
    event_type: str,
    schema_version: int,
    dedupe_key: str,
    payload: dict[str, Any],
    occurred_at: datetime,
) -> None:
    """Stage one schema-versioned, deduplicated outbox event.

    Delegates to the repository's session-bound
    :meth:`~clearcut.collaboration.ports.repository.CollaborationRepositoryPort.stage_outbox_event`
    within the caller's transaction. Defined as a module-level seam so the
    outbox write is patchable at this boundary; the behavioral rollback tests
    inject a failure here to prove the whole command rolls back atomically.
    """
    await repository.stage_outbox_event(
        session,
        PendingOutboxEvent(
            org_id=org_id,
            project_id=project_id,
            event_type=event_type,
            schema_version=schema_version,
            dedupe_key=dedupe_key,
            payload=payload,
            occurred_at=occurred_at,
        ),
    )


@dataclass(frozen=True)
class DraftReferralCommand:
    """A validated request to save a referral brief as a draft.

    ``actor_role`` is the server-derived membership role; capability is never
    taken from the client. ``expected_version`` and ``intent_hash`` are validated
    for a consistent command shape, but a draft never advances the item version.
    """

    org_id: UUID
    project_id: UUID
    item_id: UUID
    actor_id: UUID
    actor_role: str
    target_role: str
    question: str
    rationale: str
    expected_version: int
    intent_hash: str
    idempotency_key: str


@dataclass(frozen=True)
class SubmitReferralCommand:
    """A validated request to submit one specialist referral."""

    org_id: UUID
    project_id: UUID
    item_id: UUID
    actor_id: UUID
    actor_role: str
    target_role: str
    question: str
    rationale: str
    expected_version: int
    intent_hash: str
    idempotency_key: str


@dataclass(frozen=True)
class AcknowledgeReferralCommand:
    """A validated request to acknowledge one referral as the target actor."""

    org_id: UUID
    project_id: UUID
    item_id: UUID
    referral_id: UUID
    actor_id: UUID
    actor_role: str
    response: str
    rationale: str
    expected_version: int
    intent_hash: str
    idempotency_key: str


class ReferralService:
    """Coordinates draft/submit/acknowledge referral transitions transactionally."""

    def __init__(self, repository: CollaborationRepositoryPort) -> None:
        self._repository = repository

    async def draft(
        self,
        session: AsyncSession,
        command: DraftReferralCommand,
    ) -> PersistedReferral:
        target_role = command.target_role.strip()
        question = command.question.strip()
        rationale = command.rationale.strip()
        if not target_role or not question or not rationale:
            raise CommandValidationError(
                "A referral draft requires a target role, question, and rationale."
            )

        # Build the envelope so malformed intent/version is a typed validation
        # error before any storage is touched. The draft carries its own
        # operation identity, distinct from submit, so a draft receipt/audit
        # reflects the real transition.
        CommandEnvelope(
            org_id=command.org_id,
            project_id=command.project_id,
            actor_id=command.actor_id,
            operation=_DRAFT_OPERATION,
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

        # Capability is derived from the server-provided role only. Drafting is
        # available to project participants (Owner/Admin/Editor/Reviewer); an
        # Editor who cannot submit may still draft a brief.
        if not has_capability(command.actor_role, _DRAFT_CAPABILITY):
            raise CommandForbiddenError()

        referral_id = uuid6.uuid7()
        occurred_at = datetime.now(UTC)
        prior = await self._repository.insert_draft_referral(
            session,
            referral_id=referral_id,
            org_id=command.org_id,
            project_id=command.project_id,
            item_id=command.item_id,
            target_role=target_role,
            question=question,
            notes=rationale,
            submitted_by_actor_id=command.actor_id,
            idempotency_key=command.idempotency_key,
            occurred_at=occurred_at,
        )
        if prior is not None:
            # The idempotency key was already used for a draft; replay the
            # original draft identity instead of surfacing a raw integrity error.
            # A draft never advances the item version.
            return PersistedReferral(
                referral_id=prior.referral_id,
                item_id=command.item_id,
                org_id=command.org_id,
                project_id=command.project_id,
                target_role=prior.target_role,
                question=prior.question,
                status="draft",
                response=None,
                resulting_item_version=item.version,
            )
        # A draft never advances the item version.
        return PersistedReferral(
            referral_id=referral_id,
            item_id=command.item_id,
            org_id=command.org_id,
            project_id=command.project_id,
            target_role=target_role,
            question=question,
            status="draft",
            response=None,
            resulting_item_version=item.version,
        )

    async def submit(
        self,
        session: AsyncSession,
        command: SubmitReferralCommand,
    ) -> PersistedReferral:
        target_role = command.target_role.strip()
        question = command.question.strip()
        rationale = command.rationale.strip()

        envelope = CommandEnvelope(
            org_id=command.org_id,
            project_id=command.project_id,
            actor_id=command.actor_id,
            operation=_SUBMIT_OPERATION,
            idempotency_key=command.idempotency_key,
            intent_hash=command.intent_hash,
            expected_version=command.expected_version,
        )

        referral_id = uuid6.uuid7()

        async def load_item(session: AsyncSession, _envelope: CommandEnvelope) -> ScopedItem:
            return await self._repository.load_scoped_item(
                session,
                org_id=command.org_id,
                project_id=command.project_id,
                item_id=command.item_id,
            )

        def check_capability() -> None:
            # Owner/Admin/Reviewer may submit a referral (DG-03).
            if not has_capability(command.actor_role, _SUBMIT_CAPABILITY):
                raise CommandForbiddenError()

        def validate_domain(_item: ScopedItem) -> None:
            # A referral never asserts a legal conclusion; there is no
            # zero-evidence gate to enforce here.
            return None

        async def lookup_receipt(session: AsyncSession, envelope: CommandEnvelope):
            return await lookup_command_receipt(session, envelope)

        async def commit_provisional(
            session: AsyncSession,
            context: GovernedCommandContext[ScopedItem],
        ) -> None:
            await self._repository.insert_submitted_referral(
                session,
                referral_id=referral_id,
                org_id=command.org_id,
                project_id=command.project_id,
                item_id=command.item_id,
                target_role=target_role,
                question=question,
                notes=rationale,
                submitted_by_actor_id=command.actor_id,
                idempotency_key=command.idempotency_key,
                expected_version=context.item.version,
                resulting_version=context.resulting_version,
                occurred_at=context.occurred_at,
            )

        async def persist_receipt(
            session: AsyncSession,
            envelope: CommandEnvelope,
            context: GovernedCommandContext[ScopedItem],
        ):
            return await self._repository.persist_receipt_idempotent(
                session,
                envelope,
                item_id=command.item_id,
                resulting_version=context.resulting_version,
                result_id=referral_id,
                occurred_at=context.occurred_at,
            )

        def build_audit(context: GovernedCommandContext[ScopedItem]) -> GovernedAudit:
            return GovernedAudit(
                action=_SUBMIT_AUDIT_ACTION,
                target_type=_AUDIT_TARGET_TYPE,
                target_id=referral_id,
                payload=AuditPayload(
                    {
                        "referralId": str(referral_id),
                        "itemId": str(command.item_id),
                        "targetRole": target_role,
                        "expectedVersion": context.item.version,
                        "resultingVersion": context.resulting_version,
                        "status": "submitted",
                    }
                ),
            )

        async def append_audit(session, envelope, audit, correlation_id, occurred_at) -> None:
            # Append the authoritative audit event and stage the outbox event in
            # the same transaction. Resolving both seams through this module lets
            # the behavioral tests patch either and prove the whole command rolls
            # back on failure. Both run after the provisional write and the
            # receipt, so any failure discards the referral, the version advance,
            # the receipt, and (for an audit failure) nothing is enqueued.
            await insert_authoritative_audit(
                session,
                envelope,
                action=audit.action,
                target_type=audit.target_type,
                target_id=audit.target_id,
                payload=audit.payload,
                correlation_id=correlation_id,
                occurred_at=occurred_at,
            )
            await insert_outbox_event(
                self._repository,
                session,
                org_id=command.org_id,
                project_id=command.project_id,
                event_type=_SUBMIT_EVENT_TYPE,
                schema_version=_OUTBOX_SCHEMA_VERSION,
                dedupe_key=f"referral.submit:{referral_id}",
                payload={
                    "referralId": str(referral_id),
                    "itemId": str(command.item_id),
                    "targetRole": target_role,
                    "status": "submitted",
                },
                occurred_at=occurred_at,
            )

        async def load_replay_result(
            session: AsyncSession,
            _envelope: CommandEnvelope,
            prior: PriorReceipt,
        ) -> PersistedReferral:
            persisted = await self._repository.load_scoped_referral(
                session,
                org_id=command.org_id,
                project_id=command.project_id,
                item_id=command.item_id,
                referral_id=prior.result_id,
            )
            return PersistedReferral(
                referral_id=persisted.referral_id,
                item_id=persisted.item_id,
                org_id=persisted.org_id,
                project_id=persisted.project_id,
                target_role=persisted.target_role,
                question=persisted.question,
                status=persisted.status,
                response=persisted.response,
                resulting_item_version=prior.resulting_version,
            )

        def project_result(context: GovernedCommandContext[ScopedItem]) -> PersistedReferral:
            return PersistedReferral(
                referral_id=referral_id,
                item_id=command.item_id,
                org_id=command.org_id,
                project_id=command.project_id,
                target_role=target_role,
                question=question,
                status="submitted",
                response=None,
                resulting_item_version=context.resulting_version,
            )

        return await execute_governed_command(
            session,
            envelope,
            load_item=load_item,
            check_capability=check_capability,
            validate_domain=validate_domain,
            current_version=lambda item: item.version,
            lookup_receipt=lookup_receipt,
            commit_provisional=commit_provisional,
            persist_receipt=persist_receipt,
            build_audit=build_audit,
            append_audit=append_audit,
            load_replay_result=load_replay_result,
            project_result=project_result,
        )

    async def acknowledge(
        self,
        session: AsyncSession,
        command: AcknowledgeReferralCommand,
    ) -> PersistedReferral:
        response_text = command.response.strip()
        rationale = command.rationale.strip()

        envelope = CommandEnvelope(
            org_id=command.org_id,
            project_id=command.project_id,
            actor_id=command.actor_id,
            operation=_ACKNOWLEDGE_OPERATION,
            idempotency_key=command.idempotency_key,
            intent_hash=command.intent_hash,
            expected_version=command.expected_version,
        )

        # Load the referral first so a missing/foreign referral is a neutral
        # not-found before any capability detail is revealed. The loaded target
        # role and item are then reused by the template's hooks.
        referral = await self._repository.load_scoped_referral(
            session,
            org_id=command.org_id,
            project_id=command.project_id,
            item_id=command.item_id,
            referral_id=command.referral_id,
        )

        async def load_item(session: AsyncSession, _envelope: CommandEnvelope) -> ScopedItem:
            return await self._repository.load_scoped_item(
                session,
                org_id=command.org_id,
                project_id=command.project_id,
                item_id=command.item_id,
            )

        async def check_capability_async() -> None:
            # Acknowledgement requires an active authorized target actor: an
            # active member whose role matches the referral's target role.
            await self._repository.load_active_member_with_role(
                session,
                org_id=command.org_id,
                user_id=command.actor_id,
                role=referral.target_role,
            )

        # The active-target-actor check needs a session query, so run it before
        # the template (which expects a synchronous capability precheck). The
        # referral and item are already loaded in this scope.
        await check_capability_async()

        def check_capability() -> None:
            # Capability was validated above against the active target actor; the
            # template's synchronous hook is a no-op that preserves the ordering.
            return None

        def validate_domain(_item: ScopedItem) -> None:
            return None

        async def lookup_receipt(session: AsyncSession, envelope: CommandEnvelope):
            return await lookup_command_receipt(session, envelope)

        async def commit_provisional(
            session: AsyncSession,
            context: GovernedCommandContext[ScopedItem],
        ) -> None:
            # Terminal-state guard: a referral may be acknowledged exactly once.
            # This runs only on the fresh-command path (an idempotent same-key
            # replay short-circuits before any provisional write), so a
            # distinct-idempotency-key acknowledge of an already-acknowledged
            # referral is rejected as a typed conflict here rather than advancing
            # the item version and emitting a second acknowledged audit/outbox.
            # The referral was loaded at command entry; its status reflects the
            # authoritative pre-command state.
            if referral.status != "submitted":
                raise StaleVersionConflictError()
            await self._repository.acknowledge_referral(
                session,
                referral_id=command.referral_id,
                org_id=command.org_id,
                project_id=command.project_id,
                item_id=command.item_id,
                acknowledged_by_actor_id=command.actor_id,
                response=response_text,
                expected_version=context.item.version,
                resulting_version=context.resulting_version,
                occurred_at=context.occurred_at,
            )

        async def persist_receipt(
            session: AsyncSession,
            envelope: CommandEnvelope,
            context: GovernedCommandContext[ScopedItem],
        ):
            return await self._repository.persist_receipt_idempotent(
                session,
                envelope,
                item_id=command.item_id,
                resulting_version=context.resulting_version,
                result_id=command.referral_id,
                occurred_at=context.occurred_at,
            )

        def build_audit(context: GovernedCommandContext[ScopedItem]) -> GovernedAudit:
            return GovernedAudit(
                action=_ACKNOWLEDGE_AUDIT_ACTION,
                target_type=_AUDIT_TARGET_TYPE,
                target_id=command.referral_id,
                payload=AuditPayload(
                    {
                        "referralId": str(command.referral_id),
                        "itemId": str(command.item_id),
                        "targetRole": referral.target_role,
                        "expectedVersion": context.item.version,
                        "resultingVersion": context.resulting_version,
                        "status": "acknowledged",
                        "rationale": rationale,
                    }
                ),
            )

        async def append_audit(session, envelope, audit, correlation_id, occurred_at) -> None:
            await insert_authoritative_audit(
                session,
                envelope,
                action=audit.action,
                target_type=audit.target_type,
                target_id=audit.target_id,
                payload=audit.payload,
                correlation_id=correlation_id,
                occurred_at=occurred_at,
            )
            await insert_outbox_event(
                self._repository,
                session,
                org_id=command.org_id,
                project_id=command.project_id,
                event_type=_ACKNOWLEDGE_EVENT_TYPE,
                schema_version=_OUTBOX_SCHEMA_VERSION,
                dedupe_key=f"referral.acknowledge:{command.referral_id}",
                payload={
                    "referralId": str(command.referral_id),
                    "itemId": str(command.item_id),
                    "targetRole": referral.target_role,
                    "status": "acknowledged",
                },
                occurred_at=occurred_at,
            )

        async def load_replay_result(
            session: AsyncSession,
            _envelope: CommandEnvelope,
            prior: PriorReceipt,
        ) -> PersistedReferral:
            persisted = await self._repository.load_scoped_referral(
                session,
                org_id=command.org_id,
                project_id=command.project_id,
                item_id=command.item_id,
                referral_id=prior.result_id,
            )
            return PersistedReferral(
                referral_id=persisted.referral_id,
                item_id=persisted.item_id,
                org_id=persisted.org_id,
                project_id=persisted.project_id,
                target_role=persisted.target_role,
                question=persisted.question,
                status=persisted.status,
                response=persisted.response,
                resulting_item_version=prior.resulting_version,
            )

        def project_result(context: GovernedCommandContext[ScopedItem]) -> PersistedReferral:
            return PersistedReferral(
                referral_id=command.referral_id,
                item_id=command.item_id,
                org_id=command.org_id,
                project_id=command.project_id,
                target_role=referral.target_role,
                question=referral.question,
                status="acknowledged",
                response=response_text,
                resulting_item_version=context.resulting_version,
            )

        return await execute_governed_command(
            session,
            envelope,
            load_item=load_item,
            check_capability=check_capability,
            validate_domain=validate_domain,
            current_version=lambda item: item.version,
            lookup_receipt=lookup_receipt,
            commit_provisional=commit_provisional,
            persist_receipt=persist_receipt,
            build_audit=build_audit,
            append_audit=append_audit,
            load_replay_result=load_replay_result,
            project_result=project_result,
        )


__all__ = [
    "DraftReferralCommand",
    "SubmitReferralCommand",
    "AcknowledgeReferralCommand",
    "ReferralService",
    "PersistedReferral",
    "insert_outbox_event",
]

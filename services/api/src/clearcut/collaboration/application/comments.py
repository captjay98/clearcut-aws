"""Application services for the persisted collaboration comment slice.

Three attributable, versioned writes live here — adding a comment, replying to
a comment (one level only), and revising a comment — each performed by an *active
authorized project member*. Comments remain operational collaboration records,
not legal conclusions, but every command uses the shared governed-command
choreography: exact item scope, expected-version compare-and-swap, durable
idempotency receipt, authoritative audit event, and schema-versioned deduplicated
outbox event all commit or roll back in the caller's single transaction.

The transactional unit includes:

* the comment (or reply) row plus its immutable revision and mention rows,
* the accountable command receipt and item version advance,
* the authoritative audit event through the typed
  :class:`~clearcut.commanding.domain.AuditPayload` seam, and
* a schema-versioned, deduplicated outbox event.

Safety invariants enforced here rather than assumed:

* **Active-member requirement.** The author must be an active member of the
  organization; a non-member or deactivated member is a typed
  :class:`~clearcut.commanding.errors.CommandForbiddenError`. Every project role
  holds ``project:read``, so participation is the gate — no role beyond active
  membership is required to comment.
* **Single reply level.** A reply carries ``reply_depth = 1`` and
  ``parent_reply_depth = 0``; the database rejects a reply-to-reply, which the
  adapter surfaces as a typed
  :class:`~clearcut.commanding.errors.CommandValidationError` (never a 500).
* **Immutable parent identity.** A reply's parent is fixed at creation; a
  revision only appends a new revision row and never rewrites the parent linkage.
* **Append-only revisions.** A revision appends at ``latest_ordinal + 1``; the
  original ordinal-1 body is never overwritten.
* **Authorized mentions.** Mention recipients are recipient *user IDs* only
  (usernames in the body are never parsed as authority), must resolve to active
  authorized members, exclude the actor, and are deduplicated. A requested
  recipient that is not active in scope receives the same neutral typed not-found
  error as an absent recipient, preventing membership disclosure.

Only typed results or typed governed-command errors cross the boundary; no
booleans, ``None`` sentinels, or raw dicts encode decisions, and no comment ever
asserts a legal conclusion.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from clearcut.collaboration.ports.repository import (
    CollaborationRepositoryPort,
    PendingOutboxEvent,
    PersistedComment,
    ScopedComment,
    ScopedItem,
)
from clearcut.commanding.domain import AuditPayload, CommandEnvelope, PriorReceipt
from clearcut.commanding.errors import (
    CommandForbiddenError,
    CommandNotFoundError,
    CommandValidationError,
    IdempotencyIntentConflictError,
)
from clearcut.commanding.sql import insert_authoritative_audit, lookup_command_receipt
from clearcut.commanding.template import (
    GovernedAudit,
    GovernedCommandContext,
    execute_governed_command,
)
from clearcut.organizations.domain.capabilities import has_capability
from sqlalchemy.ext.asyncio import AsyncSession

# Operational operation names that identify each comment write on the audit
# ledger and scope its (reused) command envelope.
_ADD_OPERATION = "comment.add"
_REPLY_OPERATION = "comment.reply"
_REVISE_OPERATION = "comment.revise"

# Participation gate: every project role (Owner/Admin/Editor/Reviewer) holds
# ``project:read``, so an active member with any role may comment. Authoring is
# not gated on a governed capability because a comment is operational, not a
# governed legal action.
_PARTICIPATION_CAPABILITY = "project:read"

_AUDIT_TARGET_TYPE = "comment"
_ADD_AUDIT_ACTION = "comment.added"
_REPLY_AUDIT_ACTION = "comment.replied"
_REVISE_AUDIT_ACTION = "comment.revised"

# Outbox event identity. The schema version lets downstream consumers evolve the
# payload shape without ambiguity; the dedupe key makes the staged event unique
# within the tenant so a write can never enqueue twice.
_OUTBOX_SCHEMA_VERSION = 1
_ADD_EVENT_TYPE = "comment_added.v1"
_REPLY_EVENT_TYPE = "comment_replied.v1"
_REVISE_EVENT_TYPE = "comment_revised.v1"


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

    Delegates to the repository's session-bound ``stage_outbox_event`` within the
    caller's transaction. Defined as a module-level seam so the outbox write is
    patchable at this boundary; the behavioral rollback tests inject a failure
    here to prove the whole command rolls back atomically.
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
class AddCommentCommand:
    """A validated request to add a root comment on an exact clearance item.

    ``actor_role`` is the server-derived membership role; capability is never
    taken from the client. ``mention_user_ids`` are recipient user IDs only — the
    service never parses ``@username`` tokens from ``content`` as mention
    authority.
    """

    org_id: UUID
    project_id: UUID
    item_id: UUID
    actor_id: UUID
    actor_role: str
    content: str
    mention_user_ids: tuple[UUID, ...]
    expected_version: int
    intent_hash: str
    idempotency_key: str


@dataclass(frozen=True)
class ReplyToCommentCommand:
    """A validated request to reply once to an existing comment."""

    org_id: UUID
    project_id: UUID
    item_id: UUID
    parent_comment_id: UUID
    actor_id: UUID
    actor_role: str
    content: str
    mention_user_ids: tuple[UUID, ...]
    expected_version: int
    intent_hash: str
    idempotency_key: str


@dataclass(frozen=True)
class ReviseCommentCommand:
    """A validated request to append an immutable revision to a comment."""

    org_id: UUID
    project_id: UUID
    item_id: UUID
    comment_id: UUID
    actor_id: UUID
    actor_role: str
    content: str
    mention_user_ids: tuple[UUID, ...]
    expected_version: int
    intent_hash: str
    idempotency_key: str


class CommentService:
    """Coordinates add/reply/revise comment writes transactionally.

    This is the persisted, governed-infrastructure-backed comment service that
    supersedes the in-memory prototype for the runtime comment path.
    """

    def __init__(self, repository: CollaborationRepositoryPort) -> None:
        self._repository = repository

    async def add(
        self,
        session: AsyncSession,
        command: AddCommentCommand,
    ) -> PersistedComment:
        content = _require_content(command.content)
        envelope = CommandEnvelope(
            org_id=command.org_id,
            project_id=command.project_id,
            actor_id=command.actor_id,
            operation=_ADD_OPERATION,
            idempotency_key=command.idempotency_key,
            intent_hash=command.intent_hash,
            expected_version=command.expected_version,
        )
        await self._require_active_authorized_member(
            session,
            org_id=command.org_id,
            project_id=command.project_id,
            actor_id=command.actor_id,
            actor_role=command.actor_role,
        )
        recipients: tuple[UUID, ...] = ()

        async def load_item(session: AsyncSession, _envelope: CommandEnvelope) -> ScopedItem:
            return await self._repository.load_scoped_item(
                session,
                org_id=command.org_id,
                project_id=command.project_id,
                item_id=command.item_id,
            )

        def check_capability() -> None:
            return None

        def validate_domain(_item: ScopedItem) -> None:
            return None

        async def lookup_receipt(session: AsyncSession, envelope: CommandEnvelope):
            return await lookup_command_receipt(session, envelope)

        async def commit_provisional(
            session: AsyncSession,
            context: GovernedCommandContext[ScopedItem],
        ) -> None:
            nonlocal recipients
            recipients = await self._resolve_recipients(
                session,
                org_id=command.org_id,
                project_id=command.project_id,
                actor_id=command.actor_id,
                requested=command.mention_user_ids,
            )
            await self._repository.insert_comment(
                session,
                comment_id=context.result_id,
                org_id=command.org_id,
                project_id=command.project_id,
                item_id=command.item_id,
                author_id=command.actor_id,
                parent_comment_id=None,
                parent_reply_depth=None,
                reply_depth=0,
                body=content,
                recipient_user_ids=recipients,
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
                result_id=context.result_id,
                occurred_at=context.occurred_at,
            )

        def build_audit(context: GovernedCommandContext[ScopedItem]) -> GovernedAudit:
            return GovernedAudit(
                action=_ADD_AUDIT_ACTION,
                target_type=_AUDIT_TARGET_TYPE,
                target_id=context.result_id,
                payload=AuditPayload(
                    {
                        "commentId": str(context.result_id),
                        "itemId": str(command.item_id),
                        "recipientUserIds": [str(uid) for uid in recipients],
                        "expectedVersion": context.item.version,
                        "resultingVersion": context.resulting_version,
                    }
                ),
            )

        async def append_audit(
            session: AsyncSession,
            envelope: CommandEnvelope,
            audit: GovernedAudit,
            correlation_id: UUID,
            occurred_at: datetime,
        ) -> None:
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
                event_type=_ADD_EVENT_TYPE,
                schema_version=_OUTBOX_SCHEMA_VERSION,
                dedupe_key=f"{_ADD_OPERATION}:{audit.target_id}",
                payload={
                    "commentId": str(audit.target_id),
                    "itemId": str(command.item_id),
                    "recipientUserIds": [str(uid) for uid in recipients],
                },
                occurred_at=occurred_at,
            )

        def project(
            comment_id: UUID,
            resulting_version: int,
            created_at: datetime,
        ) -> PersistedComment:
            return PersistedComment(
                comment_id=comment_id,
                org_id=command.org_id,
                project_id=command.project_id,
                item_id=command.item_id,
                author_id=command.actor_id,
                parent_comment_id=None,
                reply_depth=0,
                ordinal=1,
                recipient_user_ids=recipients,
                body=content,
                resulting_item_version=resulting_version,
                created_at=created_at,
            )

        async def load_replay_result(
            session: AsyncSession,
            _envelope: CommandEnvelope,
            prior: PriorReceipt,
        ) -> PersistedComment:
            if prior.item_id != command.item_id:
                raise IdempotencyIntentConflictError()
            result = await self._repository.load_persisted_comment_result(
                session,
                org_id=command.org_id,
                project_id=command.project_id,
                item_id=prior.item_id,
                comment_id=prior.result_id,
                resulting_item_version=prior.resulting_version,
            )
            if (
                isinstance(command, ReplyToCommentCommand)
                and result.parent_comment_id != command.parent_comment_id
            ):
                raise IdempotencyIntentConflictError()
            return result

        def project_result(context: GovernedCommandContext[ScopedItem]) -> PersistedComment:
            return project(
                context.result_id,
                context.resulting_version,
                context.occurred_at,
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

    async def reply(
        self,
        session: AsyncSession,
        command: ReplyToCommentCommand,
    ) -> PersistedComment:
        content = _require_content(command.content)
        envelope = CommandEnvelope(
            org_id=command.org_id,
            project_id=command.project_id,
            actor_id=command.actor_id,
            operation=_REPLY_OPERATION,
            idempotency_key=command.idempotency_key,
            intent_hash=command.intent_hash,
            expected_version=command.expected_version,
        )
        await self._require_active_authorized_member(
            session,
            org_id=command.org_id,
            project_id=command.project_id,
            actor_id=command.actor_id,
            actor_role=command.actor_role,
        )
        parent: ScopedComment | None = None
        recipients: tuple[UUID, ...] = ()

        async def load_item(session: AsyncSession, _envelope: CommandEnvelope) -> ScopedItem:
            return await self._repository.load_scoped_item(
                session,
                org_id=command.org_id,
                project_id=command.project_id,
                item_id=command.item_id,
            )

        def check_capability() -> None:
            return None

        def validate_domain(_item: ScopedItem) -> None:
            return None

        def resolved_parent() -> ScopedComment:
            if parent is None:
                raise RuntimeError("Reply parent was not loaded on the fresh path.")
            return parent

        async def lookup_receipt(session: AsyncSession, envelope: CommandEnvelope):
            return await lookup_command_receipt(session, envelope)

        async def commit_provisional(
            session: AsyncSession,
            context: GovernedCommandContext[ScopedItem],
        ) -> None:
            nonlocal parent, recipients
            parent = await self._repository.load_scoped_comment(
                session,
                org_id=command.org_id,
                project_id=command.project_id,
                item_id=command.item_id,
                comment_id=command.parent_comment_id,
            )
            if resolved_parent().reply_depth != 0:
                raise CommandValidationError(
                    "A reply may only attach to a top-level comment."
                )
            recipients = await self._resolve_recipients(
                session,
                org_id=command.org_id,
                project_id=command.project_id,
                actor_id=command.actor_id,
                requested=command.mention_user_ids,
            )
            await self._repository.insert_comment(
                session,
                comment_id=context.result_id,
                org_id=command.org_id,
                project_id=command.project_id,
                item_id=command.item_id,
                author_id=command.actor_id,
                parent_comment_id=resolved_parent().comment_id,
                parent_reply_depth=resolved_parent().reply_depth,
                reply_depth=1,
                body=content,
                recipient_user_ids=recipients,
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
                result_id=context.result_id,
                occurred_at=context.occurred_at,
            )

        def build_audit(context: GovernedCommandContext[ScopedItem]) -> GovernedAudit:
            assert parent is not None  # noqa: S101 - fresh-path invariant
            return GovernedAudit(
                action=_REPLY_AUDIT_ACTION,
                target_type=_AUDIT_TARGET_TYPE,
                target_id=context.result_id,
                payload=AuditPayload(
                    {
                        "commentId": str(context.result_id),
                        "itemId": str(command.item_id),
                        "parentId": str(resolved_parent().comment_id),
                        "recipientUserIds": [str(uid) for uid in recipients],
                        "expectedVersion": context.item.version,
                        "resultingVersion": context.resulting_version,
                    }
                ),
            )

        async def append_audit(
            session: AsyncSession,
            envelope: CommandEnvelope,
            audit: GovernedAudit,
            correlation_id: UUID,
            occurred_at: datetime,
        ) -> None:
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
                event_type=_REPLY_EVENT_TYPE,
                schema_version=_OUTBOX_SCHEMA_VERSION,
                dedupe_key=f"{_REPLY_OPERATION}:{audit.target_id}",
                payload={
                    "commentId": str(audit.target_id),
                    "itemId": str(command.item_id),
                    "parentId": str(resolved_parent().comment_id),
                    "recipientUserIds": [str(uid) for uid in recipients],
                },
                occurred_at=occurred_at,
            )

        def project(
            comment_id: UUID,
            resulting_version: int,
            created_at: datetime,
        ) -> PersistedComment:
            return PersistedComment(
                comment_id=comment_id,
                org_id=command.org_id,
                project_id=command.project_id,
                item_id=command.item_id,
                author_id=command.actor_id,
                parent_comment_id=resolved_parent().comment_id,
                reply_depth=1,
                ordinal=1,
                recipient_user_ids=recipients,
                body=content,
                resulting_item_version=resulting_version,
                created_at=created_at,
            )

        async def load_replay_result(
            session: AsyncSession,
            _envelope: CommandEnvelope,
            prior: PriorReceipt,
        ) -> PersistedComment:
            if prior.item_id != command.item_id:
                raise IdempotencyIntentConflictError()
            result = await self._repository.load_persisted_comment_result(
                session,
                org_id=command.org_id,
                project_id=command.project_id,
                item_id=prior.item_id,
                comment_id=prior.result_id,
                resulting_item_version=prior.resulting_version,
            )
            if (
                isinstance(command, ReplyToCommentCommand)
                and result.parent_comment_id != command.parent_comment_id
            ):
                raise IdempotencyIntentConflictError()
            return result

        def project_result(context: GovernedCommandContext[ScopedItem]) -> PersistedComment:
            return project(
                context.result_id,
                context.resulting_version,
                context.occurred_at,
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

    async def revise(
        self,
        session: AsyncSession,
        command: ReviseCommentCommand,
    ) -> PersistedComment:
        content = _require_content(command.content)
        envelope = CommandEnvelope(
            org_id=command.org_id,
            project_id=command.project_id,
            actor_id=command.actor_id,
            operation=_REVISE_OPERATION,
            idempotency_key=command.idempotency_key,
            intent_hash=command.intent_hash,
            expected_version=command.expected_version,
        )
        await self._require_active_authorized_member(
            session,
            org_id=command.org_id,
            project_id=command.project_id,
            actor_id=command.actor_id,
            actor_role=command.actor_role,
        )
        comment: ScopedComment | None = None
        recipients: tuple[UUID, ...] = ()
        next_ordinal = 0

        async def load_item(session: AsyncSession, _envelope: CommandEnvelope) -> ScopedItem:
            return await self._repository.load_scoped_item(
                session,
                org_id=command.org_id,
                project_id=command.project_id,
                item_id=command.item_id,
            )

        def check_capability() -> None:
            return None

        def validate_domain(_item: ScopedItem) -> None:
            return None

        def resolved_comment() -> ScopedComment:
            if comment is None:
                raise RuntimeError("Revised comment was not loaded on the fresh path.")
            return comment

        async def lookup_receipt(session: AsyncSession, envelope: CommandEnvelope):
            return await lookup_command_receipt(session, envelope)

        async def commit_provisional(
            session: AsyncSession,
            context: GovernedCommandContext[ScopedItem],
        ) -> None:
            nonlocal comment, recipients, next_ordinal
            comment = await self._repository.load_scoped_comment(
                session,
                org_id=command.org_id,
                project_id=command.project_id,
                item_id=command.item_id,
                comment_id=command.comment_id,
            )
            next_ordinal = comment.latest_ordinal + 1
            recipients = await self._resolve_recipients(
                session,
                org_id=command.org_id,
                project_id=command.project_id,
                actor_id=command.actor_id,
                requested=command.mention_user_ids,
            )
            await self._repository.append_comment_revision(
                session,
                revision_id=context.result_id,
                comment_id=resolved_comment().comment_id,
                org_id=command.org_id,
                project_id=command.project_id,
                item_id=command.item_id,
                author_id=command.actor_id,
                ordinal=next_ordinal,
                body=content,
                recipient_user_ids=recipients,
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
                result_id=context.result_id,
                occurred_at=context.occurred_at,
            )

        def build_audit(context: GovernedCommandContext[ScopedItem]) -> GovernedAudit:
            return GovernedAudit(
                action=_REVISE_AUDIT_ACTION,
                target_type=_AUDIT_TARGET_TYPE,
                target_id=resolved_comment().comment_id,
                payload=AuditPayload(
                    {
                        "commentId": str(resolved_comment().comment_id),
                        "revisionId": str(context.result_id),
                        "itemId": str(command.item_id),
                        "ordinal": next_ordinal,
                        "recipientUserIds": [str(uid) for uid in recipients],
                        "expectedVersion": context.item.version,
                        "resultingVersion": context.resulting_version,
                    }
                ),
            )

        async def append_audit(
            session: AsyncSession,
            envelope: CommandEnvelope,
            audit: GovernedAudit,
            correlation_id: UUID,
            occurred_at: datetime,
        ) -> None:
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
                event_type=_REVISE_EVENT_TYPE,
                schema_version=_OUTBOX_SCHEMA_VERSION,
                dedupe_key=(
                    f"{_REVISE_OPERATION}:{audit.payload.as_redacted()['revisionId']}"
                ),
                payload={
                    "commentId": str(resolved_comment().comment_id),
                    "itemId": str(command.item_id),
                    "ordinal": next_ordinal,
                    "recipientUserIds": [str(uid) for uid in recipients],
                },
                occurred_at=occurred_at,
            )

        def project(
            resulting_version: int,
            created_at: datetime,
        ) -> PersistedComment:
            return PersistedComment(
                comment_id=resolved_comment().comment_id,
                org_id=command.org_id,
                project_id=command.project_id,
                item_id=command.item_id,
                author_id=command.actor_id,
                parent_comment_id=resolved_comment().parent_comment_id,
                reply_depth=resolved_comment().reply_depth,
                ordinal=next_ordinal,
                recipient_user_ids=recipients,
                body=content,
                resulting_item_version=resulting_version,
                created_at=created_at,
            )

        async def load_replay_result(
            session: AsyncSession,
            _envelope: CommandEnvelope,
            prior: PriorReceipt,
        ) -> PersistedComment:
            if prior.item_id != command.item_id:
                raise IdempotencyIntentConflictError()
            result = await self._repository.load_persisted_revision_result(
                session,
                org_id=command.org_id,
                project_id=command.project_id,
                item_id=prior.item_id,
                revision_id=prior.result_id,
                resulting_item_version=prior.resulting_version,
            )
            if result.comment_id != command.comment_id:
                raise IdempotencyIntentConflictError()
            return result

        def project_result(context: GovernedCommandContext[ScopedItem]) -> PersistedComment:
            return project(context.resulting_version, context.occurred_at)

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

    async def _require_active_authorized_member(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        actor_id: UUID,
        actor_role: str,
    ) -> None:
        """Require an active member who participates in the project.

        Capability is derived from the server-provided role only. Active
        membership is confirmed against storage so a deactivated member — whose
        role string may still be present on the request scope — cannot comment.
        """
        if not has_capability(actor_role, _PARTICIPATION_CAPABILITY):
            raise CommandForbiddenError()
        await self._repository.load_active_project_member(
            session,
            org_id=org_id,
            project_id=project_id,
            user_id=actor_id,
        )

    async def _resolve_recipients(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        actor_id: UUID,
        requested: Sequence[UUID],
    ) -> tuple[UUID, ...]:
        """Resolve mention recipients to active authorized members.

        Deduplicates while preserving first-seen order, excludes the actor, and
        rejects any requested recipient that is not an active member with a
        neutral typed not-found error. Mentions are recipient user IDs only;
        usernames in the body carry no authority.
        """
        deduped: list[UUID] = []
        seen: set[UUID] = set()
        for candidate in requested:
            if candidate == actor_id or candidate in seen:
                continue
            seen.add(candidate)
            deduped.append(candidate)
        if not deduped:
            return ()
        active = await self._repository.filter_active_member_recipients(
            session,
            org_id=org_id,
            project_id=project_id,
            candidate_user_ids=tuple(deduped),
        )
        unauthorized = [uid for uid in deduped if uid not in active]
        if unauthorized:
            raise CommandNotFoundError()
        return tuple(deduped)

def _require_content(raw: str) -> str:
    """Return trimmed, non-empty content or raise a typed validation error."""
    if not isinstance(raw, str) or not raw.strip():
        raise CommandValidationError("A comment requires non-empty content.")
    return raw.strip()


__all__ = [
    "AddCommentCommand",
    "ReplyToCommentCommand",
    "ReviseCommentCommand",
    "CommentService",
    "PersistedComment",
    "insert_outbox_event",
]

"""Session-bound SQL adapter for the governed collaboration referral port.

Every statement here runs on the caller-provided
:class:`~sqlalchemy.ext.asyncio.AsyncSession` and never opens, commits, or rolls
back its own transaction, so the referral state transition, the item version
advance, the idempotency receipt, the authoritative audit event, and the outbox
event share one atomic unit of work. All reads and writes are constrained by the
full ``(org_id, project_id)`` tenant scope (and the ``item_id`` scope for
item-bound reads/writes), so a referral or item is never loaded or mutated
outside the authenticated organization-and-project scope. A missing or foreign
item or referral surfaces as a typed
:class:`~clearcut.commanding.errors.CommandNotFoundError` with the same neutral
shape, never a raw ``None`` or a distinguishing error.

Two concurrency branches are handled here, mirroring the governed
evidence-decision adapter, because they only fire under genuine interleaving
that the caller's sequential classification cannot pre-empt:

* When the version-guarded compare-and-swap affects zero rows, the row moved
  between load and update. The adapter re-checks scoped existence: a still
  present item is a typed
  :class:`~clearcut.commanding.errors.StaleVersionConflictError`, while a
  genuinely absent/foreign item keeps the neutral
  :class:`~clearcut.commanding.errors.CommandNotFoundError` parity.
* When the idempotency-receipt insert loses a unique-constraint race, the
  adapter rolls the failed insert back to a savepoint, re-reads the prior
  receipt under the kernel's documented caller re-read contract, and returns it
  so the caller replays the original idempotent result instead of surfacing a
  raw integrity error.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import sqlalchemy as sa
import uuid6
from clearcut.collaboration.ports.repository import (
    ActiveMember,
    PendingOutboxEvent,
    PersistedComment,
    ScopedComment,
    ScopedItem,
    ScopedReferral,
)
from clearcut.commanding.domain import CommandEnvelope, PriorReceipt
from clearcut.commanding.errors import (
    CommandForbiddenError,
    CommandNotFoundError,
    CommandValidationError,
    StaleVersionConflictError,
)
from clearcut.commanding.sql import insert_command_receipt, lookup_command_receipt
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import TextClause

_LOAD_SCOPED_ITEM = sa.text(
    """
    SELECT i.id, i.version_id, i.category, i.text, i.status, i.workflow_status,
           i.disposition_status, i.assigned_to_user_id, i.version,
           e.text AS context_text
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

_LOAD_DRAFT_BY_IDEMPOTENCY_KEY = sa.text(
    """
    SELECT r.id, r.item_id, r.target_role, r.question, r.notes, r.status,
           r.submitted_by_actor_id, r.acknowledged_by_actor_id,
           i.version AS item_version
    FROM governed_referrals r
    JOIN clearance_items i
      ON i.id = r.item_id AND i.org_id = r.org_id AND i.project_id = r.project_id
    WHERE r.org_id = :org_id
      AND r.project_id = :project_id
      AND r.idempotency_key = :idempotency_key
      AND r.status = 'draft'
    """
)

_LOAD_SUBMITTED_BY_IDEMPOTENCY_KEY = sa.text(
    """
    SELECT r.id, r.item_id, r.target_role, r.question, r.notes, r.status,
           r.submitted_by_actor_id, r.acknowledged_by_actor_id,
           i.version AS item_version
    FROM governed_referrals r
    JOIN clearance_items i
      ON i.id = r.item_id AND i.org_id = r.org_id AND i.project_id = r.project_id
    WHERE r.org_id = :org_id
      AND r.project_id = :project_id
      AND r.idempotency_key = :idempotency_key
      AND r.status <> 'draft'
    """
)

_LOAD_SCOPED_REFERRAL = sa.text(
    """
    SELECT r.id, r.item_id, r.target_role, r.question, r.notes, r.status,
           r.submitted_by_actor_id, r.acknowledged_by_actor_id,
           i.version AS item_version
    FROM governed_referrals r
    JOIN clearance_items i
      ON i.id = r.item_id AND i.org_id = r.org_id AND i.project_id = r.project_id
    WHERE r.id = :referral_id
      AND r.item_id = :item_id
      AND r.org_id = :org_id
      AND r.project_id = :project_id
    """
)

_ACTIVE_MEMBER_WITH_ROLE = sa.text(
    """
    SELECT m.role FROM memberships m
    WHERE m.org_id = :org_id AND m.user_id = :user_id
      AND m.role = :role AND m.status = 'active'
    """
)

_ACTIVE_MEMBER = sa.text(
    """
    SELECT m.role FROM memberships m
    WHERE m.org_id = :org_id AND m.user_id = :user_id AND m.status = 'active'
      AND (
        m.role IN ('owner', 'admin')
        OR EXISTS (
          SELECT 1 FROM project_grants pg
          WHERE pg.membership_id = m.id
            AND pg.org_id = m.org_id
            AND pg.project_id = :project_id
        )
      )
    """
)

_ACTIVE_MEMBERS_IN = sa.text(
    """
    SELECT m.user_id FROM memberships m
    WHERE m.org_id = :org_id AND m.status = 'active'
      AND (
        m.role IN ('owner', 'admin')
        OR EXISTS (
          SELECT 1 FROM project_grants pg
          WHERE pg.membership_id = m.id
            AND pg.org_id = m.org_id
            AND pg.project_id = :project_id
        )
      )
    """
)

_LOAD_SCOPED_COMMENT = sa.text(
    """
    SELECT c.id, c.item_id, c.author_id, c.parent_comment_id, c.reply_depth,
           COALESCE(MAX(r.ordinal), 0) AS latest_ordinal
    FROM governed_comments c
    LEFT JOIN governed_comment_revisions r
      ON r.comment_id = c.id AND r.org_id = c.org_id AND r.project_id = c.project_id
    WHERE c.id = :comment_id AND c.item_id = :item_id
      AND c.org_id = :org_id AND c.project_id = :project_id
    GROUP BY c.id, c.item_id, c.author_id, c.parent_comment_id, c.reply_depth
    """
)

_LOAD_COMMENT_RESULT = sa.text(
    """
    SELECT c.id AS comment_id, c.item_id, r.id AS revision_id, r.author_id,
           c.parent_comment_id, c.reply_depth, r.ordinal, r.body, r.created_at
    FROM governed_comments c
    JOIN governed_comment_revisions r
      ON r.comment_id = c.id AND r.org_id = c.org_id AND r.project_id = c.project_id
    WHERE c.id = :result_id AND r.ordinal = 1 AND c.item_id = :item_id
      AND c.org_id = :org_id AND c.project_id = :project_id
    """
)

_LOAD_REVISION_RESULT = sa.text(
    """
    SELECT c.id AS comment_id, c.item_id, r.id AS revision_id, r.author_id,
           c.parent_comment_id, c.reply_depth, r.ordinal, r.body, r.created_at
    FROM governed_comment_revisions r
    JOIN governed_comments c
      ON c.id = r.comment_id AND c.org_id = r.org_id AND c.project_id = r.project_id
    WHERE r.id = :result_id AND c.item_id = :item_id
      AND r.org_id = :org_id AND r.project_id = :project_id
    """
)

_LOAD_COMMENT_MENTIONS = sa.text(
    """
    SELECT recipient_user_id
    FROM governed_comment_mentions
    WHERE revision_id = :revision_id AND comment_id = :comment_id
      AND org_id = :org_id AND project_id = :project_id
    ORDER BY created_at, id
    """
)

_INSERT_COMMENT = sa.text(
    """
    INSERT INTO governed_comments (
        id, org_id, project_id, item_id, author_id, parent_comment_id,
        parent_reply_depth, reply_depth, created_at
    ) VALUES (
        :id, :org_id, :project_id, :item_id, :author_id, :parent_comment_id,
        :parent_reply_depth, :reply_depth, :created_at
    )
    """
)

_INSERT_COMMENT_REVISION = sa.text(
    """
    INSERT INTO governed_comment_revisions (
        id, org_id, project_id, comment_id, author_id, ordinal, body, created_at
    ) VALUES (
        :id, :org_id, :project_id, :comment_id, :author_id, :ordinal, :body, :created_at
    )
    """
)

_INSERT_COMMENT_MENTION = sa.text(
    """
    INSERT INTO governed_comment_mentions (
        id, org_id, project_id, comment_id, revision_id, recipient_user_id, created_at
    ) VALUES (
        :id, :org_id, :project_id, :comment_id, :revision_id,
        :recipient_user_id, :created_at
    )
    """
)

_INSERT_REFERRAL = sa.text(
    """
    INSERT INTO governed_referrals (
        id, org_id, project_id, item_id, target_role, question, notes,
        submitted_by_actor_id, acknowledged_by_actor_id, status,
        submitted_at, acknowledged_at, idempotency_key
    ) VALUES (
        :id, :org_id, :project_id, :item_id, :target_role, :question, :notes,
        :submitted_by_actor_id, NULL, :status,
        :submitted_at, NULL, :idempotency_key
    )
    """
)

_ADVANCE_ITEM_VERSION = sa.text(
    """
    UPDATE clearance_items
    SET version = :resulting_version
    WHERE id = :item_id AND org_id = :org_id AND project_id = :project_id
      AND version = :expected_version
    """
)

_ADVANCE_ITEM_WORKFLOW = sa.text(
    """
    UPDATE clearance_items
    SET version = :resulting_version, workflow_status = :workflow_status
    WHERE id = :item_id AND org_id = :org_id AND project_id = :project_id
      AND version = :expected_version
    """
)

# Acknowledgement transitions only a currently ``submitted`` referral, so a
# double-acknowledge of an already-acknowledged referral cannot overwrite the
# authoritative acknowledging actor/time.
_ACKNOWLEDGE_REFERRAL = sa.text(
    """
    UPDATE governed_referrals
    SET status = 'acknowledged',
        acknowledged_by_actor_id = :acknowledged_by_actor_id,
        acknowledged_at = :acknowledged_at
    WHERE id = :referral_id
      AND org_id = :org_id
      AND project_id = :project_id
      AND status = 'submitted'
    """
)

_INSERT_OUTBOX = sa.text(
    """
    INSERT INTO governed_outbox (
        id, org_id, project_id, event_type, schema_version, dedupe_key,
        payload, created_at, processed_at
    ) VALUES (
        :id, :org_id, :project_id, :event_type, :schema_version, :dedupe_key,
        :payload, :created_at, NULL
    )
    """
).bindparams(sa.bindparam("payload", type_=sa.JSON()))


class SqlCollaborationRepository:
    """SQL implementation of :class:`CollaborationRepositoryPort`."""

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
            workflow_status=str(row["workflow_status"]),
            disposition_status=(
                str(row["disposition_status"]) if row["disposition_status"] is not None else None
            ),
            assigned_to_user_id=_as_optional_uuid(row["assigned_to_user_id"]),
            context_text=(str(row["context_text"]) if row["context_text"] is not None else None),
            version=int(row["version"]),
        )

    async def load_scoped_referral(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        referral_id: UUID,
    ) -> ScopedReferral:
        row = (
            (
                await session.execute(
                    _LOAD_SCOPED_REFERRAL,
                    {
                        "referral_id": str(referral_id),
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
        return ScopedReferral(
            referral_id=_as_uuid(row["id"]),
            org_id=org_id,
            project_id=project_id,
            item_id=_as_uuid(row["item_id"]),
            target_role=str(row["target_role"]),
            question=str(row["question"]),
            notes=(str(row["notes"]) if row["notes"] is not None else None),
            status=str(row["status"]),
            submitted_by_actor_id=_as_uuid(row["submitted_by_actor_id"]),
            acknowledged_by_actor_id=_as_optional_uuid(row["acknowledged_by_actor_id"]),
            response=None,
            item_version=int(row["item_version"]),
        )

    async def _load_referral_by_idempotency_key(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        idempotency_key: str,
    ) -> ScopedReferral | None:
        """Re-read a non-draft referral persisted under this idempotency key.

        Used by the submit path to disambiguate a lost version compare-and-swap:
        when a referral already exists under this exact idempotency scope, the
        version race we lost is our own duplicate, so the caller returns and lets
        the receipt guard drive the idempotent replay rather than surfacing a raw
        integrity error. Returns ``None`` when no submitted referral carries the
        key.
        """
        row = (
            (
                await session.execute(
                    _LOAD_SUBMITTED_BY_IDEMPOTENCY_KEY,
                    {
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                        "idempotency_key": idempotency_key,
                    },
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        return ScopedReferral(
            referral_id=_as_uuid(row["id"]),
            org_id=org_id,
            project_id=project_id,
            item_id=_as_uuid(row["item_id"]),
            target_role=str(row["target_role"]),
            question=str(row["question"]),
            notes=(str(row["notes"]) if row["notes"] is not None else None),
            status=str(row["status"]),
            submitted_by_actor_id=_as_uuid(row["submitted_by_actor_id"]),
            acknowledged_by_actor_id=_as_optional_uuid(row["acknowledged_by_actor_id"]),
            response=None,
            item_version=int(row["item_version"]),
        )

    async def _load_draft_by_idempotency_key(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        idempotency_key: str,
    ) -> ScopedReferral | None:
        """Re-read the ``draft`` already persisted under this idempotency key.

        Used to replay a same-key draft re-issue: returns the prior draft as a
        typed :class:`ScopedReferral`, or ``None`` when no draft carries the key
        so the caller performs a fresh insert.
        """
        row = (
            (
                await session.execute(
                    _LOAD_DRAFT_BY_IDEMPOTENCY_KEY,
                    {
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                        "idempotency_key": idempotency_key,
                    },
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        return ScopedReferral(
            referral_id=_as_uuid(row["id"]),
            org_id=org_id,
            project_id=project_id,
            item_id=_as_uuid(row["item_id"]),
            target_role=str(row["target_role"]),
            question=str(row["question"]),
            notes=(str(row["notes"]) if row["notes"] is not None else None),
            status=str(row["status"]),
            submitted_by_actor_id=_as_uuid(row["submitted_by_actor_id"]),
            acknowledged_by_actor_id=_as_optional_uuid(row["acknowledged_by_actor_id"]),
            response=None,
            item_version=int(row["item_version"]),
        )

    async def load_active_member_with_role(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        user_id: UUID,
        role: str,
    ) -> ActiveMember:
        active_role = (
            await session.execute(
                _ACTIVE_MEMBER_WITH_ROLE,
                {"org_id": str(org_id), "user_id": str(user_id), "role": role},
            )
        ).scalar_one_or_none()
        if active_role is None:
            raise CommandForbiddenError()
        return ActiveMember(user_id=user_id, role=str(active_role))

    async def load_active_project_member(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        user_id: UUID,
    ) -> ActiveMember:
        active_role = (
            await session.execute(
                _ACTIVE_MEMBER,
                {
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                    "user_id": str(user_id),
                },
            )
        ).scalar_one_or_none()
        if active_role is None:
            raise CommandForbiddenError()
        return ActiveMember(user_id=user_id, role=str(active_role))

    async def load_scoped_comment(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        comment_id: UUID,
    ) -> ScopedComment:
        row = (
            (
                await session.execute(
                    _LOAD_SCOPED_COMMENT,
                    {
                        "comment_id": str(comment_id),
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
        return ScopedComment(
            comment_id=_as_uuid(row["id"]),
            org_id=org_id,
            project_id=project_id,
            item_id=_as_uuid(row["item_id"]),
            author_id=_as_uuid(row["author_id"]),
            parent_comment_id=_as_optional_uuid(row["parent_comment_id"]),
            reply_depth=int(row["reply_depth"]),
            latest_ordinal=int(row["latest_ordinal"]),
        )

    async def load_persisted_comment_result(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        comment_id: UUID,
        resulting_item_version: int,
    ) -> PersistedComment:
        return await self._load_persisted_comment_result(
            session,
            statement=_LOAD_COMMENT_RESULT,
            org_id=org_id,
            project_id=project_id,
            item_id=item_id,
            result_id=comment_id,
            resulting_item_version=resulting_item_version,
        )

    async def load_persisted_revision_result(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        revision_id: UUID,
        resulting_item_version: int,
    ) -> PersistedComment:
        return await self._load_persisted_comment_result(
            session,
            statement=_LOAD_REVISION_RESULT,
            org_id=org_id,
            project_id=project_id,
            item_id=item_id,
            result_id=revision_id,
            resulting_item_version=resulting_item_version,
        )

    async def _load_persisted_comment_result(
        self,
        session: AsyncSession,
        *,
        statement: TextClause,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        result_id: UUID,
        resulting_item_version: int,
    ) -> PersistedComment:
        row = (
            (
                await session.execute(
                    statement,
                    {
                        "result_id": str(result_id),
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
        comment_id = _as_uuid(row["comment_id"])
        recipients = (
            (
                await session.execute(
                    _LOAD_COMMENT_MENTIONS,
                    {
                        "revision_id": str(row["revision_id"]),
                        "comment_id": str(comment_id),
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                    },
                )
            )
            .scalars()
            .all()
        )
        return PersistedComment(
            comment_id=comment_id,
            org_id=org_id,
            project_id=project_id,
            item_id=_as_uuid(row["item_id"]),
            author_id=_as_uuid(row["author_id"]),
            parent_comment_id=_as_optional_uuid(row["parent_comment_id"]),
            reply_depth=int(row["reply_depth"]),
            ordinal=int(row["ordinal"]),
            recipient_user_ids=tuple(_as_uuid(value) for value in recipients),
            body=str(row["body"]),
            resulting_item_version=resulting_item_version,
            created_at=_as_aware_datetime(row["created_at"]),
        )

    async def filter_active_member_recipients(
        self,
        session: AsyncSession,
        *,
        org_id: UUID,
        project_id: UUID,
        candidate_user_ids: tuple[UUID, ...],
    ) -> frozenset[UUID]:
        if not candidate_user_ids:
            return frozenset()
        active = (
            (
                await session.execute(
                    _ACTIVE_MEMBERS_IN,
                    {"org_id": str(org_id), "project_id": str(project_id)},
                )
            )
            .scalars()
            .all()
        )
        active_ids = {_as_uuid(value) for value in active}
        return frozenset(uid for uid in candidate_user_ids if uid in active_ids)

    async def insert_comment(
        self,
        session: AsyncSession,
        *,
        comment_id: UUID,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        author_id: UUID,
        parent_comment_id: UUID | None,
        parent_reply_depth: int | None,
        reply_depth: int,
        body: str,
        recipient_user_ids: tuple[UUID, ...],
        expected_version: int,
        resulting_version: int,
        occurred_at: datetime,
    ) -> None:
        if not isinstance(occurred_at, datetime):
            raise TypeError("occurred_at must be a datetime.")
        version_result = await session.execute(
            _ADVANCE_ITEM_VERSION,
            {
                "resulting_version": resulting_version,
                "item_id": str(item_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "expected_version": expected_version,
            },
        )
        if cast(CursorResult[Any], version_result).rowcount != 1:
            await self.classify_cas_miss(
                session,
                org_id=org_id,
                project_id=project_id,
                item_id=item_id,
            )
        # The database enforces the single-reply-level guarantee: the composite
        # parent foreign key is bound to the parent's reply_depth and the
        # parent-is-root CHECK forces a reply's parent_reply_depth to 0, so a
        # reply to a depth-1 comment cannot satisfy both and fails at the DB. Any
        # such integrity failure is reclassified here as a typed
        # CommandValidationError; because the command then raises, the caller's
        # single transaction is rolled back in full, so no partial comment,
        # revision, or mention row survives. (A defensive savepoint is
        # deliberately not used: this is the unit of work's first write, and a
        # top-level SQLite savepoint would commit on release rather than nest
        # inside a not-yet-established outer transaction.)
        try:
            await session.execute(
                _INSERT_COMMENT,
                {
                    "id": str(comment_id),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                    "item_id": str(item_id),
                    "author_id": str(author_id),
                    "parent_comment_id": (
                        str(parent_comment_id) if parent_comment_id is not None else None
                    ),
                    "parent_reply_depth": parent_reply_depth,
                    "reply_depth": reply_depth,
                    "created_at": occurred_at,
                },
            )
            # Seed the first immutable revision (ordinal 1) with the original body.
            revision_id = uuid6.uuid7()
            await session.execute(
                _INSERT_COMMENT_REVISION,
                {
                    "id": str(revision_id),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                    "comment_id": str(comment_id),
                    "author_id": str(author_id),
                    "ordinal": 1,
                    "body": body,
                    "created_at": occurred_at,
                },
            )
            for recipient_user_id in recipient_user_ids:
                await session.execute(
                    _INSERT_COMMENT_MENTION,
                    {
                        "id": str(uuid6.uuid7()),
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                        "comment_id": str(comment_id),
                        "revision_id": str(revision_id),
                        "recipient_user_id": str(recipient_user_id),
                        "created_at": occurred_at,
                    },
                )
        except IntegrityError as error:
            raise CommandValidationError(
                "A reply may only attach to a top-level comment."
            ) from error

    async def append_comment_revision(
        self,
        session: AsyncSession,
        *,
        revision_id: UUID,
        comment_id: UUID,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        author_id: UUID,
        ordinal: int,
        body: str,
        recipient_user_ids: tuple[UUID, ...],
        expected_version: int,
        resulting_version: int,
        occurred_at: datetime,
    ) -> None:
        if not isinstance(occurred_at, datetime):
            raise TypeError("occurred_at must be a datetime.")
        version_result = await session.execute(
            _ADVANCE_ITEM_VERSION,
            {
                "resulting_version": resulting_version,
                "item_id": str(item_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "expected_version": expected_version,
            },
        )
        if cast(CursorResult[Any], version_result).rowcount != 1:
            await self.classify_cas_miss(
                session,
                org_id=org_id,
                project_id=project_id,
                item_id=item_id,
            )
        # Append-only: insert a new revision row. The original ordinal-1 body is
        # never updated or deleted, so the full attributable history is preserved.
        await session.execute(
            _INSERT_COMMENT_REVISION,
            {
                "id": str(revision_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "comment_id": str(comment_id),
                "author_id": str(author_id),
                "ordinal": ordinal,
                "body": body,
                "created_at": occurred_at,
            },
        )
        for recipient_user_id in recipient_user_ids:
            await session.execute(
                _INSERT_COMMENT_MENTION,
                {
                    "id": str(uuid6.uuid7()),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                    "comment_id": str(comment_id),
                    "revision_id": str(revision_id),
                    "recipient_user_id": str(recipient_user_id),
                    "created_at": occurred_at,
                },
            )

    async def insert_draft_referral(
        self,
        session: AsyncSession,
        *,
        referral_id: UUID,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        target_role: str,
        question: str,
        notes: str | None,
        submitted_by_actor_id: UUID,
        idempotency_key: str,
        occurred_at: datetime,
    ) -> ScopedReferral | None:
        """Insert a ``draft`` referral, replaying a prior same-key draft.

        A draft carries no command receipt of its own, so idempotency is
        reconciled here: the adapter first re-reads any existing ``draft`` under
        the same ``(org, project, idempotency_key)`` scope and, when one exists,
        returns it so the caller replays the original draft identity instead of
        writing a second row. A draft never advances the item version; it only
        records the brief. Returns ``None`` on a fresh insert, or the prior
        :class:`ScopedReferral` when the draft key was already used.
        """
        if not isinstance(occurred_at, datetime):
            raise TypeError("occurred_at must be a datetime.")
        prior = await self._load_draft_by_idempotency_key(
            session,
            org_id=org_id,
            project_id=project_id,
            idempotency_key=idempotency_key,
        )
        if prior is not None:
            return prior
        await session.execute(
            _INSERT_REFERRAL,
            {
                "id": str(referral_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "item_id": str(item_id),
                "target_role": target_role,
                "question": question,
                "notes": notes,
                "submitted_by_actor_id": str(submitted_by_actor_id),
                "status": "draft",
                "submitted_at": occurred_at,
                "idempotency_key": idempotency_key,
            },
        )
        return None

    async def insert_submitted_referral(
        self,
        session: AsyncSession,
        *,
        referral_id: UUID,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        target_role: str,
        question: str,
        notes: str | None,
        submitted_by_actor_id: UUID,
        idempotency_key: str,
        expected_version: int,
        resulting_version: int,
        occurred_at: datetime,
    ) -> None:
        if not isinstance(occurred_at, datetime):
            raise TypeError("occurred_at must be a datetime.")
        # Advance the item version first with the version-guarded compare-and-swap.
        # The compare-and-swap is a real write that establishes the outer
        # transaction and is the authoritative concurrency serializer: for a
        # given expected version exactly one concurrent writer wins it. Running
        # it before the referral insert also means a genuinely concurrent
        # same-key submit that lost the version race is disambiguated here —
        # a lost compare-and-swap that is actually our own idempotency key
        # replaying is reconciled into the receipt replay path rather than
        # colliding on ``uq_governed_referrals_idempotency`` and surfacing a raw
        # integrity error.
        result = await session.execute(
            _ADVANCE_ITEM_WORKFLOW,
            {
                "resulting_version": resulting_version,
                "workflow_status": "referred",
                "item_id": str(item_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "expected_version": expected_version,
            },
        )
        if cast(CursorResult[Any], result).rowcount != 1:
            # The compare-and-swap matched no row. Before classifying the miss as
            # a stale-version/not-found conflict, disambiguate a genuinely
            # concurrent same-key retry: if a referral already exists under this
            # exact idempotency scope, the version race we lost is our own
            # duplicate. Leave the item untouched and return so the receipt insert
            # that follows reconciles the duplicate into the idempotent replay
            # path (mirroring ``persist_receipt_idempotent``) rather than raising.
            prior = await self._load_referral_by_idempotency_key(
                session,
                org_id=org_id,
                project_id=project_id,
                idempotency_key=idempotency_key,
            )
            if prior is not None:
                return
            # Not our idempotency key: a real concurrent advance or a
            # genuinely absent/foreign item. Classify by scoped existence so a
            # still-present item is a stale-version conflict (409) while an
            # absent/foreign item keeps neutral not-found parity (404).
            await self.classify_cas_miss(
                session,
                org_id=org_id,
                project_id=project_id,
                item_id=item_id,
            )
        # We won the version race, so we are the sole submitter at this version.
        # The referral insert cannot collide on the idempotency key here (a
        # duplicate would have lost the compare-and-swap above), and the
        # compare-and-swap already established the outer transaction, so a plain
        # insert is safe and correct.
        await session.execute(
            _INSERT_REFERRAL,
            {
                "id": str(referral_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "item_id": str(item_id),
                "target_role": target_role,
                "question": question,
                "notes": notes,
                "submitted_by_actor_id": str(submitted_by_actor_id),
                "status": "submitted",
                "submitted_at": occurred_at,
                "idempotency_key": idempotency_key,
            },
        )

    async def acknowledge_referral(
        self,
        session: AsyncSession,
        *,
        referral_id: UUID,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        acknowledged_by_actor_id: UUID,
        response: str,
        expected_version: int,
        resulting_version: int,
        occurred_at: datetime,
    ) -> None:
        if not isinstance(occurred_at, datetime):
            raise TypeError("occurred_at must be a datetime.")
        # Transition only a currently submitted referral to acknowledged. The
        # ``response`` is recorded on the authoritative audit/outbox payload;
        # the referral row carries the acknowledging actor and time. The
        # application service enforces the terminal-state guard before this
        # method runs (a distinct-key acknowledge of an already-acknowledged
        # referral is rejected as a typed conflict on the fresh-command path),
        # so under normal flow the referral is in the submitted state here. The
        # ``status = 'submitted'`` predicate remains as defense in depth against
        # a concurrent double-acknowledge overwriting the authoritative
        # acknowledging actor/time; the item compare-and-swap below is the
        # authoritative concurrency guard and surfaces the correct typed
        # conflict, so the referral update is intentionally not force-classified
        # here.
        await session.execute(
            _ACKNOWLEDGE_REFERRAL,
            {
                "referral_id": str(referral_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "acknowledged_by_actor_id": str(acknowledged_by_actor_id),
                "acknowledged_at": occurred_at,
            },
        )
        result = await session.execute(
            _ADVANCE_ITEM_WORKFLOW,
            {
                "resulting_version": resulting_version,
                "workflow_status": "referral_acknowledged",
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

    async def stage_outbox_event(
        self,
        session: AsyncSession,
        event: PendingOutboxEvent,
    ) -> None:
        if not isinstance(event.occurred_at, datetime):
            raise TypeError("occurred_at must be a datetime.")
        await session.execute(
            _INSERT_OUTBOX,
            {
                "id": str(uuid6.uuid7()),
                "org_id": str(event.org_id),
                "project_id": str(event.project_id),
                "event_type": event.event_type,
                "schema_version": event.schema_version,
                "dedupe_key": event.dedupe_key,
                "payload": dict(event.payload),
                "created_at": event.occurred_at,
            },
        )


def _as_uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _as_optional_uuid(value: Any) -> UUID | None:
    if value is None:
        return None
    return _as_uuid(value)


__all__ = ["SqlCollaborationRepository"]



def _as_aware_datetime(value: Any) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed

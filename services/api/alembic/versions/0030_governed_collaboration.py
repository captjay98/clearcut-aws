"""Persist governed collaboration state, receipts, and tenant-scoped invariants.

Revision ID: 0030_governed_collaboration
Revises: 0029_job_list_pagination
Create Date: 2026-08-31 00:00:00.000000

This migration is additive and reversible. It introduces canonical governed
collaboration tables rather than mutating the legacy 0010-0012/0017 tables, and
adds an optimistic-concurrency ``version`` column to ``clearance_items`` with a
safe default so existing rows remain valid. Governed events target the existing
``authoritative_audit_events`` table; this migration deliberately introduces no
second audit table and never writes the legacy ``audit_events`` table.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0030_governed_collaboration"
down_revision: str | None = "0029_job_list_pagination"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    # 1. Optimistic-concurrency version on clearance items.
    # Add as non-null with a safe default so existing rows adopt version 1 and
    # future writes can compare-and-swap monotonically.
    with op.batch_alter_table("clearance_items") as batch_op:
        batch_op.add_column(
            sa.Column(
                "version",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )
    with op.batch_alter_table("clearance_items") as batch_op:
        batch_op.create_check_constraint("ck_clearance_items_version_positive", "version >= 1")

    # 2. Governed command receipts: accountable-trigger identity for governed
    # commands, unique per (org, project, actor, operation, idempotency_key).
    op.create_table(
        "governed_command_receipts",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("item_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.String(100), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("expected_version", sa.Integer(), nullable=False),
        sa.Column("resulting_version", sa.Integer(), nullable=False),
        sa.Column("intent_hash", sa.String(64), nullable=False),
        sa.Column("result_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "org_id",
            "project_id",
            "actor_id",
            "operation",
            "idempotency_key",
            name="uq_governed_command_receipts_idempotency",
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "project_id"],
            ["projects.org_id", "projects.id"],
            name="fk_governed_command_receipts_project_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["item_id", "org_id", "project_id"],
            [
                "clearance_items.id",
                "clearance_items.org_id",
                "clearance_items.project_id",
            ],
            name="fk_governed_command_receipts_item_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name="fk_governed_command_receipts_actor",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "idx_governed_command_receipts_item",
        "governed_command_receipts",
        ["org_id", "project_id", "item_id", "occurred_at"],
    )

    # 3. Versioned decision/disposition records.
    op.create_table(
        "governed_decision_records",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("item_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("decision_kind", sa.String(50), nullable=False),
        sa.Column("decision_value", sa.String(50), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("expected_version", sa.Integer(), nullable=False),
        sa.Column("resulting_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id", "project_id"],
            ["projects.org_id", "projects.id"],
            name="fk_governed_decision_records_project_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["item_id", "org_id", "project_id"],
            [
                "clearance_items.id",
                "clearance_items.org_id",
                "clearance_items.project_id",
            ],
            name="fk_governed_decision_records_item_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name="fk_governed_decision_records_actor",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "idx_governed_decision_records_item_history",
        "governed_decision_records",
        ["org_id", "project_id", "item_id", "created_at"],
    )

    # 4. Referral lifecycle.
    op.create_table(
        "governed_referrals",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("item_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("target_role", sa.String(50), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("submitted_by_actor_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("acknowledged_by_actor_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.UniqueConstraint(
            "org_id",
            "project_id",
            "idempotency_key",
            name="uq_governed_referrals_idempotency",
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "project_id"],
            ["projects.org_id", "projects.id"],
            name="fk_governed_referrals_project_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["item_id", "org_id", "project_id"],
            [
                "clearance_items.id",
                "clearance_items.org_id",
                "clearance_items.project_id",
            ],
            name="fk_governed_referrals_item_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["submitted_by_actor_id"],
            ["users.id"],
            name="fk_governed_referrals_submitting_actor",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["acknowledged_by_actor_id"],
            ["users.id"],
            name="fk_governed_referrals_acknowledging_actor",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "idx_governed_referrals_item",
        "governed_referrals",
        ["org_id", "project_id", "item_id", "submitted_at"],
    )

    # 5. Comments with immutable parent identity and a single reply level.
    op.create_table(
        "governed_comments",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("item_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("author_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_comment_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("reply_depth", sa.Integer(), nullable=False, server_default="0"),
        # Mirror of the referenced parent's reply_depth. NULL for roots. The composite
        # FK below binds this to the parent's actual depth, and the CHECK forces it to 0
        # for replies, so a reply can only attach to a root (depth 0). This makes a
        # grandchild reply structurally impossible rather than relying on a row-local rule.
        sa.Column("parent_reply_depth", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        # Self-scope uniqueness lets replies, revisions, and mentions carry a
        # composite FK that cannot cross org or project.
        sa.UniqueConstraint(
            "id",
            "org_id",
            "project_id",
            name="uq_governed_comments_scope",
        ),
        # Uniqueness including reply_depth lets the parent FK bind to the parent's depth,
        # so the referenced parent row's actual depth is enforced structurally.
        sa.UniqueConstraint(
            "id",
            "org_id",
            "project_id",
            "reply_depth",
            name="uq_governed_comments_depth_scope",
        ),
        # One reply level only: a reply's depth must be 1 and a root's depth 0.
        sa.CheckConstraint(
            "(parent_comment_id IS NULL AND reply_depth = 0) "
            "OR (parent_comment_id IS NOT NULL AND reply_depth = 1)",
            name="ck_governed_comments_single_reply_level",
        ),
        # A reply's parent must be a root: parent_reply_depth is 0 for replies and NULL
        # for roots. Combined with the composite parent FK on parent_reply_depth, this
        # forces the referenced parent to have reply_depth = 0. A reply to a depth-1
        # comment cannot satisfy both this CHECK (=0) and the FK (parent depth = 1),
        # so a grandchild reply fails with IntegrityError at the database.
        sa.CheckConstraint(
            "(parent_comment_id IS NULL AND parent_reply_depth IS NULL) "
            "OR (parent_comment_id IS NOT NULL AND parent_reply_depth = 0)",
            name="ck_governed_comments_parent_is_root",
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "project_id"],
            ["projects.org_id", "projects.id"],
            name="fk_governed_comments_project_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["item_id", "org_id", "project_id"],
            [
                "clearance_items.id",
                "clearance_items.org_id",
                "clearance_items.project_id",
            ],
            name="fk_governed_comments_item_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name="fk_governed_comments_author",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["parent_comment_id", "org_id", "project_id", "parent_reply_depth"],
            [
                "governed_comments.id",
                "governed_comments.org_id",
                "governed_comments.project_id",
                "governed_comments.reply_depth",
            ],
            name="fk_governed_comments_parent_scope",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "idx_governed_comments_item",
        "governed_comments",
        ["org_id", "project_id", "item_id", "created_at"],
    )

    # 6. Append-only immutable comment revisions.
    op.create_table(
        "governed_comment_revisions",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("comment_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("ordinal >= 1", name="ck_governed_comment_revisions_ordinal_positive"),
        sa.UniqueConstraint(
            "org_id",
            "project_id",
            "comment_id",
            "ordinal",
            name="uq_governed_comment_revisions_sequence",
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "project_id"],
            ["projects.org_id", "projects.id"],
            name="fk_governed_comment_revisions_project_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["comment_id", "org_id", "project_id"],
            [
                "governed_comments.id",
                "governed_comments.org_id",
                "governed_comments.project_id",
            ],
            name="fk_governed_comment_revisions_comment_scope",
            ondelete="CASCADE",
        ),
    )

    # 7. Mentions referencing recipient user IDs (never usernames).
    op.create_table(
        "governed_comment_mentions",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("comment_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("recipient_user_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "org_id",
            "project_id",
            "comment_id",
            "recipient_user_id",
            name="uq_governed_comment_mentions_recipient",
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "project_id"],
            ["projects.org_id", "projects.id"],
            name="fk_governed_comment_mentions_project_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["comment_id", "org_id", "project_id"],
            [
                "governed_comments.id",
                "governed_comments.org_id",
                "governed_comments.project_id",
            ],
            name="fk_governed_comment_mentions_comment_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recipient_user_id"],
            ["users.id"],
            name="fk_governed_comment_mentions_recipient",
            ondelete="CASCADE",
        ),
    )

    # 8. Outbox events with schema version and dedupe identity.
    op.create_table(
        "governed_outbox",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("dedupe_key", sa.String(255), nullable=False),
        sa.Column("payload", _json(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "org_id",
            "project_id",
            "dedupe_key",
            name="uq_governed_outbox_dedupe",
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "project_id"],
            ["projects.org_id", "projects.id"],
            name="fk_governed_outbox_project_scope",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "idx_governed_outbox_delivery",
        "governed_outbox",
        ["org_id", "project_id", "processed_at", "created_at"],
    )


def downgrade() -> None:
    # Reverse dependency order: indexes and child tables first, command tables
    # next, then the clearance_items version column.
    op.drop_index("idx_governed_outbox_delivery", table_name="governed_outbox")
    op.drop_table("governed_outbox")

    op.drop_table("governed_comment_mentions")
    op.drop_table("governed_comment_revisions")
    op.drop_index("idx_governed_comments_item", table_name="governed_comments")
    op.drop_table("governed_comments")

    op.drop_index("idx_governed_referrals_item", table_name="governed_referrals")
    op.drop_table("governed_referrals")

    op.drop_index(
        "idx_governed_decision_records_item_history",
        table_name="governed_decision_records",
    )
    op.drop_table("governed_decision_records")

    op.drop_index(
        "idx_governed_command_receipts_item",
        table_name="governed_command_receipts",
    )
    op.drop_table("governed_command_receipts")

    with op.batch_alter_table("clearance_items") as batch_op:
        batch_op.drop_constraint("ck_clearance_items_version_positive", type_="check")
        batch_op.drop_column("version")

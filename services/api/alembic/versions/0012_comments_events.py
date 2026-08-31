"""0012_comments_events

Revision ID: 0012_comments_events
Revises: 0011_decisions_assignments
Create Date: 2026-08-30 15:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

revision: str = "0012_comments_events"
down_revision: str | None = "0011_decisions_assignments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Comments table
    op.create_table(
        "comments",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "item_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("clearance_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "author_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "parent_comment_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("comments.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "mentions",
            sa.JSON().with_variant(ARRAY(sa.String(100)), "postgresql"),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("is_edited", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id", "project_id"],
            ["projects.org_id", "projects.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index("idx_comments_item", "comments", ["org_id", "project_id", "item_id"])

    # Collaboration outbox table
    op.create_table(
        "collaboration_outbox",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_outbox_pending", "collaboration_outbox", ["processed_at", "created_at"])


def downgrade() -> None:
    op.drop_table("collaboration_outbox")
    op.drop_table("comments")

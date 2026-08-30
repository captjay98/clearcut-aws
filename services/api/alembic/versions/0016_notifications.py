"""0016_notifications

Revision ID: 0016_notifications
Revises: 0015_monitoring
Create Date: 2026-08-30 15:30:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_notifications"
down_revision: str | None = "0015_monitoring"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "recipient_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tier", sa.String(50), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body_redacted", sa.Text(), nullable=False),
        sa.Column("destination_path", sa.Text(), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "idx_notifications_recipient",
        "notifications",
        ["recipient_id", "is_read", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("notifications")

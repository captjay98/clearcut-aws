"""0019_deletion

Revision ID: 0019_deletion
Revises: 0018_trust_learning
Create Date: 2026-08-30 15:35:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_deletion"
down_revision: str | None = "0018_trust_learning"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organization_deletion_schedules",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("scheduled_by", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("grace_ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "deletion_tombstones",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("state", sa.String(50), nullable=False),
        sa.Column(
            "reproducibility_loss_recorded",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column("purged_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("deletion_tombstones")
    op.drop_table("organization_deletion_schedules")

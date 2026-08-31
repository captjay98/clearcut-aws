"""0020_report_snapshots

Revision ID: 0020_report_snapshots
Revises: 0019_deletion
Create Date: 2026-08-30 15:58:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020_report_snapshots"
down_revision: str | None = "0019_deletion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "report_snapshots",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "script_version_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("script_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("content_hash", sa.String(100), nullable=False),
        sa.Column("binding_manifest", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id", "project_id"],
            ["projects.org_id", "projects.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "idx_report_snapshots_project",
        "report_snapshots",
        ["project_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("report_snapshots")

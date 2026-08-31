"""0014_version_lineage_rescan

Revision ID: 0014_version_lineage_rescan
Revises: 0013_rewrite_proposals
Create Date: 2026-08-30 15:24:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0014_version_lineage_rescan"
down_revision: str | None = "0013_rewrite_proposals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Script diffs table
    op.create_table(
        "script_diffs",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "before_version_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("script_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "after_version_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("script_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("diff_payload", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id", "project_id"],
            ["projects.org_id", "projects.id"],
            ondelete="CASCADE",
        ),
    )

    # Rescan jobs table
    op.create_table(
        "rescan_jobs",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "after_version_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("script_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("affected_count", sa.Integer(), nullable=False),
        sa.Column("saved_calls_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id", "project_id"],
            ["projects.org_id", "projects.id"],
            ondelete="CASCADE",
        ),
    )


def downgrade() -> None:
    op.drop_table("rescan_jobs")
    op.drop_table("script_diffs")

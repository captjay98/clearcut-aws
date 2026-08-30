"""0021_report_releases

Revision ID: 0021_report_releases
Revises: 0020_report_snapshots
Create Date: 2026-08-30 15:58:30.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_report_releases"
down_revision: str | None = "0020_report_snapshots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "report_releases",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "snapshot_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("report_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "released_by",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attestation", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id", "project_id"],
            ["projects.org_id", "projects.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "idx_report_releases_snapshot",
        "report_releases",
        ["snapshot_id"],
    )


def downgrade() -> None:
    op.drop_table("report_releases")

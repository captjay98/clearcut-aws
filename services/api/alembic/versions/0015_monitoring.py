"""0015_monitoring

Revision ID: 0015_monitoring
Revises: 0014_version_lineage_rescan
Create Date: 2026-08-30 15:29:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_monitoring"
down_revision: str | None = "0014_version_lineage_rescan"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Monitoring watches table
    op.create_table(
        "monitoring_watches",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "item_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("clearance_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("cadence", sa.String(50), nullable=False, server_default="daily"),
        sa.Column("watch_kind", sa.String(50), nullable=False, server_default="exact_source"),
        sa.Column("target_url", sa.Text(), nullable=True),
        sa.Column("query_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id", "project_id"],
            ["projects.org_id", "projects.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "idx_monitoring_watches_item",
        "monitoring_watches",
        ["org_id", "project_id", "item_id"],
    )

    # Monitoring runs table
    op.create_table(
        "monitoring_runs",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "watch_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("monitoring_watches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column(
            "new_snapshot_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("source_snapshots.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id", "project_id"],
            ["projects.org_id", "projects.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "idx_monitoring_runs_watch",
        "monitoring_runs",
        ["watch_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("monitoring_runs")
    op.drop_table("monitoring_watches")

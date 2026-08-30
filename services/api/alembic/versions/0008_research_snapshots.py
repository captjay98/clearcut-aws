"""0008_research_snapshots

Revision ID: 0008_research_snapshots
Revises: 0007_evaluation
Create Date: 2026-08-30 14:47:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_research_snapshots"
down_revision: str | None = "0007_evaluation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Research runs table
    op.create_table(
        "research_runs",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "item_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("clearance_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id", "project_id"],
            ["projects.org_id", "projects.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index("idx_research_runs_item", "research_runs", ["item_id"])

    # Research queries table
    op.create_table(
        "research_queries",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("research_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
    )
    op.create_index("idx_research_queries_run", "research_queries", ["run_id", "ordinal"])

    # Provider attempts table
    op.create_table(
        "provider_attempts",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("research_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("operation_kind", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("receipt_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_provider_attempts_run", "provider_attempts", ["run_id"])

    # Source snapshots table
    op.create_table(
        "source_snapshots",
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
            "run_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("research_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("publisher", sa.Text(), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("origin", sa.String(50), nullable=False),
        sa.Column("sha256_hash", sa.String(64), nullable=False),
        sa.Column("published_date", sa.String(50), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id", "project_id"],
            ["projects.org_id", "projects.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "idx_source_snapshots_item",
        "source_snapshots",
        ["org_id", "project_id", "item_id"],
    )


def downgrade() -> None:
    op.drop_table("source_snapshots")
    op.drop_table("provider_attempts")
    op.drop_table("research_queries")
    op.drop_table("research_runs")

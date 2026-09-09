"""Persist deterministic report artifacts and release uniqueness.

Revision ID: 0034_report_artifacts
Revises: 0033_comment_mention_scope
Create Date: 2026-08-31 05:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034_report_artifacts"
down_revision: str | None = "0033_comment_mention_scope"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "export_artifacts",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "snapshot_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("report_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("media_type", sa.String(100), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id", "project_id"],
            ["projects.org_id", "projects.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "snapshot_id",
            "media_type",
            name="uq_export_artifacts_snapshot_media_type",
        ),
    )
    op.create_index(
        "idx_export_artifacts_scope",
        "export_artifacts",
        ["org_id", "project_id", "snapshot_id"],
    )
    with op.batch_alter_table("report_releases") as batch_op:
        batch_op.create_unique_constraint(
            "uq_report_releases_snapshot",
            ["snapshot_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("report_releases") as batch_op:
        batch_op.drop_constraint(
            "uq_report_releases_snapshot",
            type_="unique",
        )
    op.drop_table("export_artifacts")

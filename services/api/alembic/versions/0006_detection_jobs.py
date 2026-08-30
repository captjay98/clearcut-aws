"""0006_detection_jobs

Revision ID: 0006_detection_jobs
Revises: 0005_script_versions
Create Date: 2026-08-30 14:39:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0006_detection_jobs"
down_revision: str | None = "0005_script_versions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Jobs table
    op.create_table(
        "jobs",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("job_type", sa.String(100), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("result", JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "org_id",
            "project_id",
            "idempotency_key",
            name="uq_jobs_idempotency",
        ),
    )
    op.create_index(
        "idx_jobs_lease",
        "jobs",
        ["status", "available_at", "lease_expires_at", "id"],
    )

    # Clearance items table
    op.create_table(
        "clearance_items",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("script_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("version_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("element_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id", "project_id"],
            ["projects.org_id", "projects.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "idx_clearance_items_project_created",
        "clearance_items",
        ["org_id", "project_id", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_table("clearance_items")
    op.drop_table("jobs")

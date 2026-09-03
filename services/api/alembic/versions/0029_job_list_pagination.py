"""Index tenant-scoped job keyset pagination.

Revision ID: 0029_job_list_pagination
Revises: 0028_project_production_details
Create Date: 2026-08-31 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0029_job_list_pagination"
down_revision: str | None = "0028_project_production_details"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "idx_jobs_project_created",
        "jobs",
        ["org_id", "project_id", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("idx_jobs_project_created", table_name="jobs")

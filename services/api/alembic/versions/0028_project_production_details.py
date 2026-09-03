"""Persist canonical production description fields on projects.

Revision ID: 0028_project_production_details
Revises: 0027_research_execution
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028_project_production_details"
down_revision: str | None = "0027_research_execution"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch:
        batch.add_column(sa.Column("production_type", sa.String(100), nullable=True))
        batch.add_column(sa.Column("production_stage", sa.String(100), nullable=True))
        batch.add_column(sa.Column("jurisdiction", sa.String(200), nullable=True))
        batch.add_column(sa.Column("target_lock_date", sa.Date(), nullable=True))
        batch.add_column(sa.Column("review_brief", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("projects") as batch:
        batch.drop_column("review_brief")
        batch.drop_column("target_lock_date")
        batch.drop_column("jurisdiction")
        batch.drop_column("production_stage")
        batch.drop_column("production_type")

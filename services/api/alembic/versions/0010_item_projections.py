"""0010_item_projections

Revision ID: 0010_item_projections
Revises: 0009_evidence_claims
Create Date: 2026-08-30 14:59:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_item_projections"
down_revision: str | None = "0009_evidence_claims"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add state tracking columns to clearance_items
    op.add_column(
        "clearance_items",
        sa.Column(
            "research_status",
            sa.String(50),
            nullable=False,
            server_default="not_started",
        ),
    )
    op.add_column(
        "clearance_items",
        sa.Column(
            "workflow_status",
            sa.String(50),
            nullable=False,
            server_default="open",
        ),
    )
    op.add_column(
        "clearance_items",
        sa.Column(
            "disposition_status",
            sa.String(50),
            nullable=False,
            server_default="undisposed",
        ),
    )
    op.add_column(
        "clearance_items",
        sa.Column(
            "assigned_to_user_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_clearance_items_projection",
        "clearance_items",
        ["org_id", "project_id", "category", "workflow_status"],
    )


def downgrade() -> None:
    op.drop_index("idx_clearance_items_projection", table_name="clearance_items")
    op.drop_column("clearance_items", "assigned_to_user_id")
    op.drop_column("clearance_items", "disposition_status")
    op.drop_column("clearance_items", "workflow_status")
    op.drop_column("clearance_items", "research_status")

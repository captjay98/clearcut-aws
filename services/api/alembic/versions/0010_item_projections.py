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
    with op.batch_alter_table("clearance_items") as batch_op:
        batch_op.add_column(
            sa.Column(
                "research_status",
                sa.String(50),
                nullable=False,
                server_default="not_started",
            ),
        )
        batch_op.add_column(
            sa.Column(
                "workflow_status",
                sa.String(50),
                nullable=False,
                server_default="open",
            ),
        )
        batch_op.add_column(
            sa.Column(
                "disposition_status",
                sa.String(50),
                nullable=False,
                server_default="undisposed",
            ),
        )
        batch_op.add_column(
            sa.Column(
                "assigned_to_user_id",
                sa.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_clearance_items_assigned_to_user_id"),
                nullable=True,
            ),
        )
        batch_op.create_index(
            "idx_clearance_items_projection",
            ["org_id", "project_id", "category", "workflow_status"],
        )


def downgrade() -> None:
    with op.batch_alter_table("clearance_items") as batch_op:
        batch_op.drop_index("idx_clearance_items_projection")
        batch_op.drop_column("assigned_to_user_id")
        batch_op.drop_column("disposition_status")
        batch_op.drop_column("workflow_status")
        batch_op.drop_column("research_status")

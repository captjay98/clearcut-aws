"""0017_audit_receipts

Revision ID: 0017_audit_receipts
Revises: 0016_notifications
Create Date: 2026-08-30 15:33:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017_audit_receipts"
down_revision: str | None = "0016_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "authoritative_audit_events",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("target_type", sa.String(100), nullable=False),
        sa.Column("target_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("payload_redacted", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "idx_authoritative_audit_org",
        "authoritative_audit_events",
        ["org_id", "occurred_at"],
    )

    op.create_table(
        "decision_receipts",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("decision_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("decision_type", sa.String(50), nullable=False),
        sa.Column("actor_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("decision_receipts")
    op.drop_table("authoritative_audit_events")

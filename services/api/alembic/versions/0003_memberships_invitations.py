"""0003_memberships_invitations

Revision ID: 0003_memberships_invitations
Revises: 0002_organizations_projects
Create Date: 2026-08-30 14:28:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_memberships_invitations"
down_revision: str | None = "0002_organizations_projects"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Invitations table
    op.create_table(
        "invitations",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "invited_by_user_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("token_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_invitations_org_email", "invitations", ["org_id", "email"])
    op.create_index("idx_invitations_token_hash", "invitations", ["token_hash"], unique=True)

    # Project grants table
    op.create_table(
        "project_grants",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "membership_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("memberships.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "org_id",
            "project_id",
            "membership_id",
            name="uq_project_grants_org_proj_member",
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "project_id"],
            ["projects.org_id", "projects.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "idx_project_grants_lookup",
        "project_grants",
        ["org_id", "project_id", "membership_id"],
    )


def downgrade() -> None:
    op.drop_table("project_grants")
    op.drop_table("invitations")

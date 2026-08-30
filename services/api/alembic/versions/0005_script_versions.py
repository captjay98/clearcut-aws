"""0005_script_versions

Revision ID: 0005_script_versions
Revises: 0004_import_artifacts
Create Date: 2026-08-30 14:36:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_script_versions"
down_revision: str | None = "0004_import_artifacts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Scripts table
    op.create_table(
        "scripts",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id", "project_id"],
            ["projects.org_id", "projects.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index("idx_scripts_project", "scripts", ["org_id", "project_id"])

    # Script versions table
    op.create_table(
        "script_versions",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "script_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("scripts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("parser_version", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "org_id",
            "project_id",
            "script_id",
            "ordinal",
            name="uq_script_versions_ordinal",
        ),
    )
    op.create_index(
        "idx_script_versions_lookup",
        "script_versions",
        ["org_id", "project_id", "script_id", "ordinal"],
    )

    # Script elements table
    op.create_table(
        "script_elements",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "version_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("script_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("element_type", sa.String(50), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("scene_number", sa.Integer(), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
    )
    op.create_index(
        "idx_script_elements_version_ord",
        "script_elements",
        ["version_id", "ordinal"],
    )

    # Element spans table
    op.create_table(
        "element_spans",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "element_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("script_elements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("start_char", sa.Integer(), nullable=False),
        sa.Column("end_char", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("tag", sa.String(50), nullable=True),
    )
    op.create_index("idx_element_spans_element", "element_spans", ["element_id"])


def downgrade() -> None:
    op.drop_table("element_spans")
    op.drop_table("script_elements")
    op.drop_table("script_versions")
    op.drop_table("scripts")

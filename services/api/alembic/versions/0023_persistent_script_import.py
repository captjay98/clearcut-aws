"""Persist screenplay import capabilities, parse records, and version bindings.

Revision ID: 0023_persistent_script_import
Revises: 0022_runtime_alignment
Create Date: 2026-08-31 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_persistent_script_import"
down_revision: str | None = "0022_runtime_alignment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("import_artifacts") as batch_op:
        batch_op.create_unique_constraint(
            "uq_import_artifacts_scope", ["id", "org_id", "project_id"]
        )
        batch_op.create_unique_constraint(
            "uq_import_artifacts_storage_path", ["storage_path"]
        )
        batch_op.create_check_constraint(
            "ck_import_artifacts_size_nonnegative", "size_bytes >= 0"
        )

    op.create_table(
        "import_upload_capabilities",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("nonce_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "id", "org_id", "project_id", name="uq_import_upload_capabilities_scope"
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "project_id"],
            ["projects.org_id", "projects.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "idx_import_upload_capabilities_expiry",
        "import_upload_capabilities",
        ["org_id", "project_id", "expires_at"],
    )

    op.create_table(
        "parse_runs",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by_user_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("parser_name", sa.String(100), nullable=False),
        sa.Column("parser_version", sa.String(50), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("scene_count", sa.Integer(), nullable=False),
        sa.Column("element_count", sa.Integer(), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=False),
        sa.Column("diagnostics_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "id", "org_id", "project_id", name="uq_parse_runs_scope"
        ),
        sa.UniqueConstraint(
            "org_id",
            "project_id",
            "artifact_id",
            name="uq_parse_runs_artifact",
        ),
        sa.CheckConstraint("scene_count >= 0", name="ck_parse_runs_scene_count"),
        sa.CheckConstraint("element_count >= 0", name="ck_parse_runs_element_count"),
        sa.ForeignKeyConstraint(
            ["org_id", "project_id"],
            ["projects.org_id", "projects.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id", "org_id", "project_id"],
            ["import_artifacts.id", "import_artifacts.org_id", "import_artifacts.project_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
    )
    op.create_index(
        "idx_parse_runs_project_created",
        "parse_runs",
        ["org_id", "project_id", "created_at"],
    )

    op.create_table(
        "parse_diagnostics",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("requires_acceptance", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id", "org_id", "project_id"],
            ["parse_runs.id", "parse_runs.org_id", "parse_runs.project_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "idx_parse_diagnostics_run",
        "parse_diagnostics",
        ["run_id", "line_number"],
    )

    op.create_table(
        "parse_warning_acceptances",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("accepted_by_user_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("diagnostics_hash", sa.String(64), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "org_id",
            "project_id",
            "run_id",
            name="uq_parse_warning_acceptances_run",
        ),
        sa.ForeignKeyConstraint(
            ["run_id", "org_id", "project_id"],
            ["parse_runs.id", "parse_runs.org_id", "parse_runs.project_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["accepted_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
    )

    with op.batch_alter_table("scripts") as batch_op:
        batch_op.add_column(sa.Column("current_slot", sa.String(20), nullable=True))

    connection = op.get_bind()
    project_scopes = connection.execute(
        sa.text("SELECT DISTINCT org_id, project_id FROM scripts")
    ).mappings().all()
    for scope in project_scopes:
        current_script_id = connection.execute(
            sa.text(
                "SELECT s.id FROM scripts s "
                "LEFT JOIN script_versions v ON v.script_id = s.id "
                "WHERE s.org_id = :org_id AND s.project_id = :project_id "
                "GROUP BY s.id, s.created_at "
                "ORDER BY COALESCE(MAX(v.created_at), s.created_at) DESC, s.id DESC "
                "LIMIT 1"
            ),
            {"org_id": scope["org_id"], "project_id": scope["project_id"]},
        ).scalar_one()
        connection.execute(
            sa.text("UPDATE scripts SET current_slot = 'current' WHERE id = :script_id"),
            {"script_id": current_script_id},
        )

    with op.batch_alter_table("scripts") as batch_op:
        batch_op.create_unique_constraint(
            "uq_scripts_current_per_project",
            ["org_id", "project_id", "current_slot"],
        )

    with op.batch_alter_table("script_versions") as batch_op:
        batch_op.add_column(
            sa.Column("import_artifact_id", sa.UUID(as_uuid=True), nullable=True)
        )
        batch_op.add_column(sa.Column("parse_run_id", sa.UUID(as_uuid=True), nullable=True))
        batch_op.create_unique_constraint(
            "uq_script_versions_parse_run", ["parse_run_id"]
        )
        batch_op.create_foreign_key(
            "fk_script_versions_import_artifact_scope",
            "import_artifacts",
            ["import_artifact_id", "org_id", "project_id"],
            ["id", "org_id", "project_id"],
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            "fk_script_versions_parse_run_scope",
            "parse_runs",
            ["parse_run_id", "org_id", "project_id"],
            ["id", "org_id", "project_id"],
            ondelete="RESTRICT",
        )

    with op.batch_alter_table("script_elements") as batch_op:
        batch_op.create_unique_constraint(
            "uq_script_elements_ordinal", ["version_id", "ordinal"]
        )


def downgrade() -> None:
    with op.batch_alter_table("script_elements") as batch_op:
        batch_op.drop_constraint("uq_script_elements_ordinal", type_="unique")

    with op.batch_alter_table("script_versions") as batch_op:
        batch_op.drop_constraint(
            "fk_script_versions_parse_run_scope", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "fk_script_versions_import_artifact_scope", type_="foreignkey"
        )
        batch_op.drop_constraint("uq_script_versions_parse_run", type_="unique")
        batch_op.drop_column("parse_run_id")
        batch_op.drop_column("import_artifact_id")

    with op.batch_alter_table("scripts") as batch_op:
        batch_op.drop_constraint(
            "uq_scripts_current_per_project", type_="unique"
        )
        batch_op.drop_column("current_slot")

    op.drop_table("parse_warning_acceptances")
    op.drop_index("idx_parse_diagnostics_run", table_name="parse_diagnostics")
    op.drop_table("parse_diagnostics")
    op.drop_index("idx_parse_runs_project_created", table_name="parse_runs")
    op.drop_table("parse_runs")
    op.drop_index(
        "idx_import_upload_capabilities_expiry",
        table_name="import_upload_capabilities",
    )
    op.drop_table("import_upload_capabilities")

    with op.batch_alter_table("import_artifacts") as batch_op:
        batch_op.drop_constraint(
            "ck_import_artifacts_size_nonnegative", type_="check"
        )
        batch_op.drop_constraint("uq_import_artifacts_storage_path", type_="unique")
        batch_op.drop_constraint("uq_import_artifacts_scope", type_="unique")

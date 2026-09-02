"""Align runtime records with canonical queue and provenance requirements.

Revision ID: 0022_runtime_alignment
Revises: 0021_report_releases
Create Date: 2026-08-31 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_runtime_alignment"
down_revision: str | None = "0021_report_releases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _require_parent_rows(table: str, parent: str, join_condition: str) -> None:
    """Stop before changing schema when historical rows cannot be aligned safely."""
    connection = op.get_bind()
    missing = connection.execute(
        sa.text(
            f"SELECT count(*) FROM {table} child "
            f"LEFT JOIN {parent} parent ON {join_condition} "
            "WHERE parent.id IS NULL"
        )
    ).scalar_one()
    if missing:
        raise RuntimeError(
            f"Cannot align {table}: {missing} row(s) have no matching {parent} parent. "
            "Repair or export those rows before upgrading."
        )


def _align_historical_scope() -> None:
    """Repair denormalized scope from authoritative parents without deleting data."""
    connection = op.get_bind()

    relationships = (
        ("jobs", "projects", "child.project_id = parent.id"),
        ("deterministic_gate_results", "jobs", "child.run_id = parent.id"),
        ("agent_evaluations", "jobs", "child.run_id = parent.id"),
        ("authoritative_audit_events", "users", "child.actor_id = parent.id"),
        ("script_versions", "scripts", "child.script_id = parent.id"),
        (
            "clearance_items",
            "script_elements",
            "child.element_id = parent.id AND child.version_id = parent.version_id",
        ),
        ("clearance_items", "script_versions", "child.version_id = parent.id"),
        ("research_runs", "clearance_items", "child.item_id = parent.id"),
        ("research_queries", "research_runs", "child.run_id = parent.id"),
        ("provider_attempts", "research_runs", "child.run_id = parent.id"),
        ("source_snapshots", "research_runs", "child.run_id = parent.id"),
        ("evidence_claims", "source_snapshots", "child.snapshot_id = parent.id"),
        ("evidence_conflicts", "clearance_items", "child.item_id = parent.id"),
        ("judge_verdicts", "agent_evaluations", "child.evaluation_id = parent.id"),
        ("report_snapshots", "script_versions", "child.script_version_id = parent.id"),
        ("report_releases", "report_snapshots", "child.snapshot_id = parent.id"),
    )
    for table, parent, join_condition in relationships:
        _require_parent_rows(table, parent, join_condition)

    missing_audit_projects = connection.execute(
        sa.text(
            "SELECT count(*) FROM authoritative_audit_events child "
            "LEFT JOIN projects parent ON child.project_id = parent.id "
            "WHERE child.project_id IS NOT NULL AND parent.id IS NULL"
        )
    ).scalar_one()
    if missing_audit_projects:
        raise RuntimeError(
            "Cannot align authoritative_audit_events: "
            f"{missing_audit_projects} row(s) have no matching projects parent. "
            "Repair or export those rows before upgrading."
        )

    # Scope columns are denormalized for efficient authorization. Their parent
    # record is authoritative when historical rows disagree.
    connection.execute(
        sa.text(
            "UPDATE jobs SET org_id = ("
            "SELECT projects.org_id FROM projects WHERE projects.id = jobs.project_id)"
        )
    )
    connection.execute(
        sa.text(
            "UPDATE deterministic_gate_results SET "
            "org_id = (SELECT jobs.org_id FROM jobs "
            "WHERE jobs.id = deterministic_gate_results.run_id), "
            "project_id = (SELECT jobs.project_id FROM jobs "
            "WHERE jobs.id = deterministic_gate_results.run_id)"
        )
    )
    connection.execute(
        sa.text(
            "UPDATE agent_evaluations SET "
            "org_id = (SELECT jobs.org_id FROM jobs "
            "WHERE jobs.id = agent_evaluations.run_id), "
            "project_id = (SELECT jobs.project_id FROM jobs "
            "WHERE jobs.id = agent_evaluations.run_id)"
        )
    )
    connection.execute(
        sa.text(
            "UPDATE authoritative_audit_events SET org_id = ("
            "SELECT projects.org_id FROM projects "
            "WHERE projects.id = authoritative_audit_events.project_id) "
            "WHERE project_id IS NOT NULL"
        )
    )
    connection.execute(
        sa.text(
            "UPDATE script_versions SET "
            "org_id = (SELECT scripts.org_id FROM scripts WHERE scripts.id = script_versions.script_id), "
            "project_id = (SELECT scripts.project_id FROM scripts "
            "WHERE scripts.id = script_versions.script_id)"
        )
    )
    connection.execute(
        sa.text(
            "UPDATE clearance_items SET "
            "org_id = (SELECT script_versions.org_id FROM script_versions "
            "WHERE script_versions.id = clearance_items.version_id), "
            "project_id = (SELECT script_versions.project_id FROM script_versions "
            "WHERE script_versions.id = clearance_items.version_id), "
            "script_id = (SELECT script_versions.script_id FROM script_versions "
            "WHERE script_versions.id = clearance_items.version_id)"
        )
    )
    connection.execute(
        sa.text(
            "UPDATE research_runs SET "
            "org_id = (SELECT clearance_items.org_id FROM clearance_items "
            "WHERE clearance_items.id = research_runs.item_id), "
            "project_id = (SELECT clearance_items.project_id FROM clearance_items "
            "WHERE clearance_items.id = research_runs.item_id)"
        )
    )
    connection.execute(
        sa.text(
            "UPDATE source_snapshots SET "
            "org_id = (SELECT research_runs.org_id FROM research_runs "
            "WHERE research_runs.id = source_snapshots.run_id), "
            "project_id = (SELECT research_runs.project_id FROM research_runs "
            "WHERE research_runs.id = source_snapshots.run_id), "
            "item_id = (SELECT research_runs.item_id FROM research_runs "
            "WHERE research_runs.id = source_snapshots.run_id)"
        )
    )
    connection.execute(
        sa.text(
            "UPDATE evidence_claims SET "
            "org_id = (SELECT source_snapshots.org_id FROM source_snapshots "
            "WHERE source_snapshots.id = evidence_claims.snapshot_id), "
            "project_id = (SELECT source_snapshots.project_id FROM source_snapshots "
            "WHERE source_snapshots.id = evidence_claims.snapshot_id), "
            "item_id = (SELECT source_snapshots.item_id FROM source_snapshots "
            "WHERE source_snapshots.id = evidence_claims.snapshot_id)"
        )
    )
    connection.execute(
        sa.text(
            "UPDATE report_snapshots SET "
            "org_id = (SELECT script_versions.org_id FROM script_versions "
            "WHERE script_versions.id = report_snapshots.script_version_id), "
            "project_id = (SELECT script_versions.project_id FROM script_versions "
            "WHERE script_versions.id = report_snapshots.script_version_id)"
        )
    )
    connection.execute(
        sa.text(
            "UPDATE report_releases SET "
            "org_id = (SELECT report_snapshots.org_id FROM report_snapshots "
            "WHERE report_snapshots.id = report_releases.snapshot_id), "
            "project_id = (SELECT report_snapshots.project_id FROM report_snapshots "
            "WHERE report_snapshots.id = report_releases.snapshot_id)"
        )
    )


def _backfill_child_scope() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "UPDATE research_queries SET "
            "org_id = (SELECT research_runs.org_id FROM research_runs "
            "WHERE research_runs.id = research_queries.run_id), "
            "project_id = (SELECT research_runs.project_id FROM research_runs "
            "WHERE research_runs.id = research_queries.run_id)"
        )
    )
    connection.execute(
        sa.text(
            "UPDATE provider_attempts SET "
            "org_id = (SELECT research_runs.org_id FROM research_runs "
            "WHERE research_runs.id = provider_attempts.run_id), "
            "project_id = (SELECT research_runs.project_id FROM research_runs "
            "WHERE research_runs.id = provider_attempts.run_id)"
        )
    )
    connection.execute(
        sa.text(
            "UPDATE evidence_conflicts SET "
            "org_id = (SELECT clearance_items.org_id FROM clearance_items "
            "WHERE clearance_items.id = evidence_conflicts.item_id), "
            "project_id = (SELECT clearance_items.project_id FROM clearance_items "
            "WHERE clearance_items.id = evidence_conflicts.item_id)"
        )
    )
    connection.execute(
        sa.text(
            "UPDATE judge_verdicts SET "
            "org_id = (SELECT agent_evaluations.org_id FROM agent_evaluations "
            "WHERE agent_evaluations.id = judge_verdicts.evaluation_id), "
            "project_id = (SELECT agent_evaluations.project_id FROM agent_evaluations "
            "WHERE agent_evaluations.id = judge_verdicts.evaluation_id)"
        )
    )


def upgrade() -> None:
    _align_historical_scope()

    for table_name in (
        "research_queries",
        "provider_attempts",
        "evidence_conflicts",
        "judge_verdicts",
    ):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.add_column(sa.Column("org_id", sa.UUID(as_uuid=True), nullable=True))
            batch_op.add_column(sa.Column("project_id", sa.UUID(as_uuid=True), nullable=True))
    _backfill_child_scope()
    for table_name in (
        "research_queries",
        "provider_attempts",
        "evidence_conflicts",
        "judge_verdicts",
    ):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.alter_column(
                "org_id", existing_type=sa.UUID(as_uuid=True), nullable=False
            )
            batch_op.alter_column(
                "project_id", existing_type=sa.UUID(as_uuid=True), nullable=False
            )

    # Add queue/runtime fields as nullable first so existing jobs remain readable
    # while deterministic values are backfilled.
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.add_column(sa.Column("progress", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("stage", sa.String(50), nullable=True))
        batch_op.add_column(sa.Column("actor_id", sa.UUID(as_uuid=True), nullable=True))
        batch_op.add_column(sa.Column("correlation_id", sa.UUID(as_uuid=True), nullable=True))
        batch_op.add_column(sa.Column("attempt_count", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("lease_owner", sa.String(255), nullable=True))

    op.execute(
        sa.text(
            "UPDATE jobs SET progress = 0, stage = status, correlation_id = id, "
            "attempt_count = 0, updated_at = created_at"
        )
    )

    with op.batch_alter_table("jobs") as batch_op:
        batch_op.alter_column("progress", existing_type=sa.Float(), nullable=False)
        batch_op.alter_column("stage", existing_type=sa.String(50), nullable=False)
        batch_op.alter_column(
            "correlation_id", existing_type=sa.UUID(as_uuid=True), nullable=False
        )
        batch_op.alter_column("attempt_count", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column(
            "updated_at", existing_type=sa.DateTime(timezone=True), nullable=False
        )
        batch_op.create_check_constraint(
            "ck_jobs_progress_range", "progress >= 0 AND progress <= 100"
        )
        batch_op.create_check_constraint(
            "ck_jobs_attempt_count_nonnegative", "attempt_count >= 0"
        )
        batch_op.create_unique_constraint(
            "uq_jobs_scope", ["id", "org_id", "project_id"]
        )
        batch_op.create_foreign_key(
            "fk_jobs_project_scope",
            "projects",
            ["org_id", "project_id"],
            ["org_id", "id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_jobs_actor", "users", ["actor_id"], ["id"], ondelete="RESTRICT"
        )
    op.create_index("idx_jobs_correlation", "jobs", ["org_id", "project_id", "correlation_id"])

    with op.batch_alter_table("deterministic_gate_results") as batch_op:
        batch_op.create_foreign_key(
            "fk_deterministic_gate_results_run_scope",
            "jobs",
            ["run_id", "org_id", "project_id"],
            ["id", "org_id", "project_id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_deterministic_gate_results_project_scope",
            "projects",
            ["org_id", "project_id"],
            ["org_id", "id"],
            ondelete="CASCADE",
        )
    with op.batch_alter_table("agent_evaluations") as batch_op:
        batch_op.create_unique_constraint(
            "uq_agent_evaluations_scope", ["id", "org_id", "project_id"]
        )
        batch_op.create_foreign_key(
            "fk_agent_evaluations_run_scope",
            "jobs",
            ["run_id", "org_id", "project_id"],
            ["id", "org_id", "project_id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_agent_evaluations_project_scope",
            "projects",
            ["org_id", "project_id"],
            ["org_id", "id"],
            ondelete="CASCADE",
        )

    with op.batch_alter_table("authoritative_audit_events") as batch_op:
        batch_op.add_column(sa.Column("correlation_id", sa.UUID(as_uuid=True), nullable=True))
    op.execute(sa.text("UPDATE authoritative_audit_events SET correlation_id = id"))
    with op.batch_alter_table("authoritative_audit_events") as batch_op:
        batch_op.alter_column(
            "correlation_id", existing_type=sa.UUID(as_uuid=True), nullable=False
        )
        batch_op.create_foreign_key(
            "fk_authoritative_audit_project_scope",
            "projects",
            ["org_id", "project_id"],
            ["org_id", "id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_authoritative_audit_actor",
            "users",
            ["actor_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    op.create_index(
        "idx_authoritative_audit_project",
        "authoritative_audit_events",
        ["org_id", "project_id", "occurred_at"],
    )

    # Composite roots close tenant scope at each provenance/report boundary.
    with op.batch_alter_table("scripts") as batch_op:
        batch_op.create_unique_constraint(
            "uq_scripts_scope", ["id", "org_id", "project_id"]
        )
    with op.batch_alter_table("script_versions") as batch_op:
        batch_op.create_unique_constraint(
            "uq_script_versions_scope", ["id", "org_id", "project_id"]
        )
        batch_op.create_foreign_key(
            "fk_script_versions_script_scope",
            "scripts",
            ["script_id", "org_id", "project_id"],
            ["id", "org_id", "project_id"],
            ondelete="CASCADE",
        )
    with op.batch_alter_table("script_elements") as batch_op:
        batch_op.create_unique_constraint(
            "uq_script_elements_version", ["id", "version_id"]
        )
    with op.batch_alter_table("clearance_items") as batch_op:
        batch_op.create_unique_constraint(
            "uq_clearance_items_scope", ["id", "org_id", "project_id"]
        )
        batch_op.create_foreign_key(
            "fk_clearance_items_element_version",
            "script_elements",
            ["element_id", "version_id"],
            ["id", "version_id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_clearance_items_script_scope",
            "scripts",
            ["script_id", "org_id", "project_id"],
            ["id", "org_id", "project_id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_clearance_items_version_scope",
            "script_versions",
            ["version_id", "org_id", "project_id"],
            ["id", "org_id", "project_id"],
            ondelete="CASCADE",
        )
    with op.batch_alter_table("research_runs") as batch_op:
        batch_op.create_unique_constraint(
            "uq_research_runs_project_scope", ["id", "org_id", "project_id"]
        )
        batch_op.create_unique_constraint(
            "uq_research_runs_scope", ["id", "org_id", "project_id", "item_id"]
        )
        batch_op.create_foreign_key(
            "fk_research_runs_item_scope",
            "clearance_items",
            ["item_id", "org_id", "project_id"],
            ["id", "org_id", "project_id"],
            ondelete="CASCADE",
        )
    for table_name in ("research_queries", "provider_attempts"):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.create_foreign_key(
                f"fk_{table_name}_run_scope",
                "research_runs",
                ["run_id", "org_id", "project_id"],
                ["id", "org_id", "project_id"],
                ondelete="CASCADE",
            )
            batch_op.create_foreign_key(
                f"fk_{table_name}_project_scope",
                "projects",
                ["org_id", "project_id"],
                ["org_id", "id"],
                ondelete="CASCADE",
            )
    with op.batch_alter_table("source_snapshots") as batch_op:
        batch_op.create_unique_constraint(
            "uq_source_snapshots_scope", ["id", "org_id", "project_id", "item_id"]
        )
        batch_op.create_foreign_key(
            "fk_source_snapshots_run_scope",
            "research_runs",
            ["run_id", "org_id", "project_id", "item_id"],
            ["id", "org_id", "project_id", "item_id"],
            ondelete="CASCADE",
        )
    with op.batch_alter_table("evidence_claims") as batch_op:
        batch_op.create_foreign_key(
            "fk_evidence_claims_snapshot_scope",
            "source_snapshots",
            ["snapshot_id", "org_id", "project_id", "item_id"],
            ["id", "org_id", "project_id", "item_id"],
            ondelete="CASCADE",
        )
    with op.batch_alter_table("evidence_conflicts") as batch_op:
        batch_op.create_foreign_key(
            "fk_evidence_conflicts_item_scope",
            "clearance_items",
            ["item_id", "org_id", "project_id"],
            ["id", "org_id", "project_id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_evidence_conflicts_project_scope",
            "projects",
            ["org_id", "project_id"],
            ["org_id", "id"],
            ondelete="CASCADE",
        )
    with op.batch_alter_table("judge_verdicts") as batch_op:
        batch_op.create_foreign_key(
            "fk_judge_verdicts_evaluation_scope",
            "agent_evaluations",
            ["evaluation_id", "org_id", "project_id"],
            ["id", "org_id", "project_id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_judge_verdicts_project_scope",
            "projects",
            ["org_id", "project_id"],
            ["org_id", "id"],
            ondelete="CASCADE",
        )

    with op.batch_alter_table("report_snapshots") as batch_op:
        batch_op.create_unique_constraint(
            "uq_report_snapshots_scope", ["id", "org_id", "project_id"]
        )
        batch_op.create_foreign_key(
            "fk_report_snapshots_version_scope",
            "script_versions",
            ["script_version_id", "org_id", "project_id"],
            ["id", "org_id", "project_id"],
            ondelete="CASCADE",
        )
    with op.batch_alter_table("report_releases") as batch_op:
        batch_op.create_foreign_key(
            "fk_report_releases_snapshot_scope",
            "report_snapshots",
            ["snapshot_id", "org_id", "project_id"],
            ["id", "org_id", "project_id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    with op.batch_alter_table("report_releases") as batch_op:
        batch_op.drop_constraint("fk_report_releases_snapshot_scope", type_="foreignkey")
    with op.batch_alter_table("report_snapshots") as batch_op:
        batch_op.drop_constraint("fk_report_snapshots_version_scope", type_="foreignkey")
        batch_op.drop_constraint("uq_report_snapshots_scope", type_="unique")

    with op.batch_alter_table("judge_verdicts") as batch_op:
        batch_op.drop_constraint("fk_judge_verdicts_project_scope", type_="foreignkey")
        batch_op.drop_constraint("fk_judge_verdicts_evaluation_scope", type_="foreignkey")
    with op.batch_alter_table("evidence_conflicts") as batch_op:
        batch_op.drop_constraint("fk_evidence_conflicts_project_scope", type_="foreignkey")
        batch_op.drop_constraint("fk_evidence_conflicts_item_scope", type_="foreignkey")
    with op.batch_alter_table("evidence_claims") as batch_op:
        batch_op.drop_constraint("fk_evidence_claims_snapshot_scope", type_="foreignkey")
    with op.batch_alter_table("source_snapshots") as batch_op:
        batch_op.drop_constraint("fk_source_snapshots_run_scope", type_="foreignkey")
        batch_op.drop_constraint("uq_source_snapshots_scope", type_="unique")
    for table_name in ("provider_attempts", "research_queries"):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_constraint(f"fk_{table_name}_project_scope", type_="foreignkey")
            batch_op.drop_constraint(f"fk_{table_name}_run_scope", type_="foreignkey")
    with op.batch_alter_table("research_runs") as batch_op:
        batch_op.drop_constraint("fk_research_runs_item_scope", type_="foreignkey")
        batch_op.drop_constraint("uq_research_runs_scope", type_="unique")
        batch_op.drop_constraint("uq_research_runs_project_scope", type_="unique")
    with op.batch_alter_table("clearance_items") as batch_op:
        batch_op.drop_constraint("fk_clearance_items_version_scope", type_="foreignkey")
        batch_op.drop_constraint("fk_clearance_items_script_scope", type_="foreignkey")
        batch_op.drop_constraint("fk_clearance_items_element_version", type_="foreignkey")
        batch_op.drop_constraint("uq_clearance_items_scope", type_="unique")
    with op.batch_alter_table("script_elements") as batch_op:
        batch_op.drop_constraint("uq_script_elements_version", type_="unique")
    with op.batch_alter_table("script_versions") as batch_op:
        batch_op.drop_constraint("fk_script_versions_script_scope", type_="foreignkey")
        batch_op.drop_constraint("uq_script_versions_scope", type_="unique")
    with op.batch_alter_table("scripts") as batch_op:
        batch_op.drop_constraint("uq_scripts_scope", type_="unique")

    op.drop_index("idx_authoritative_audit_project", table_name="authoritative_audit_events")
    with op.batch_alter_table("authoritative_audit_events") as batch_op:
        batch_op.drop_constraint("fk_authoritative_audit_actor", type_="foreignkey")
        batch_op.drop_constraint("fk_authoritative_audit_project_scope", type_="foreignkey")
        batch_op.drop_column("correlation_id")

    with op.batch_alter_table("agent_evaluations") as batch_op:
        batch_op.drop_constraint("fk_agent_evaluations_project_scope", type_="foreignkey")
        batch_op.drop_constraint("fk_agent_evaluations_run_scope", type_="foreignkey")
        batch_op.drop_constraint("uq_agent_evaluations_scope", type_="unique")
    with op.batch_alter_table("deterministic_gate_results") as batch_op:
        batch_op.drop_constraint(
            "fk_deterministic_gate_results_project_scope", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "fk_deterministic_gate_results_run_scope", type_="foreignkey"
        )

    op.drop_index("idx_jobs_correlation", table_name="jobs")
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.drop_constraint("fk_jobs_actor", type_="foreignkey")
        batch_op.drop_constraint("fk_jobs_project_scope", type_="foreignkey")
        batch_op.drop_constraint("uq_jobs_scope", type_="unique")
        batch_op.drop_constraint("ck_jobs_attempt_count_nonnegative", type_="check")
        batch_op.drop_constraint("ck_jobs_progress_range", type_="check")
        batch_op.drop_column("lease_owner")
        batch_op.drop_column("updated_at")
        batch_op.drop_column("attempt_count")
        batch_op.drop_column("correlation_id")
        batch_op.drop_column("actor_id")
        batch_op.drop_column("stage")
        batch_op.drop_column("progress")

    for table_name in (
        "judge_verdicts",
        "evidence_conflicts",
        "provider_attempts",
        "research_queries",
    ):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_column("project_id")
            batch_op.drop_column("org_id")

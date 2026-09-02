"""Persist replay-safe Flash detection invocations and candidate provenance.

Revision ID: 0025_detection_execution
Revises: 0024_ai_evaluation_provenance
Create Date: 2026-09-03 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025_detection_execution"
down_revision: str | None = "0024_ai_evaluation_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _ensure_unique_constraint(
    table_name: str,
    constraint_name: str,
    columns: list[str],
) -> None:
    existing = {
        constraint["name"]
        for constraint in sa.inspect(op.get_bind()).get_unique_constraints(table_name)
    }
    if constraint_name not in existing:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.create_unique_constraint(constraint_name, columns)


def upgrade() -> None:
    _ensure_unique_constraint(
        "script_versions",
        "uq_script_versions_scope",
        ["id", "org_id", "project_id"],
    )
    _ensure_unique_constraint(
        "script_elements",
        "uq_script_elements_version",
        ["id", "version_id"],
    )
    with op.batch_alter_table("ai_judge_invocations") as batch_op:
        batch_op.add_column(
            sa.Column("lease_owner", sa.String(255), nullable=True)
        )
    op.create_table(
        "detection_invocations",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("job_attempt_number", sa.Integer(), nullable=False),
        sa.Column("lease_owner", sa.String(255), nullable=False),
        sa.Column("script_version_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("element_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("requested_model", sa.String(255), nullable=False),
        sa.Column("returned_model", sa.String(255), nullable=True),
        sa.Column("input_sha256", sa.String(64), nullable=False),
        sa.Column("response_id", sa.String(255), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("candidate_count", sa.Integer(), nullable=True),
        sa.Column("safe_error", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "id", "org_id", "project_id", name="uq_detection_invocations_scope"
        ),
        sa.UniqueConstraint(
            "id",
            "org_id",
            "project_id",
            "run_id",
            "script_version_id",
            "element_id",
            name="uq_detection_invocations_provenance",
        ),
        sa.UniqueConstraint(
            "org_id",
            "project_id",
            "run_id",
            "job_attempt_number",
            "element_id",
            name="uq_detection_invocations_identity",
        ),
        sa.CheckConstraint(
            "job_attempt_number > 0",
            name="ck_detection_invocations_job_attempt",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'succeeded', 'failed')",
            name="ck_detection_invocations_status",
        ),
        sa.CheckConstraint(
            "length(input_sha256) = 64",
            name="ck_detection_invocations_input_hash",
        ),
        sa.CheckConstraint(
            "(input_tokens IS NULL OR input_tokens >= 0) AND "
            "(output_tokens IS NULL OR output_tokens >= 0) AND "
            "(total_tokens IS NULL OR total_tokens >= 0)",
            name="ck_detection_invocations_token_usage",
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND returned_model IS NULL "
            "AND response_id IS NULL AND latency_ms IS NULL "
            "AND candidate_count IS NULL AND safe_error IS NULL "
            "AND completed_at IS NULL) OR "
            "(status = 'succeeded' AND returned_model IS NOT NULL "
            "AND response_id IS NOT NULL AND latency_ms >= 0 "
            "AND candidate_count >= 0 AND safe_error IS NULL "
            "AND completed_at IS NOT NULL) OR "
            "(status = 'failed' AND latency_ms >= 0 "
            "AND candidate_count IS NULL AND safe_error IS NOT NULL "
            "AND completed_at IS NOT NULL)",
            name="ck_detection_invocations_terminal_state",
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "project_id"],
            ["projects.org_id", "projects.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id", "org_id", "project_id"],
            ["jobs.id", "jobs.org_id", "jobs.project_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["script_version_id", "org_id", "project_id"],
            ["script_versions.id", "script_versions.org_id", "script_versions.project_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["element_id", "script_version_id"],
            ["script_elements.id", "script_elements.version_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "idx_detection_invocations_run",
        "detection_invocations",
        ["org_id", "project_id", "run_id", "job_attempt_number", "created_at"],
    )

    op.create_table(
        "detection_candidates",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("invocation_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("script_version_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("element_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("span_start", sa.Integer(), nullable=False),
        sa.Column("span_end", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("uncertainty", sa.String(20), nullable=False),
        sa.Column("candidate_fingerprint", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "id", "org_id", "project_id", name="uq_detection_candidates_scope"
        ),
        sa.UniqueConstraint(
            "id",
            "org_id",
            "project_id",
            "run_id",
            name="uq_detection_candidates_run_scope",
        ),
        sa.UniqueConstraint(
            "id",
            "org_id",
            "project_id",
            "script_version_id",
            "element_id",
            name="uq_detection_candidates_item_scope",
        ),
        sa.UniqueConstraint(
            "org_id",
            "project_id",
            "invocation_id",
            "ordinal",
            name="uq_detection_candidates_invocation_ordinal",
        ),
        sa.UniqueConstraint(
            "org_id",
            "project_id",
            "invocation_id",
            "candidate_fingerprint",
            name="uq_detection_candidates_invocation_fingerprint",
        ),
        sa.CheckConstraint("ordinal > 0", name="ck_detection_candidates_ordinal"),
        sa.CheckConstraint(
            "span_start >= 0 AND span_end > span_start",
            name="ck_detection_candidates_span",
        ),
        sa.CheckConstraint(
            "uncertainty IN ('low', 'medium', 'high')",
            name="ck_detection_candidates_uncertainty",
        ),
        sa.CheckConstraint(
            "length(candidate_fingerprint) = 64",
            name="ck_detection_candidates_fingerprint",
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "project_id"],
            ["projects.org_id", "projects.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id", "org_id", "project_id"],
            ["jobs.id", "jobs.org_id", "jobs.project_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            [
                "invocation_id",
                "org_id",
                "project_id",
                "run_id",
                "script_version_id",
                "element_id",
            ],
            [
                "detection_invocations.id",
                "detection_invocations.org_id",
                "detection_invocations.project_id",
                "detection_invocations.run_id",
                "detection_invocations.script_version_id",
                "detection_invocations.element_id",
            ],
            name="fk_detection_candidates_invocation_provenance",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["script_version_id", "org_id", "project_id"],
            ["script_versions.id", "script_versions.org_id", "script_versions.project_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["element_id", "script_version_id"],
            ["script_elements.id", "script_elements.version_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "idx_detection_candidates_run",
        "detection_candidates",
        ["org_id", "project_id", "run_id", "element_id", "ordinal"],
    )

    with op.batch_alter_table("clearance_items") as batch_op:
        batch_op.add_column(
            sa.Column("detection_candidate_id", sa.UUID(as_uuid=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("candidate_fingerprint", sa.String(64), nullable=True)
        )
        batch_op.create_unique_constraint(
            "uq_clearance_items_candidate_fingerprint",
            ["org_id", "project_id", "version_id", "candidate_fingerprint"],
        )
        batch_op.create_foreign_key(
            "fk_clearance_items_detection_candidate_scope",
            "detection_candidates",
            [
                "detection_candidate_id",
                "org_id",
                "project_id",
                "version_id",
                "element_id",
            ],
            ["id", "org_id", "project_id", "script_version_id", "element_id"],
            ondelete="RESTRICT",
        )
        batch_op.create_check_constraint(
            "ck_clearance_items_candidate_fingerprint",
            "candidate_fingerprint IS NULL OR length(candidate_fingerprint) = 64",
        )

    with op.batch_alter_table("deterministic_gate_results") as batch_op:
        batch_op.add_column(
            sa.Column("candidate_id", sa.UUID(as_uuid=True), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_gate_results_detection_candidate_scope",
            "detection_candidates",
            ["candidate_id", "org_id", "project_id", "run_id"],
            ["id", "org_id", "project_id", "run_id"],
            ondelete="CASCADE",
        )
        batch_op.create_unique_constraint(
            "uq_gate_results_candidate_gate",
            ["org_id", "project_id", "run_id", "candidate_id", "gate_name"],
        )


def downgrade() -> None:
    with op.batch_alter_table("deterministic_gate_results") as batch_op:
        batch_op.drop_constraint(
            "uq_gate_results_candidate_gate", type_="unique"
        )
        batch_op.drop_constraint(
            "fk_gate_results_detection_candidate_scope", type_="foreignkey"
        )
        batch_op.drop_column("candidate_id")

    with op.batch_alter_table("clearance_items") as batch_op:
        batch_op.drop_constraint(
            "ck_clearance_items_candidate_fingerprint", type_="check"
        )
        batch_op.drop_constraint(
            "fk_clearance_items_detection_candidate_scope", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "uq_clearance_items_candidate_fingerprint", type_="unique"
        )
        batch_op.drop_column("candidate_fingerprint")
        batch_op.drop_column("detection_candidate_id")

    op.drop_index("idx_detection_candidates_run", table_name="detection_candidates")
    op.drop_table("detection_candidates")
    op.drop_index("idx_detection_invocations_run", table_name="detection_invocations")
    op.drop_table("detection_invocations")
    with op.batch_alter_table("ai_judge_invocations") as batch_op:
        batch_op.drop_column("lease_owner")

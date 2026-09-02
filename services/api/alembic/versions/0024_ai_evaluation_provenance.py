"""Persist immutable AI judge bindings and provider attempt provenance.

Revision ID: 0024_ai_evaluation_provenance
Revises: 0023_persistent_script_import
Create Date: 2026-09-02 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024_ai_evaluation_provenance"
down_revision: str | None = "0023_persistent_script_import"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("agent_evaluations") as batch_op:
        batch_op.add_column(sa.Column("critique", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("rubric_version", sa.String(100), nullable=True))
        batch_op.add_column(sa.Column("prompt_version", sa.String(100), nullable=True))
        batch_op.add_column(sa.Column("policy_version", sa.String(100), nullable=True))
        batch_op.add_column(sa.Column("requested_model", sa.String(255), nullable=True))
        batch_op.add_column(sa.Column("returned_model", sa.String(255), nullable=True))
        batch_op.add_column(sa.Column("input_sha256", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("response_id", sa.String(255), nullable=True))
        batch_op.add_column(sa.Column("input_tokens", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("output_tokens", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("total_tokens", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("latency_ms", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("repair_count", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("attempt_group_id", sa.UUID(as_uuid=True), nullable=True))

    op.execute(
        sa.text(
            "UPDATE agent_evaluations SET critique = '', "
            "rubric_version = 'legacy-unbound', "
            "prompt_version = 'legacy-unbound', "
            "policy_version = 'legacy-unbound', "
            "requested_model = 'legacy-unbound', "
            "input_sha256 = :empty_hash, latency_ms = 0, repair_count = 0, "
            "attempt_group_id = id"
        ).bindparams(empty_hash="0" * 64)
    )

    with op.batch_alter_table("agent_evaluations") as batch_op:
        batch_op.alter_column("critique", existing_type=sa.Text(), nullable=False)
        batch_op.alter_column(
            "rubric_version", existing_type=sa.String(100), nullable=False
        )
        batch_op.alter_column(
            "prompt_version", existing_type=sa.String(100), nullable=False
        )
        batch_op.alter_column(
            "policy_version", existing_type=sa.String(100), nullable=False
        )
        batch_op.alter_column(
            "requested_model", existing_type=sa.String(255), nullable=False
        )
        batch_op.alter_column(
            "input_sha256", existing_type=sa.String(64), nullable=False
        )
        batch_op.alter_column("latency_ms", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("repair_count", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column(
            "attempt_group_id", existing_type=sa.UUID(as_uuid=True), nullable=False
        )
        batch_op.create_check_constraint(
            "ck_agent_evaluations_headline_score",
            "headline_score IS NULL OR (headline_score >= 0 AND headline_score <= 100)",
        )
        batch_op.create_check_constraint(
            "ck_agent_evaluations_token_usage",
            "(input_tokens IS NULL OR input_tokens >= 0) AND "
            "(output_tokens IS NULL OR output_tokens >= 0) AND "
            "(total_tokens IS NULL OR total_tokens >= 0)",
        )
        batch_op.create_check_constraint(
            "ck_agent_evaluations_latency", "latency_ms >= 0"
        )
        batch_op.create_check_constraint(
            "ck_agent_evaluations_repair_count", "repair_count >= 0 AND repair_count <= 1"
        )
        batch_op.create_check_constraint(
            "ck_agent_evaluations_input_hash", "length(input_sha256) = 64"
        )

    unique_names = {
        constraint["name"]
        for constraint in sa.inspect(op.get_bind()).get_unique_constraints(
            "agent_evaluations"
        )
    }
    if "uq_agent_evaluations_scope" not in unique_names:
        with op.batch_alter_table("agent_evaluations") as batch_op:
            batch_op.create_unique_constraint(
                "uq_agent_evaluations_scope", ["id", "org_id", "project_id"]
            )

    job_unique_names = {
        constraint["name"]
        for constraint in sa.inspect(op.get_bind()).get_unique_constraints("jobs")
    }
    if "uq_jobs_scope" not in job_unique_names:
        with op.batch_alter_table("jobs") as batch_op:
            batch_op.create_unique_constraint(
                "uq_jobs_scope", ["id", "org_id", "project_id"]
            )

    with op.batch_alter_table("judge_verdicts") as batch_op:
        batch_op.create_check_constraint(
            "ck_judge_verdicts_score_status",
            "(status = 'scored' AND score IS NOT NULL AND score >= 0 AND score <= 100) OR "
            "(status IN ('incomplete', 'not_applicable') AND score IS NULL) OR "
            "(status = 'failed' AND score = 0)",
        )

    op.create_table(
        "ai_judge_invocations",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("job_attempt_number", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("requested_model", sa.String(255), nullable=False),
        sa.Column("rubric_version", sa.String(100), nullable=False),
        sa.Column("prompt_version", sa.String(100), nullable=False),
        sa.Column("policy_version", sa.String(100), nullable=False),
        sa.Column("input_sha256", sa.String(64), nullable=False),
        sa.Column("evaluation_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("safe_error", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "id", "org_id", "project_id", name="uq_ai_judge_invocations_scope"
        ),
        sa.UniqueConstraint(
            "org_id",
            "project_id",
            "run_id",
            "job_attempt_number",
            "stage",
            name="uq_ai_judge_invocations_identity",
        ),
        sa.CheckConstraint(
            "job_attempt_number > 0",
            name="ck_ai_judge_invocations_attempt_number",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'succeeded', 'failed')",
            name="ck_ai_judge_invocations_status",
        ),
        sa.CheckConstraint(
            "length(input_sha256) = 64",
            name="ck_ai_judge_invocations_input_hash",
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND evaluation_id IS NULL "
            "AND safe_error IS NULL AND completed_at IS NULL) OR "
            "(status = 'succeeded' AND evaluation_id IS NOT NULL "
            "AND safe_error IS NULL AND completed_at IS NOT NULL) OR "
            "(status = 'failed' AND evaluation_id IS NULL "
            "AND safe_error IS NOT NULL AND completed_at IS NOT NULL)",
            name="ck_ai_judge_invocations_terminal_state",
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
            ["evaluation_id", "org_id", "project_id"],
            [
                "agent_evaluations.id",
                "agent_evaluations.org_id",
                "agent_evaluations.project_id",
            ],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "idx_ai_judge_invocations_run",
        "ai_judge_invocations",
        ["org_id", "project_id", "run_id", "job_attempt_number", "stage"],
    )

    op.create_table(
        "ai_provider_attempts",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("evaluation_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("attempt_group_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("requested_model", sa.String(255), nullable=False),
        sa.Column("returned_model", sa.String(255), nullable=True),
        sa.Column("rubric_version", sa.String(100), nullable=False),
        sa.Column("prompt_version", sa.String(100), nullable=False),
        sa.Column("policy_version", sa.String(100), nullable=False),
        sa.Column("input_sha256", sa.String(64), nullable=False),
        sa.Column("response_id", sa.String(255), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("safe_error", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "id", "org_id", "project_id", name="uq_ai_provider_attempts_scope"
        ),
        sa.UniqueConstraint(
            "org_id",
            "project_id",
            "attempt_group_id",
            "ordinal",
            name="uq_ai_provider_attempts_group_ordinal",
        ),
        sa.CheckConstraint("ordinal > 0", name="ck_ai_provider_attempts_ordinal"),
        sa.CheckConstraint(
            "status IN ('started', 'succeeded', 'failed', 'invalid_response')",
            name="ck_ai_provider_attempts_status",
        ),
        sa.CheckConstraint("latency_ms >= 0", name="ck_ai_provider_attempts_latency"),
        sa.CheckConstraint(
            "length(input_sha256) = 64", name="ck_ai_provider_attempts_input_hash"
        ),
        sa.CheckConstraint(
            "(input_tokens IS NULL OR input_tokens >= 0) AND "
            "(output_tokens IS NULL OR output_tokens >= 0) AND "
            "(total_tokens IS NULL OR total_tokens >= 0)",
            name="ck_ai_provider_attempts_token_usage",
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
            ["attempt_group_id", "org_id", "project_id"],
            [
                "ai_judge_invocations.id",
                "ai_judge_invocations.org_id",
                "ai_judge_invocations.project_id",
            ],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_id", "org_id", "project_id"],
            [
                "agent_evaluations.id",
                "agent_evaluations.org_id",
                "agent_evaluations.project_id",
            ],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "idx_ai_provider_attempts_run",
        "ai_provider_attempts",
        ["org_id", "project_id", "run_id", "created_at"],
    )
    op.create_index(
        "idx_ai_provider_attempts_evaluation",
        "ai_provider_attempts",
        ["org_id", "project_id", "evaluation_id", "ordinal"],
    )


def downgrade() -> None:
    op.drop_index("idx_ai_provider_attempts_evaluation", table_name="ai_provider_attempts")
    op.drop_index("idx_ai_provider_attempts_run", table_name="ai_provider_attempts")
    op.drop_table("ai_provider_attempts")

    op.drop_index("idx_ai_judge_invocations_run", table_name="ai_judge_invocations")
    op.drop_table("ai_judge_invocations")

    with op.batch_alter_table("judge_verdicts") as batch_op:
        batch_op.drop_constraint(
            "ck_judge_verdicts_score_status", type_="check"
        )

    with op.batch_alter_table("agent_evaluations") as batch_op:
        batch_op.drop_constraint("ck_agent_evaluations_input_hash", type_="check")
        batch_op.drop_constraint("ck_agent_evaluations_repair_count", type_="check")
        batch_op.drop_constraint("ck_agent_evaluations_latency", type_="check")
        batch_op.drop_constraint("ck_agent_evaluations_token_usage", type_="check")
        batch_op.drop_constraint(
            "ck_agent_evaluations_headline_score", type_="check"
        )
        for column in (
            "attempt_group_id",
            "repair_count",
            "latency_ms",
            "total_tokens",
            "output_tokens",
            "input_tokens",
            "response_id",
            "input_sha256",
            "returned_model",
            "requested_model",
            "policy_version",
            "prompt_version",
            "rubric_version",
            "critique",
        ):
            batch_op.drop_column(column)

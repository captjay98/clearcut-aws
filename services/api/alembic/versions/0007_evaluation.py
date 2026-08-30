"""0007_evaluation

Revision ID: 0007_evaluation
Revises: 0006_detection_jobs
Create Date: 2026-08-30 14:40:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_evaluation"
down_revision: str | None = "0006_detection_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Deterministic gate results
    op.create_table(
        "deterministic_gate_results",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("gate_name", sa.String(100), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("severity", sa.String(50), nullable=False),
        sa.Column("details", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "idx_gate_results_run",
        "deterministic_gate_results",
        ["org_id", "project_id", "run_id"],
    )

    # Agent evaluations
    op.create_table(
        "agent_evaluations",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("stage", sa.String(50), nullable=False),
        sa.Column("headline_score", sa.Float(), nullable=True),
        sa.Column("scored_dimensions_count", sa.Integer(), nullable=False),
        sa.Column("blockers_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "idx_agent_evaluations_run",
        "agent_evaluations",
        ["org_id", "project_id", "run_id"],
    )

    # Judge verdicts
    op.create_table(
        "judge_verdicts",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "evaluation_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("agent_evaluations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("dimension", sa.String(100), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "idx_judge_verdicts_eval",
        "judge_verdicts",
        ["evaluation_id", "dimension"],
    )


def downgrade() -> None:
    op.drop_table("judge_verdicts")
    op.drop_table("agent_evaluations")
    op.drop_table("deterministic_gate_results")

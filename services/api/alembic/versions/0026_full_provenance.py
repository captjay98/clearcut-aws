"""Bind judge and clearance-item records to complete provenance chains.

Revision ID: 0026_full_provenance
Revises: 0025_detection_execution
Create Date: 2026-09-03 04:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026_full_provenance"
down_revision: str | None = "0025_detection_execution"
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


def _require_no_rows(description: str, query: str) -> None:
    count = int(op.get_bind().execute(sa.text(query)).scalar_one())
    if count:
        raise RuntimeError(
            f"Cannot enforce full provenance: {description} ({count} rows)."
        )


def _preflight_provenance() -> None:
    _require_no_rows(
        "judge invocations reference a mismatched evaluation",
        """
        SELECT count(*)
        FROM ai_judge_invocations AS invocation
        LEFT JOIN agent_evaluations AS evaluation
          ON evaluation.id = invocation.evaluation_id
         AND evaluation.org_id = invocation.org_id
         AND evaluation.project_id = invocation.project_id
         AND evaluation.run_id = invocation.run_id
         AND evaluation.attempt_group_id = invocation.id
        WHERE invocation.evaluation_id IS NOT NULL
          AND evaluation.id IS NULL
        """,
    )
    _require_no_rows(
        "provider attempts reference a mismatched judge invocation",
        """
        SELECT count(*)
        FROM ai_provider_attempts AS attempt
        LEFT JOIN ai_judge_invocations AS invocation
          ON invocation.id = attempt.attempt_group_id
         AND invocation.org_id = attempt.org_id
         AND invocation.project_id = attempt.project_id
         AND invocation.run_id = attempt.run_id
        WHERE invocation.id IS NULL
        """,
    )
    _require_no_rows(
        "provider attempts reference a mismatched evaluation",
        """
        SELECT count(*)
        FROM ai_provider_attempts AS attempt
        LEFT JOIN agent_evaluations AS evaluation
          ON evaluation.id = attempt.evaluation_id
         AND evaluation.org_id = attempt.org_id
         AND evaluation.project_id = attempt.project_id
         AND evaluation.run_id = attempt.run_id
         AND evaluation.attempt_group_id = attempt.attempt_group_id
        WHERE attempt.evaluation_id IS NOT NULL
          AND evaluation.id IS NULL
        """,
    )
    _require_no_rows(
        "clearance items reference a version owned by another script",
        """
        SELECT count(*)
        FROM clearance_items AS item
        LEFT JOIN script_versions AS version
          ON version.id = item.version_id
         AND version.org_id = item.org_id
         AND version.project_id = item.project_id
         AND version.script_id = item.script_id
        WHERE version.id IS NULL
        """,
    )
    _require_no_rows(
        "clearance items have partial detection provenance",
        """
        SELECT count(*)
        FROM clearance_items
        WHERE NOT (
            (detection_candidate_id IS NULL
             AND detection_run_id IS NULL
             AND candidate_fingerprint IS NULL)
            OR
            (detection_candidate_id IS NOT NULL
             AND detection_run_id IS NOT NULL
             AND candidate_fingerprint IS NOT NULL)
        )
        """,
    )
    _require_no_rows(
        "clearance items reference mismatched detection candidate provenance",
        """
        SELECT count(*)
        FROM clearance_items AS item
        LEFT JOIN detection_candidates AS candidate
          ON candidate.id = item.detection_candidate_id
         AND candidate.org_id = item.org_id
         AND candidate.project_id = item.project_id
         AND candidate.run_id = item.detection_run_id
         AND candidate.script_version_id = item.version_id
         AND candidate.element_id = item.element_id
         AND candidate.candidate_fingerprint = item.candidate_fingerprint
        WHERE item.detection_candidate_id IS NOT NULL
          AND candidate.id IS NULL
        """,
    )


def upgrade() -> None:
    with op.batch_alter_table("clearance_items") as batch_op:
        batch_op.add_column(
            sa.Column("detection_run_id", sa.UUID(as_uuid=True), nullable=True)
        )

    op.execute(
        sa.text(
            """
            UPDATE clearance_items
            SET detection_run_id = (
                SELECT candidate.run_id
                FROM detection_candidates AS candidate
                WHERE candidate.id = clearance_items.detection_candidate_id
                  AND candidate.org_id = clearance_items.org_id
                  AND candidate.project_id = clearance_items.project_id
            )
            WHERE detection_candidate_id IS NOT NULL
            """
        )
    )
    _preflight_provenance()

    _ensure_unique_constraint(
        "agent_evaluations",
        "uq_agent_evaluations_invocation_provenance",
        ["id", "org_id", "project_id", "run_id", "attempt_group_id"],
    )
    _ensure_unique_constraint(
        "ai_judge_invocations",
        "uq_ai_judge_invocations_run_scope",
        ["id", "org_id", "project_id", "run_id"],
    )
    _ensure_unique_constraint(
        "script_versions",
        "uq_script_versions_script_provenance",
        ["id", "org_id", "project_id", "script_id"],
    )
    _ensure_unique_constraint(
        "detection_candidates",
        "uq_detection_candidates_item_provenance",
        [
            "id",
            "org_id",
            "project_id",
            "run_id",
            "script_version_id",
            "element_id",
            "candidate_fingerprint",
        ],
    )

    with op.batch_alter_table("ai_judge_invocations") as batch_op:
        batch_op.create_foreign_key(
            "fk_ai_judge_invocations_evaluation_provenance",
            "agent_evaluations",
            ["evaluation_id", "org_id", "project_id", "run_id", "id"],
            ["id", "org_id", "project_id", "run_id", "attempt_group_id"],
            ondelete="CASCADE",
        )

    with op.batch_alter_table("ai_provider_attempts") as batch_op:
        batch_op.create_foreign_key(
            "fk_ai_provider_attempts_invocation_provenance",
            "ai_judge_invocations",
            ["attempt_group_id", "org_id", "project_id", "run_id"],
            ["id", "org_id", "project_id", "run_id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_ai_provider_attempts_evaluation_provenance",
            "agent_evaluations",
            ["evaluation_id", "org_id", "project_id", "run_id", "attempt_group_id"],
            ["id", "org_id", "project_id", "run_id", "attempt_group_id"],
            ondelete="CASCADE",
        )

    with op.batch_alter_table("clearance_items") as batch_op:
        batch_op.create_foreign_key(
            "fk_clearance_items_script_version_provenance",
            "script_versions",
            ["version_id", "org_id", "project_id", "script_id"],
            ["id", "org_id", "project_id", "script_id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_clearance_items_detection_candidate_provenance",
            "detection_candidates",
            [
                "detection_candidate_id",
                "org_id",
                "project_id",
                "detection_run_id",
                "version_id",
                "element_id",
                "candidate_fingerprint",
            ],
            [
                "id",
                "org_id",
                "project_id",
                "run_id",
                "script_version_id",
                "element_id",
                "candidate_fingerprint",
            ],
            ondelete="RESTRICT",
        )
        batch_op.create_check_constraint(
            "ck_clearance_items_detection_candidate_binding",
            "(detection_candidate_id IS NULL AND detection_run_id IS NULL "
            "AND candidate_fingerprint IS NULL) OR "
            "(detection_candidate_id IS NOT NULL AND detection_run_id IS NOT NULL "
            "AND candidate_fingerprint IS NOT NULL)",
        )


def downgrade() -> None:
    with op.batch_alter_table("clearance_items") as batch_op:
        batch_op.drop_constraint(
            "ck_clearance_items_detection_candidate_binding", type_="check"
        )
        batch_op.drop_constraint(
            "fk_clearance_items_detection_candidate_provenance", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "fk_clearance_items_script_version_provenance", type_="foreignkey"
        )
        batch_op.drop_column("detection_run_id")

    with op.batch_alter_table("ai_provider_attempts") as batch_op:
        batch_op.drop_constraint(
            "fk_ai_provider_attempts_evaluation_provenance", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "fk_ai_provider_attempts_invocation_provenance", type_="foreignkey"
        )

    with op.batch_alter_table("ai_judge_invocations") as batch_op:
        batch_op.drop_constraint(
            "fk_ai_judge_invocations_evaluation_provenance", type_="foreignkey"
        )

    with op.batch_alter_table("detection_candidates") as batch_op:
        batch_op.drop_constraint(
            "uq_detection_candidates_item_provenance", type_="unique"
        )
    with op.batch_alter_table("script_versions") as batch_op:
        batch_op.drop_constraint(
            "uq_script_versions_script_provenance", type_="unique"
        )
    with op.batch_alter_table("ai_judge_invocations") as batch_op:
        batch_op.drop_constraint(
            "uq_ai_judge_invocations_run_scope", type_="unique"
        )
    with op.batch_alter_table("agent_evaluations") as batch_op:
        batch_op.drop_constraint(
            "uq_agent_evaluations_invocation_provenance", type_="unique"
        )

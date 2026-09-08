"""Persist additive revision, evidence lineage, and selective-rescan checkpoints.

Revision ID: 0035_revision_selective_rescan
Revises: 0034_report_artifacts
Create Date: 2026-09-04 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0035_revision_selective_rescan"
down_revision: str | None = "0034_report_artifacts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def _preflight_historical_diffs() -> None:
    invalid_count = (
        op.get_bind()
        .execute(
            sa.text(
                """
            SELECT count(*)
            FROM script_diffs AS diff
            LEFT JOIN script_versions AS before_version
              ON before_version.id = diff.before_version_id
            LEFT JOIN script_versions AS after_version
              ON after_version.id = diff.after_version_id
            WHERE before_version.id IS NULL
               OR after_version.id IS NULL
               OR before_version.org_id <> diff.org_id
               OR before_version.project_id <> diff.project_id
               OR after_version.org_id <> diff.org_id
               OR after_version.project_id <> diff.project_id
               OR before_version.script_id <> after_version.script_id
               OR after_version.ordinal <> before_version.ordinal + 1
            """
            )
        )
        .scalar_one()
    )
    if invalid_count:
        raise RuntimeError(
            "0035 cannot safely scope historical script_diffs: "
            "an endpoint is missing, cross-scoped, cross-script, or non-adjacent"
        )

    duplicate_count = (
        op.get_bind()
        .execute(
            sa.text(
                """
                SELECT count(*)
                FROM (
                    SELECT org_id, project_id, after_version_id
                    FROM script_diffs
                    GROUP BY org_id, project_id, after_version_id
                    HAVING count(*) > 1
                ) AS duplicate_adjacent_diffs
                """
            )
        )
        .scalar_one()
    )
    if duplicate_count:
        raise RuntimeError(
            "0035 cannot preserve duplicate adjacent script_diffs while enforcing "
            "one canonical diff per after version; repair duplicate history first"
        )


def upgrade() -> None:
    _preflight_historical_diffs()
    with op.batch_alter_table("script_versions") as batch_op:
        batch_op.add_column(
            sa.Column("predecessor_version_id", sa.UUID(as_uuid=True), nullable=True)
        )
        batch_op.add_column(sa.Column("predecessor_ordinal", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("committed_by_actor_id", sa.UUID(as_uuid=True), nullable=True)
        )
        batch_op.create_unique_constraint(
            "uq_script_versions_revision_provenance",
            ["id", "org_id", "project_id", "script_id", "ordinal"],
        )
        batch_op.create_unique_constraint(
            "uq_script_versions_predecessor_provenance",
            [
                "id",
                "org_id",
                "project_id",
                "script_id",
                "predecessor_version_id",
            ],
        )
        batch_op.create_check_constraint(
            "ck_script_versions_predecessor_adjacency",
            "(predecessor_version_id IS NULL AND predecessor_ordinal IS NULL) OR "
            "(predecessor_version_id IS NOT NULL AND predecessor_ordinal IS NOT NULL "
            "AND ordinal = predecessor_ordinal + 1)",
        )
        batch_op.create_foreign_key(
            "fk_script_versions_predecessor_scope",
            "script_versions",
            [
                "predecessor_version_id",
                "org_id",
                "project_id",
                "script_id",
                "predecessor_ordinal",
            ],
            ["id", "org_id", "project_id", "script_id", "ordinal"],
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            "fk_script_versions_committing_actor_membership",
            "memberships",
            ["org_id", "committed_by_actor_id"],
            ["org_id", "user_id"],
            ondelete="RESTRICT",
        )

    op.create_index(
        "uq_script_versions_checkpoint_scope",
        "script_versions",
        ["id", "org_id", "project_id"],
        unique=True,
    )

    with op.batch_alter_table("script_diffs") as batch_op:
        batch_op.add_column(sa.Column("script_id", sa.UUID(as_uuid=True), nullable=True))
        batch_op.add_column(sa.Column("before_ordinal", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("after_ordinal", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("algorithm_version", sa.String(100), nullable=True))
        batch_op.add_column(sa.Column("summary_payload", _JSON, nullable=True))

    op.execute(
        sa.text(
            """
            UPDATE script_diffs
            SET script_id = (
                    SELECT script_id
                    FROM script_versions
                    WHERE script_versions.id = script_diffs.before_version_id
                ),
                before_ordinal = (
                    SELECT ordinal
                    FROM script_versions
                    WHERE script_versions.id = script_diffs.before_version_id
                ),
                after_ordinal = (
                    SELECT ordinal
                    FROM script_versions
                    WHERE script_versions.id = script_diffs.after_version_id
                ),
                algorithm_version = 'legacy',
                summary_payload = '{}'
            """
        )
    )

    with op.batch_alter_table("script_diffs") as batch_op:
        batch_op.alter_column(
            "script_id",
            existing_type=sa.UUID(as_uuid=True),
            nullable=False,
        )
        batch_op.alter_column(
            "before_ordinal",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.alter_column(
            "after_ordinal",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.alter_column(
            "algorithm_version",
            existing_type=sa.String(100),
            nullable=False,
        )
        batch_op.alter_column(
            "summary_payload",
            existing_type=_JSON,
            nullable=False,
        )
        batch_op.create_unique_constraint(
            "uq_script_diffs_adjacent",
            [
                "org_id",
                "project_id",
                "script_id",
                "before_version_id",
                "after_version_id",
            ],
        )
        batch_op.create_unique_constraint(
            "uq_script_diffs_after_version",
            ["org_id", "project_id", "script_id", "after_version_id"],
        )
        batch_op.create_unique_constraint(
            "uq_script_diffs_lineage_provenance",
            [
                "id",
                "org_id",
                "project_id",
                "script_id",
                "before_version_id",
                "after_version_id",
                "algorithm_version",
            ],
        )
        batch_op.create_check_constraint(
            "ck_script_diffs_adjacent_ordinals",
            "after_ordinal = before_ordinal + 1",
        )
        batch_op.create_check_constraint(
            "ck_script_diffs_distinct_versions",
            "before_version_id <> after_version_id",
        )
        batch_op.create_foreign_key(
            "fk_script_diffs_before_version_scope",
            "script_versions",
            [
                "before_version_id",
                "org_id",
                "project_id",
                "script_id",
                "before_ordinal",
            ],
            ["id", "org_id", "project_id", "script_id", "ordinal"],
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            "fk_script_diffs_after_version_scope",
            "script_versions",
            [
                "after_version_id",
                "org_id",
                "project_id",
                "script_id",
                "after_ordinal",
            ],
            ["id", "org_id", "project_id", "script_id", "ordinal"],
            ondelete="RESTRICT",
        )

    op.create_index(
        "idx_script_diffs_after_version",
        "script_diffs",
        ["org_id", "project_id", "script_id", "after_version_id"],
    )

    op.create_table(
        "script_element_lineage",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("script_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("diff_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("before_version_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("after_version_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("before_element_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("after_element_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("change_kind", sa.String(20), nullable=False),
        sa.Column("confidence", sa.String(20), nullable=False),
        sa.Column("algorithm_version", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "diff_id",
            "before_element_id",
            name="uq_script_element_lineage_before",
        ),
        sa.UniqueConstraint(
            "diff_id",
            "after_element_id",
            name="uq_script_element_lineage_after",
        ),
        sa.CheckConstraint(
            "change_kind IN ('unchanged', 'moved', 'modified', 'added', 'removed')",
            name="ck_script_element_lineage_change_kind",
        ),
        sa.CheckConstraint(
            "confidence IN ('exact', 'contextual', 'similar', 'unmatched')",
            name="ck_script_element_lineage_confidence",
        ),
        sa.CheckConstraint(
            "(change_kind = 'added' AND before_element_id IS NULL "
            "AND after_element_id IS NOT NULL AND confidence = 'unmatched') OR "
            "(change_kind = 'removed' AND before_element_id IS NOT NULL "
            "AND after_element_id IS NULL AND confidence = 'unmatched') OR "
            "(change_kind IN ('unchanged', 'moved', 'modified') "
            "AND before_element_id IS NOT NULL AND after_element_id IS NOT NULL "
            "AND confidence IN ('exact', 'contextual', 'similar'))",
            name="ck_script_element_lineage_endpoints",
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "project_id"],
            ["projects.org_id", "projects.id"],
            name="fk_script_element_lineage_project_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            [
                "diff_id",
                "org_id",
                "project_id",
                "script_id",
                "before_version_id",
                "after_version_id",
                "algorithm_version",
            ],
            [
                "script_diffs.id",
                "script_diffs.org_id",
                "script_diffs.project_id",
                "script_diffs.script_id",
                "script_diffs.before_version_id",
                "script_diffs.after_version_id",
                "script_diffs.algorithm_version",
            ],
            name="fk_script_element_lineage_diff_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["before_version_id", "org_id", "project_id", "script_id"],
            [
                "script_versions.id",
                "script_versions.org_id",
                "script_versions.project_id",
                "script_versions.script_id",
            ],
            name="fk_script_element_lineage_before_version_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["after_version_id", "org_id", "project_id", "script_id"],
            [
                "script_versions.id",
                "script_versions.org_id",
                "script_versions.project_id",
                "script_versions.script_id",
            ],
            name="fk_script_element_lineage_after_version_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["before_element_id", "before_version_id"],
            ["script_elements.id", "script_elements.version_id"],
            name="fk_script_element_lineage_before_element",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["after_element_id", "after_version_id"],
            ["script_elements.id", "script_elements.version_id"],
            name="fk_script_element_lineage_after_element",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "idx_script_element_lineage_diff",
        "script_element_lineage",
        ["org_id", "project_id", "script_id", "diff_id"],
    )

    with op.batch_alter_table("clearance_items") as batch_op:
        batch_op.add_column(sa.Column("predecessor_item_id", sa.UUID(as_uuid=True), nullable=True))
        batch_op.add_column(
            sa.Column("predecessor_version_id", sa.UUID(as_uuid=True), nullable=True)
        )
        batch_op.add_column(sa.Column("lineage_kind", sa.String(30), nullable=True))
        batch_op.add_column(
            sa.Column(
                "carried_forward_confirmation_required",
                sa.Boolean(),
                nullable=True,
            )
        )

    op.execute(
        sa.text(
            "UPDATE clearance_items "
            "SET carried_forward_confirmation_required = false "
            "WHERE carried_forward_confirmation_required IS NULL"
        )
    )

    with op.batch_alter_table("clearance_items") as batch_op:
        batch_op.alter_column(
            "carried_forward_confirmation_required",
            existing_type=sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        )
        batch_op.create_unique_constraint(
            "uq_clearance_items_predecessor_item_provenance",
            ["id", "org_id", "project_id", "script_id", "version_id"],
        )
        batch_op.create_unique_constraint(
            "uq_clearance_items_carry_edge",
            [
                "id",
                "org_id",
                "project_id",
                "predecessor_item_id",
                "lineage_kind",
                "carried_forward_confirmation_required",
            ],
        )
        batch_op.create_unique_constraint(
            "uq_clearance_items_successor_projection",
            ["org_id", "project_id", "predecessor_item_id", "version_id"],
        )
        batch_op.create_check_constraint(
            "ck_clearance_items_lineage_state",
            "(predecessor_item_id IS NULL AND predecessor_version_id IS NULL "
            "AND lineage_kind IS NULL "
            "AND carried_forward_confirmation_required = false) OR "
            "(predecessor_item_id IS NOT NULL AND predecessor_version_id IS NOT NULL "
            "AND lineage_kind = 'carried_forward' "
            "AND carried_forward_confirmation_required = true) OR "
            "(predecessor_item_id IS NOT NULL AND predecessor_version_id IS NOT NULL "
            "AND lineage_kind = 'rescanned' "
            "AND carried_forward_confirmation_required = false)",
        )
        batch_op.create_check_constraint(
            "ck_clearance_items_predecessor_not_self",
            "predecessor_item_id IS NULL OR predecessor_item_id <> id",
        )
        batch_op.create_foreign_key(
            "fk_clearance_items_predecessor_item_scope",
            "clearance_items",
            [
                "predecessor_item_id",
                "org_id",
                "project_id",
                "script_id",
                "predecessor_version_id",
            ],
            ["id", "org_id", "project_id", "script_id", "version_id"],
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            "fk_clearance_items_predecessor_version_scope",
            "script_versions",
            [
                "version_id",
                "org_id",
                "project_id",
                "script_id",
                "predecessor_version_id",
            ],
            [
                "id",
                "org_id",
                "project_id",
                "script_id",
                "predecessor_version_id",
            ],
            ondelete="RESTRICT",
        )

    with op.batch_alter_table("evidence_claims") as batch_op:
        batch_op.create_unique_constraint(
            "uq_evidence_claims_carry_provenance",
            [
                "id",
                "org_id",
                "project_id",
                "item_id",
                "snapshot_id",
                "run_id",
                "query_id",
                "provider_attempt_id",
            ],
        )

    op.create_table(
        "evidence_carry_forwards",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("new_item_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("source_item_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("original_claim_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("query_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_attempt_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "new_item_lineage_kind",
            sa.String(30),
            nullable=False,
            server_default=sa.text("'carried_forward'"),
        ),
        sa.Column(
            "confirmation_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "org_id",
            "project_id",
            "new_item_id",
            "original_claim_id",
            name="uq_evidence_carry_forwards_item_claim",
        ),
        sa.CheckConstraint(
            "new_item_lineage_kind = 'carried_forward' AND confirmation_required = true",
            name="ck_evidence_carry_forwards_lineage_state",
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "project_id"],
            ["projects.org_id", "projects.id"],
            name="fk_evidence_carry_forwards_project_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            [
                "new_item_id",
                "org_id",
                "project_id",
                "source_item_id",
                "new_item_lineage_kind",
                "confirmation_required",
            ],
            [
                "clearance_items.id",
                "clearance_items.org_id",
                "clearance_items.project_id",
                "clearance_items.predecessor_item_id",
                "clearance_items.lineage_kind",
                "clearance_items.carried_forward_confirmation_required",
            ],
            name="fk_evidence_carry_forwards_new_item_lineage",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_item_id", "org_id", "project_id"],
            [
                "clearance_items.id",
                "clearance_items.org_id",
                "clearance_items.project_id",
            ],
            name="fk_evidence_carry_forwards_source_item_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [
                "original_claim_id",
                "org_id",
                "project_id",
                "source_item_id",
                "snapshot_id",
                "run_id",
                "query_id",
                "provider_attempt_id",
            ],
            [
                "evidence_claims.id",
                "evidence_claims.org_id",
                "evidence_claims.project_id",
                "evidence_claims.item_id",
                "evidence_claims.snapshot_id",
                "evidence_claims.run_id",
                "evidence_claims.query_id",
                "evidence_claims.provider_attempt_id",
            ],
            name="fk_evidence_carry_forwards_claim_provenance",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "idx_evidence_carry_forwards_new_item",
        "evidence_carry_forwards",
        ["org_id", "project_id", "new_item_id"],
    )

    op.create_table(
        "selective_rescan_checkpoints",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("stage", sa.String(50), nullable=False),
        sa.Column("script_version_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("item_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("result", _JSON, nullable=True),
        sa.Column("safe_error", _JSON, nullable=True),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "stage IN ('queued', 'materializing_lineage', 'carrying_evidence', "
            "'detecting_affected_passages', 'researching_affected_items', "
            "'awaiting_confirmation', 'completed')",
            name="ck_selective_rescan_checkpoints_stage",
        ),
        sa.CheckConstraint(
            "attempt_number > 0",
            name="ck_selective_rescan_checkpoints_attempt",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed')",
            name="ck_selective_rescan_checkpoints_status",
        ),
        sa.CheckConstraint(
            "script_version_id IS NULL OR item_id IS NULL",
            name="ck_selective_rescan_checkpoints_single_target",
        ),
        sa.CheckConstraint(
            "(status IN ('pending', 'running') AND result IS NULL "
            "AND safe_error IS NULL AND completed_at IS NULL) OR "
            "(status = 'succeeded' AND safe_error IS NULL "
            "AND completed_at IS NOT NULL) OR "
            "(status = 'failed' AND result IS NULL "
            "AND safe_error IS NOT NULL AND completed_at IS NOT NULL)",
            name="ck_selective_rescan_checkpoints_state",
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "project_id"],
            ["projects.org_id", "projects.id"],
            name="fk_selective_rescan_checkpoints_project_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["job_id", "org_id", "project_id"],
            ["jobs.id", "jobs.org_id", "jobs.project_id"],
            name="fk_selective_rescan_checkpoints_job_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["script_version_id", "org_id", "project_id"],
            [
                "script_versions.id",
                "script_versions.org_id",
                "script_versions.project_id",
            ],
            name="fk_selective_rescan_checkpoints_script_version_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["item_id", "org_id", "project_id"],
            [
                "clearance_items.id",
                "clearance_items.org_id",
                "clearance_items.project_id",
            ],
            name="fk_selective_rescan_checkpoints_item_scope",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "idx_selective_rescan_checkpoints_job",
        "selective_rescan_checkpoints",
        ["org_id", "project_id", "job_id", "stage"],
    )
    no_target = sa.text("script_version_id IS NULL AND item_id IS NULL")
    script_version_target = sa.text("script_version_id IS NOT NULL AND item_id IS NULL")
    item_target = sa.text("script_version_id IS NULL AND item_id IS NOT NULL")
    op.create_index(
        "uq_selective_rescan_checkpoints_job_stage",
        "selective_rescan_checkpoints",
        ["org_id", "project_id", "job_id", "stage"],
        unique=True,
        sqlite_where=no_target,
        postgresql_where=no_target,
    )
    op.create_index(
        "uq_selective_rescan_checkpoints_script_version",
        "selective_rescan_checkpoints",
        ["org_id", "project_id", "job_id", "stage", "script_version_id"],
        unique=True,
        sqlite_where=script_version_target,
        postgresql_where=script_version_target,
    )
    op.create_index(
        "uq_selective_rescan_checkpoints_item",
        "selective_rescan_checkpoints",
        ["org_id", "project_id", "job_id", "stage", "item_id"],
        unique=True,
        sqlite_where=item_target,
        postgresql_where=item_target,
    )


def downgrade() -> None:
    op.drop_table("selective_rescan_checkpoints")
    op.drop_table("evidence_carry_forwards")

    with op.batch_alter_table("evidence_claims") as batch_op:
        batch_op.drop_constraint(
            "uq_evidence_claims_carry_provenance",
            type_="unique",
        )

    with op.batch_alter_table("clearance_items") as batch_op:
        batch_op.drop_constraint(
            "fk_clearance_items_predecessor_version_scope",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_clearance_items_predecessor_item_scope",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "ck_clearance_items_predecessor_not_self",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_clearance_items_lineage_state",
            type_="check",
        )
        batch_op.drop_constraint(
            "uq_clearance_items_successor_projection",
            type_="unique",
        )
        batch_op.drop_constraint(
            "uq_clearance_items_carry_edge",
            type_="unique",
        )
        batch_op.drop_constraint(
            "uq_clearance_items_predecessor_item_provenance",
            type_="unique",
        )
        batch_op.drop_column("carried_forward_confirmation_required")
        batch_op.drop_column("lineage_kind")
        batch_op.drop_column("predecessor_version_id")
        batch_op.drop_column("predecessor_item_id")

    op.drop_table("script_element_lineage")
    op.drop_index("idx_script_diffs_after_version", table_name="script_diffs")

    with op.batch_alter_table("script_diffs") as batch_op:
        batch_op.drop_constraint(
            "fk_script_diffs_after_version_scope",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_script_diffs_before_version_scope",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "ck_script_diffs_distinct_versions",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_script_diffs_adjacent_ordinals",
            type_="check",
        )
        batch_op.drop_constraint(
            "uq_script_diffs_lineage_provenance",
            type_="unique",
        )
        batch_op.drop_constraint(
            "uq_script_diffs_after_version",
            type_="unique",
        )
        batch_op.drop_constraint(
            "uq_script_diffs_adjacent",
            type_="unique",
        )
        batch_op.drop_column("summary_payload")
        batch_op.drop_column("algorithm_version")
        batch_op.drop_column("after_ordinal")
        batch_op.drop_column("before_ordinal")
        batch_op.drop_column("script_id")

    op.drop_index(
        "uq_script_versions_checkpoint_scope",
        table_name="script_versions",
    )
    with op.batch_alter_table("script_versions") as batch_op:
        batch_op.drop_constraint(
            "fk_script_versions_committing_actor_membership",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_script_versions_predecessor_scope",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "ck_script_versions_predecessor_adjacency",
            type_="check",
        )
        batch_op.drop_constraint(
            "uq_script_versions_predecessor_provenance",
            type_="unique",
        )
        batch_op.drop_constraint(
            "uq_script_versions_revision_provenance",
            type_="unique",
        )
        batch_op.drop_column("committed_by_actor_id")
        batch_op.drop_column("predecessor_ordinal")
        batch_op.drop_column("predecessor_version_id")

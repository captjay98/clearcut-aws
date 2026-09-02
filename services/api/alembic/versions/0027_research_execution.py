"""Persist lease-fenced research planning, Search authorization, and snapshots.

Revision ID: 0027_research_execution
Revises: 0026_full_provenance
Create Date: 2026-09-03 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027_research_execution"
down_revision: str | None = "0026_full_provenance"
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
        "clearance_items",
        "uq_clearance_items_research_scope",
        ["id", "org_id", "project_id", "version_id"],
    )
    _ensure_unique_constraint(
        "research_runs",
        "uq_research_runs_scope",
        ["id", "org_id", "project_id", "item_id"],
    )

    with op.batch_alter_table("research_runs") as batch_op:
        batch_op.add_column(sa.Column("job_id", sa.UUID(as_uuid=True), nullable=True))
        batch_op.add_column(
            sa.Column("version_id", sa.UUID(as_uuid=True), nullable=True)
        )
        batch_op.add_column(sa.Column("job_attempt_number", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("lease_owner", sa.String(255), nullable=True))
        batch_op.add_column(
            sa.Column("correlation_id", sa.UUID(as_uuid=True), nullable=True)
        )
        batch_op.add_column(sa.Column("objective", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("input_sha256", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("completed_at", sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column("safe_error", sa.JSON(), nullable=True))
        batch_op.create_unique_constraint(
            "uq_research_runs_job_attempt",
            ["job_id", "job_attempt_number"],
        )
        batch_op.create_check_constraint(
            "ck_research_runs_attempt",
            "job_attempt_number IS NULL OR job_attempt_number > 0",
        )
        batch_op.create_check_constraint(
            "ck_research_runs_input_hash",
            "input_sha256 IS NULL OR length(input_sha256) = 64",
        )
        batch_op.create_check_constraint(
            "ck_research_runs_status",
            "status IN ('planning', 'running', 'succeeded', 'completed', 'failed')",
        )
        batch_op.create_foreign_key(
            "fk_research_runs_job_scope",
            "jobs",
            ["job_id", "org_id", "project_id"],
            ["id", "org_id", "project_id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_research_runs_item_version_scope",
            "clearance_items",
            ["item_id", "org_id", "project_id", "version_id"],
            ["id", "org_id", "project_id", "version_id"],
            ondelete="CASCADE",
        )

    op.execute(
        sa.text(
            "UPDATE research_runs SET version_id = ("
            "SELECT version_id FROM clearance_items "
            "WHERE clearance_items.id = research_runs.item_id) "
            "WHERE version_id IS NULL"
        )
    )

    with op.batch_alter_table("research_queries") as batch_op:
        batch_op.add_column(sa.Column("item_id", sa.UUID(as_uuid=True), nullable=True))
        batch_op.add_column(
            sa.Column("version_id", sa.UUID(as_uuid=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True)
        )

    op.execute(
        sa.text(
            "UPDATE research_queries SET "
            "org_id = (SELECT org_id FROM research_runs WHERE id = run_id), "
            "project_id = (SELECT project_id FROM research_runs WHERE id = run_id), "
            "item_id = (SELECT item_id FROM research_runs WHERE id = run_id), "
            "version_id = (SELECT version_id FROM research_runs WHERE id = run_id), "
            "created_at = CURRENT_TIMESTAMP"
        )
    )
    with op.batch_alter_table("research_queries") as batch_op:
        batch_op.alter_column("org_id", nullable=False)
        batch_op.alter_column("project_id", nullable=False)
        batch_op.alter_column("item_id", nullable=False)
        batch_op.alter_column("version_id", nullable=False)
        batch_op.alter_column("created_at", nullable=False)
        batch_op.create_unique_constraint(
            "uq_research_queries_run_ordinal", ["run_id", "ordinal"]
        )
        batch_op.create_unique_constraint(
            "uq_research_queries_provenance",
            ["id", "run_id", "org_id", "project_id", "item_id"],
        )
        batch_op.create_check_constraint(
            "ck_research_queries_ordinal", "ordinal > 0"
        )
        batch_op.create_foreign_key(
            "fk_research_queries_research_item_scope",
            "research_runs",
            ["run_id", "org_id", "project_id", "item_id"],
            ["id", "org_id", "project_id", "item_id"],
            ondelete="CASCADE",
        )

    with op.batch_alter_table("provider_attempts") as batch_op:
        batch_op.add_column(sa.Column("item_id", sa.UUID(as_uuid=True), nullable=True))
        batch_op.add_column(sa.Column("query_id", sa.UUID(as_uuid=True), nullable=True))
        batch_op.add_column(sa.Column("job_attempt_number", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("lease_owner", sa.String(255), nullable=True))
        batch_op.add_column(
            sa.Column("correlation_id", sa.UUID(as_uuid=True), nullable=True)
        )
        batch_op.add_column(sa.Column("requested_model", sa.String(255)))
        batch_op.add_column(sa.Column("returned_model", sa.String(255)))
        batch_op.add_column(sa.Column("response_id", sa.String(255)))
        batch_op.add_column(sa.Column("provider_session_id", sa.String(255)))
        batch_op.add_column(sa.Column("input_sha256", sa.String(64)))
        batch_op.add_column(sa.Column("input_tokens", sa.Integer()))
        batch_op.add_column(sa.Column("output_tokens", sa.Integer()))
        batch_op.add_column(sa.Column("total_tokens", sa.Integer()))
        batch_op.add_column(sa.Column("duration_ms", sa.Integer()))
        batch_op.add_column(sa.Column("warnings", sa.JSON()))
        batch_op.add_column(sa.Column("safe_error", sa.JSON()))
        batch_op.add_column(sa.Column("completed_at", sa.DateTime(timezone=True)))
        batch_op.add_column(
            sa.Column(
                "authorizing_search_attempt_id",
                sa.UUID(as_uuid=True),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column("authorizing_operation_kind", sa.String(50), nullable=True)
        )

    op.execute(
        sa.text(
            "UPDATE provider_attempts SET "
            "org_id = (SELECT org_id FROM research_runs WHERE id = run_id), "
            "project_id = (SELECT project_id FROM research_runs WHERE id = run_id), "
            "item_id = (SELECT item_id FROM research_runs WHERE id = run_id)"
        )
    )
    with op.batch_alter_table("provider_attempts") as batch_op:
        batch_op.alter_column("org_id", nullable=False)
        batch_op.alter_column("project_id", nullable=False)
        batch_op.alter_column("item_id", nullable=False)
        batch_op.create_unique_constraint(
            "uq_provider_attempts_scope",
            ["id", "run_id", "org_id", "project_id", "item_id"],
        )
        batch_op.create_unique_constraint(
            "uq_provider_attempts_query_scope",
            ["id", "run_id", "org_id", "project_id", "item_id", "query_id"],
        )
        batch_op.create_unique_constraint(
            "uq_provider_attempts_operation_provenance",
            [
                "id",
                "run_id",
                "org_id",
                "project_id",
                "item_id",
                "query_id",
                "operation_kind",
            ],
        )
        batch_op.create_unique_constraint(
            "uq_provider_attempts_snapshot_provenance",
            [
                "id",
                "run_id",
                "org_id",
                "project_id",
                "item_id",
                "query_id",
                "authorizing_search_attempt_id",
            ],
        )
        batch_op.create_unique_constraint(
            "uq_provider_attempts_extract_target_provenance",
            [
                "id",
                "run_id",
                "org_id",
                "project_id",
                "item_id",
                "query_id",
                "authorizing_search_attempt_id",
                "operation_kind",
            ],
        )
        batch_op.create_check_constraint(
            "ck_provider_attempts_operation",
            "operation_kind IN ('planning', 'search', 'extract')",
        )
        batch_op.create_check_constraint(
            "ck_provider_attempts_status",
            "status IN ('pending', 'succeeded', 'failed')",
        )
        batch_op.create_check_constraint(
            "ck_provider_attempts_duration",
            "duration_ms IS NULL OR duration_ms >= 0",
        )
        batch_op.create_check_constraint(
            "ck_provider_attempts_input_hash",
            "input_sha256 IS NULL OR length(input_sha256) = 64",
        )
        batch_op.create_check_constraint(
            "ck_provider_attempts_authorizing_search",
            "job_attempt_number IS NULL OR "
            "(operation_kind = 'planning' AND query_id IS NULL "
            "AND authorizing_search_attempt_id IS NULL "
            "AND authorizing_operation_kind IS NULL) OR "
            "(operation_kind = 'search' AND query_id IS NOT NULL "
            "AND authorizing_search_attempt_id IS NOT NULL "
            "AND authorizing_operation_kind = 'search') OR "
            "(operation_kind = 'extract' AND query_id IS NOT NULL "
            "AND authorizing_search_attempt_id IS NOT NULL "
            "AND authorizing_operation_kind = 'search')",
        )
        batch_op.create_foreign_key(
            "fk_provider_attempts_research_item_scope",
            "research_runs",
            ["run_id", "org_id", "project_id", "item_id"],
            ["id", "org_id", "project_id", "item_id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_provider_attempts_authorizing_search_provenance",
            "provider_attempts",
            [
                "authorizing_search_attempt_id",
                "run_id",
                "org_id",
                "project_id",
                "item_id",
                "query_id",
                "authorizing_operation_kind",
            ],
            [
                "id",
                "run_id",
                "org_id",
                "project_id",
                "item_id",
                "query_id",
                "operation_kind",
            ],
        )

    op.create_table(
        "search_result_authorizations",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("item_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("query_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("search_attempt_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "search_operation_kind",
            sa.String(50),
            nullable=False,
            server_default=sa.text("'search'"),
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("publisher", sa.Text(), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("published_date", sa.String(50)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "id",
            "org_id",
            "project_id",
            "item_id",
            "run_id",
            name="uq_search_authorizations_scope",
        ),
        sa.UniqueConstraint(
            "id",
            "run_id",
            "org_id",
            "project_id",
            "item_id",
            "query_id",
            "search_attempt_id",
            name="uq_search_authorizations_provenance",
        ),
        sa.UniqueConstraint(
            "id",
            "run_id",
            "org_id",
            "project_id",
            "item_id",
            "query_id",
            "search_attempt_id",
            "canonical_url",
            name="uq_search_authorizations_extract_target_provenance",
        ),
        sa.UniqueConstraint(
            "search_attempt_id",
            "canonical_url",
            name="uq_search_authorizations_attempt_url",
        ),
        sa.CheckConstraint("ordinal > 0", name="ck_search_authorizations_ordinal"),
        sa.CheckConstraint(
            "search_operation_kind = 'search'",
            name="ck_search_authorizations_operation",
        ),
        sa.ForeignKeyConstraint(
            ["run_id", "org_id", "project_id", "item_id"],
            [
                "research_runs.id",
                "research_runs.org_id",
                "research_runs.project_id",
                "research_runs.item_id",
            ],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["query_id", "run_id", "org_id", "project_id", "item_id"],
            [
                "research_queries.id",
                "research_queries.run_id",
                "research_queries.org_id",
                "research_queries.project_id",
                "research_queries.item_id",
            ],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            [
                "search_attempt_id",
                "run_id",
                "org_id",
                "project_id",
                "item_id",
                "query_id",
                "search_operation_kind",
            ],
            [
                "provider_attempts.id",
                "provider_attempts.run_id",
                "provider_attempts.org_id",
                "provider_attempts.project_id",
                "provider_attempts.item_id",
                "provider_attempts.query_id",
                "provider_attempts.operation_kind",
            ],
            name="fk_search_authorizations_attempt_provenance",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "idx_search_authorizations_run",
        "search_result_authorizations",
        ["org_id", "project_id", "item_id", "run_id", "query_id", "ordinal"],
    )

    op.create_table(
        "extract_target_authorizations",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("item_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("query_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("extract_attempt_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "extract_operation_kind",
            sa.String(50),
            nullable=False,
            server_default=sa.text("'extract'"),
        ),
        sa.Column("authorization_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "authorizing_search_attempt_id",
            sa.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "extract_attempt_id",
            "canonical_url",
            name="uq_extract_targets_attempt_url",
        ),
        sa.UniqueConstraint(
            "extract_attempt_id",
            "ordinal",
            name="uq_extract_targets_attempt_ordinal",
        ),
        sa.CheckConstraint("ordinal > 0", name="ck_extract_targets_ordinal"),
        sa.CheckConstraint(
            "extract_operation_kind = 'extract'",
            name="ck_extract_targets_operation",
        ),
        sa.ForeignKeyConstraint(
            [
                "extract_attempt_id",
                "run_id",
                "org_id",
                "project_id",
                "item_id",
                "query_id",
                "authorizing_search_attempt_id",
                "extract_operation_kind",
            ],
            [
                "provider_attempts.id",
                "provider_attempts.run_id",
                "provider_attempts.org_id",
                "provider_attempts.project_id",
                "provider_attempts.item_id",
                "provider_attempts.query_id",
                "provider_attempts.authorizing_search_attempt_id",
                "provider_attempts.operation_kind",
            ],
            name="fk_extract_targets_attempt_provenance",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            [
                "authorization_id",
                "run_id",
                "org_id",
                "project_id",
                "item_id",
                "query_id",
                "authorizing_search_attempt_id",
                "canonical_url",
            ],
            [
                "search_result_authorizations.id",
                "search_result_authorizations.run_id",
                "search_result_authorizations.org_id",
                "search_result_authorizations.project_id",
                "search_result_authorizations.item_id",
                "search_result_authorizations.query_id",
                "search_result_authorizations.search_attempt_id",
                "search_result_authorizations.canonical_url",
            ],
            name="fk_extract_targets_authorization_provenance",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "idx_extract_targets_attempt",
        "extract_target_authorizations",
        ["org_id", "project_id", "item_id", "run_id", "extract_attempt_id"],
    )

    with op.batch_alter_table("source_snapshots") as batch_op:
        batch_op.add_column(sa.Column("query_id", sa.UUID(as_uuid=True)))
        batch_op.add_column(sa.Column("provider_attempt_id", sa.UUID(as_uuid=True)))
        batch_op.add_column(sa.Column("authorization_id", sa.UUID(as_uuid=True)))
        batch_op.add_column(
            sa.Column(
                "authorizing_search_attempt_id",
                sa.UUID(as_uuid=True),
                nullable=True,
            )
        )
        batch_op.create_unique_constraint(
            "uq_source_snapshots_research_provenance",
            [
                "id",
                "org_id",
                "project_id",
                "item_id",
                "run_id",
                "query_id",
                "provider_attempt_id",
            ],
        )
        batch_op.create_check_constraint(
            "ck_source_snapshots_research_provenance",
            "(query_id IS NULL AND provider_attempt_id IS NULL "
            "AND authorization_id IS NULL "
            "AND authorizing_search_attempt_id IS NULL) OR "
            "(query_id IS NOT NULL AND provider_attempt_id IS NOT NULL "
            "AND authorization_id IS NOT NULL "
            "AND authorizing_search_attempt_id IS NOT NULL)",
        )
        batch_op.create_foreign_key(
            "fk_source_snapshots_attempt_provenance",
            "provider_attempts",
            [
                "provider_attempt_id",
                "run_id",
                "org_id",
                "project_id",
                "item_id",
                "query_id",
                "authorizing_search_attempt_id",
            ],
            [
                "id",
                "run_id",
                "org_id",
                "project_id",
                "item_id",
                "query_id",
                "authorizing_search_attempt_id",
            ],
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            "fk_source_snapshots_authorization_provenance",
            "search_result_authorizations",
            [
                "authorization_id",
                "run_id",
                "org_id",
                "project_id",
                "item_id",
                "query_id",
                "authorizing_search_attempt_id",
            ],
            [
                "id",
                "run_id",
                "org_id",
                "project_id",
                "item_id",
                "query_id",
                "search_attempt_id",
            ],
            ondelete="RESTRICT",
        )

    with op.batch_alter_table("evidence_claims") as batch_op:
        batch_op.add_column(sa.Column("run_id", sa.UUID(as_uuid=True)))
        batch_op.add_column(sa.Column("query_id", sa.UUID(as_uuid=True)))
        batch_op.add_column(sa.Column("provider_attempt_id", sa.UUID(as_uuid=True)))
        batch_op.create_check_constraint(
            "ck_evidence_claims_research_provenance",
            "(run_id IS NULL AND query_id IS NULL AND provider_attempt_id IS NULL) OR "
            "(run_id IS NOT NULL AND query_id IS NOT NULL "
            "AND provider_attempt_id IS NOT NULL)",
        )
        batch_op.create_foreign_key(
            "fk_evidence_claims_snapshot_research_provenance",
            "source_snapshots",
            [
                "snapshot_id",
                "org_id",
                "project_id",
                "item_id",
                "run_id",
                "query_id",
                "provider_attempt_id",
            ],
            [
                "id",
                "org_id",
                "project_id",
                "item_id",
                "run_id",
                "query_id",
                "provider_attempt_id",
            ],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    with op.batch_alter_table("evidence_claims") as batch_op:
        batch_op.drop_constraint(
            "fk_evidence_claims_snapshot_research_provenance",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "ck_evidence_claims_research_provenance",
            type_="check",
        )
        batch_op.drop_column("provider_attempt_id")
        batch_op.drop_column("query_id")
        batch_op.drop_column("run_id")

    with op.batch_alter_table("source_snapshots") as batch_op:
        batch_op.drop_constraint(
            "fk_source_snapshots_authorization_provenance",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_source_snapshots_attempt_provenance",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "ck_source_snapshots_research_provenance",
            type_="check",
        )
        batch_op.drop_constraint(
            "uq_source_snapshots_research_provenance",
            type_="unique",
        )
        batch_op.drop_column("authorizing_search_attempt_id")
        batch_op.drop_column("authorization_id")
        batch_op.drop_column("provider_attempt_id")
        batch_op.drop_column("query_id")

    op.drop_index(
        "idx_extract_targets_attempt",
        table_name="extract_target_authorizations",
    )
    op.drop_table("extract_target_authorizations")

    op.drop_index(
        "idx_search_authorizations_run",
        table_name="search_result_authorizations",
    )
    op.drop_table("search_result_authorizations")

    with op.batch_alter_table("provider_attempts") as batch_op:
        batch_op.drop_constraint(
            "fk_provider_attempts_authorizing_search_provenance",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_provider_attempts_research_item_scope",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "ck_provider_attempts_authorizing_search",
            type_="check",
        )
        batch_op.drop_constraint("ck_provider_attempts_input_hash", type_="check")
        batch_op.drop_constraint("ck_provider_attempts_duration", type_="check")
        batch_op.drop_constraint("ck_provider_attempts_status", type_="check")
        batch_op.drop_constraint("ck_provider_attempts_operation", type_="check")
        batch_op.drop_constraint(
            "uq_provider_attempts_extract_target_provenance",
            type_="unique",
        )
        batch_op.drop_constraint(
            "uq_provider_attempts_snapshot_provenance",
            type_="unique",
        )
        batch_op.drop_constraint(
            "uq_provider_attempts_operation_provenance",
            type_="unique",
        )
        batch_op.drop_constraint(
            "uq_provider_attempts_query_scope",
            type_="unique",
        )
        batch_op.drop_constraint("uq_provider_attempts_scope", type_="unique")
        for column in (
            "authorizing_operation_kind",
            "authorizing_search_attempt_id",
            "completed_at",
            "safe_error",
            "warnings",
            "duration_ms",
            "total_tokens",
            "output_tokens",
            "input_tokens",
            "input_sha256",
            "provider_session_id",
            "response_id",
            "returned_model",
            "requested_model",
            "correlation_id",
            "lease_owner",
            "job_attempt_number",
            "query_id",
            "item_id",
        ):
            batch_op.drop_column(column)

    with op.batch_alter_table("research_queries") as batch_op:
        batch_op.drop_constraint(
            "fk_research_queries_research_item_scope",
            type_="foreignkey",
        )
        batch_op.drop_constraint("ck_research_queries_ordinal", type_="check")
        batch_op.drop_constraint("uq_research_queries_provenance", type_="unique")
        batch_op.drop_constraint("uq_research_queries_run_ordinal", type_="unique")
        for column in ("created_at", "version_id", "item_id"):
            batch_op.drop_column(column)

    with op.batch_alter_table("research_runs") as batch_op:
        batch_op.drop_constraint(
            "fk_research_runs_item_version_scope",
            type_="foreignkey",
        )
        batch_op.drop_constraint("fk_research_runs_job_scope", type_="foreignkey")
        batch_op.drop_constraint("ck_research_runs_status", type_="check")
        batch_op.drop_constraint("ck_research_runs_input_hash", type_="check")
        batch_op.drop_constraint("ck_research_runs_attempt", type_="check")
        batch_op.drop_constraint(
            "uq_research_runs_job_attempt",
            type_="unique",
        )
        for column in (
            "safe_error",
            "completed_at",
            "input_sha256",
            "objective",
            "correlation_id",
            "lease_owner",
            "job_attempt_number",
            "version_id",
            "job_id",
        ):
            batch_op.drop_column(column)

    with op.batch_alter_table("clearance_items") as batch_op:
        batch_op.drop_constraint(
            "uq_clearance_items_research_scope",
            type_="unique",
        )

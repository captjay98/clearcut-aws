"""Close the governance surfaces: protected configuration lifecycle, learning
candidate stages, organization settings, and per-user notification delivery.

Four areas shipped tables without the columns their surfaces need, and in one
case without the constraint their invariant depends on.

``protected_configurations`` gained no foreign keys and no uniqueness, yet
detection and research both refuse to run unless exactly one row per
organization is active. That invariant lived in two hand-written reader checks
and could not survive a concurrent activation. It becomes a database
constraint here.

``learning_candidates`` carried a single ``is_promoted`` boolean, which cannot
represent the candidate -> canary -> promoted -> rolled-back lifecycle the
product requires, nor record who promoted a candidate or what the regression
gates returned.

Organization settings and notification delivery preference had no persistence
at all.

Deliberately absent: any evidence retention duration. Evidence is kept until
its project is deleted, so a duration column would only let a surface print a
promise the product does not make.

Revision ID: 0036_governance_surfaces
Revises: 0035_revision_selective_rescan
Create Date: 2026-08-31 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0036_governance_surfaces"
down_revision: str | None = "0035_revision_selective_rescan"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSON = sa.JSON().with_variant(JSONB(), "postgresql")

_CONFIG_LIFECYCLES = ("draft", "validated", "active", "superseded")
_LEARNING_STAGES = ("candidate", "shadow", "canary", "promoted", "rolled_back")
_CADENCES = ("off", "manual", "daily", "weekly")
_DELIVERY_CHANNELS = ("in_app", "email", "push")


def upgrade() -> None:
    _upgrade_protected_configurations()
    _upgrade_learning_candidates()
    _upgrade_organization_settings()
    _create_notification_delivery_preferences()


def _upgrade_protected_configurations() -> None:
    """Give the policy binding referential integrity and a real lifecycle."""
    with op.batch_alter_table("protected_configurations") as batch:
        batch.add_column(sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("superseded_by", sa.UUID(as_uuid=True), nullable=True))
        batch.add_column(sa.Column("validated_by", sa.UUID(as_uuid=True), nullable=True))
        batch.add_column(sa.Column("created_by", sa.UUID(as_uuid=True), nullable=True))
        batch.add_column(sa.Column("label", sa.String(200), nullable=True))
        batch.add_column(
            sa.Column("validation_issues", _JSON, nullable=False, server_default="[]")
        )
        batch.create_foreign_key(
            "fk_protected_configurations_org",
            "organizations",
            ["org_id"],
            ["id"],
            ondelete="CASCADE",
        )
        # An actor named on a governed activation must not be deletable out
        # from under the record that names them.
        batch.create_foreign_key(
            "fk_protected_configurations_activated_by",
            "users",
            ["activated_by"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_check_constraint(
            "ck_protected_configurations_lifecycle",
            sa.text(
                "lifecycle IN ("
                + ", ".join(f"'{value}'" for value in _CONFIG_LIFECYCLES)
                + ")"
            ),
        )
        # No accountability constraint on active rows. A human activation records
        # its actor through the governed command path, but the binding created
        # when an organization is bootstrapped is a system default rather than a
        # decision someone made, and demanding an actor there would either block
        # onboarding or invite a fabricated one.

    op.create_index(
        "idx_protected_configurations_org_lifecycle",
        "protected_configurations",
        ["org_id", "lifecycle"],
    )
    # The invariant detection and research depend on, enforced where it cannot
    # be raced: at most one active binding per organization.
    op.create_index(
        "uq_protected_configurations_one_active",
        "protected_configurations",
        ["org_id"],
        unique=True,
        sqlite_where=sa.text("lifecycle = 'active'"),
        postgresql_where=sa.text("lifecycle = 'active'"),
    )


def _upgrade_learning_candidates() -> None:
    """Replace the promoted boolean with an auditable stage machine."""
    with op.batch_alter_table("learning_candidates") as batch:
        batch.add_column(sa.Column("stage", sa.String(50), nullable=True))
        batch.add_column(sa.Column("title", sa.String(200), nullable=True))
        batch.add_column(sa.Column("summary", sa.Text(), nullable=True))
        batch.add_column(
            sa.Column("regression_cases_passed", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(
            sa.Column("regression_cases_total", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(sa.Column("canary_started_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("promoted_by", sa.UUID(as_uuid=True), nullable=True))
        batch.add_column(sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("rolled_back_by", sa.UUID(as_uuid=True), nullable=True))
        batch.add_column(sa.Column("rollback_reason", sa.Text(), nullable=True))
        batch.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))

    # Backfill the stage from the boolean it replaces before demanding a value.
    op.execute(
        sa.text(
            "UPDATE learning_candidates SET stage = CASE "
            "WHEN is_promoted THEN 'promoted' ELSE 'candidate' END "
            "WHERE stage IS NULL"
        )
    )

    with op.batch_alter_table("learning_candidates") as batch:
        batch.alter_column("stage", existing_type=sa.String(50), nullable=False)
        batch.create_foreign_key(
            "fk_learning_candidates_org",
            "organizations",
            ["org_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.create_foreign_key(
            "fk_learning_candidates_promoted_by",
            "users",
            ["promoted_by"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_foreign_key(
            "fk_learning_candidates_rolled_back_by",
            "users",
            ["rolled_back_by"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_check_constraint(
            "ck_learning_candidates_stage",
            sa.text(
                "stage IN (" + ", ".join(f"'{value}'" for value in _LEARNING_STAGES) + ")"
            ),
        )
        batch.create_check_constraint(
            "ck_learning_candidates_promotion_accountable",
            sa.text(
                "stage <> 'promoted' OR (promoted_by IS NOT NULL AND promoted_at IS NOT NULL)"
            ),
        )
        batch.create_check_constraint(
            "ck_learning_candidates_rollback_accountable",
            sa.text(
                "stage <> 'rolled_back' OR "
                "(rolled_back_by IS NOT NULL AND rolled_back_at IS NOT NULL)"
            ),
        )
        batch.create_check_constraint(
            "ck_learning_candidates_regression_counts",
            sa.text(
                "regression_cases_passed >= 0 AND "
                "regression_cases_total >= regression_cases_passed"
            ),
        )
        batch.create_check_constraint(
            "ck_learning_candidates_canary_pass_rate",
            sa.text("canary_pass_rate >= 0 AND canary_pass_rate <= 1"),
        )

    op.create_index(
        "idx_learning_candidates_org_stage",
        "learning_candidates",
        ["org_id", "stage", "created_at"],
    )


def _upgrade_organization_settings() -> None:
    """Persist the organization-level settings the surface already edits."""
    with op.batch_alter_table("organizations") as batch:
        batch.add_column(sa.Column("jurisdiction", sa.String(200), nullable=True))
        batch.add_column(
            sa.Column(
                "default_monitoring_cadence",
                sa.String(20),
                nullable=False,
                server_default="weekly",
            )
        )
        batch.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
        # Cadence is stored canonically and rendered through a label map, so the
        # stored token never leaks into a surface or an audit entry verbatim.
        batch.create_check_constraint(
            "ck_organizations_default_monitoring_cadence",
            sa.text(
                "default_monitoring_cadence IN ("
                + ", ".join(f"'{value}'" for value in _CADENCES)
                + ")"
            ),
        )


def _create_notification_delivery_preferences() -> None:
    """Delivery channel is personal, so it is keyed by user within an org."""
    op.create_table(
        "notification_delivery_preferences",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False, server_default="in_app"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("org_id", "user_id", name="uq_notification_delivery_scope"),
        sa.CheckConstraint(
            "channel IN (" + ", ".join(f"'{value}'" for value in _DELIVERY_CHANNELS) + ")",
            name="ck_notification_delivery_channel",
        ),
    )


def downgrade() -> None:
    op.drop_table("notification_delivery_preferences")

    with op.batch_alter_table("organizations") as batch:
        batch.drop_constraint("ck_organizations_default_monitoring_cadence", type_="check")
        batch.drop_column("version")
        batch.drop_column("default_monitoring_cadence")
        batch.drop_column("jurisdiction")

    op.drop_index("idx_learning_candidates_org_stage", table_name="learning_candidates")
    with op.batch_alter_table("learning_candidates") as batch:
        for name in (
            "ck_learning_candidates_canary_pass_rate",
            "ck_learning_candidates_regression_counts",
            "ck_learning_candidates_rollback_accountable",
            "ck_learning_candidates_promotion_accountable",
            "ck_learning_candidates_stage",
        ):
            batch.drop_constraint(name, type_="check")
        for name in (
            "fk_learning_candidates_rolled_back_by",
            "fk_learning_candidates_promoted_by",
            "fk_learning_candidates_org",
        ):
            batch.drop_constraint(name, type_="foreignkey")
        for name in (
            "version",
            "rollback_reason",
            "rolled_back_by",
            "rolled_back_at",
            "promoted_by",
            "promoted_at",
            "canary_started_at",
            "regression_cases_total",
            "regression_cases_passed",
            "summary",
            "title",
            "stage",
        ):
            batch.drop_column(name)

    op.drop_index(
        "uq_protected_configurations_one_active", table_name="protected_configurations"
    )
    op.drop_index(
        "idx_protected_configurations_org_lifecycle", table_name="protected_configurations"
    )
    with op.batch_alter_table("protected_configurations") as batch:
        batch.drop_constraint("ck_protected_configurations_lifecycle", type_="check")
        batch.drop_constraint("fk_protected_configurations_activated_by", type_="foreignkey")
        batch.drop_constraint("fk_protected_configurations_org", type_="foreignkey")
        for name in (
            "validation_issues",
            "label",
            "created_by",
            "validated_by",
            "superseded_by",
            "superseded_at",
            "activated_at",
            "validated_at",
        ):
            batch.drop_column(name)

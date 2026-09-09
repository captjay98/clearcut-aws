"""Bind a rewrite proposal to the script version it produced.

``rewrite_proposals`` (0013) can record that a rewrite was proposed, approved,
rejected, or withdrawn, and its ``status`` vocabulary already includes
``materialized`` -- but the table has no column naming the successor version a
materialized proposal produced. Without that binding, "this proposal became
version 3" is unrepresentable, so the review surface cannot show which version
carries an approved rewrite, and a proposal could be reported as materialized
while pointing at nothing.

``resulting_version_id`` closes that gap. It is nullable because approval
deliberately does not create a version: materializing an approved rewrite into
the next immutable version is a separate accountable step, and until it runs the
binding genuinely does not exist. The check constraint makes the invariant a
database rule rather than a convention -- a proposal may only be ``materialized``
once it is bound to a version -- and the foreign key is scoped through
``(id, org_id, project_id)`` on ``script_versions`` (the unique index 0035
created), so a proposal can never be bound to another tenant's version.

Revision ID: 0037_rewrite_result_binding
Revises: 0036_governance_surfaces
Create Date: 2026-08-31 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0037_rewrite_result_binding"
down_revision: str | None = "0036_governance_surfaces"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("rewrite_proposals") as batch_op:
        batch_op.add_column(sa.Column("resulting_version_id", sa.UUID(as_uuid=True), nullable=True))
        batch_op.create_foreign_key(
            "fk_rewrite_proposals_resulting_version_scope",
            "script_versions",
            ["resulting_version_id", "org_id", "project_id"],
            ["id", "org_id", "project_id"],
            ondelete="RESTRICT",
        )
        batch_op.create_check_constraint(
            "ck_rewrite_proposals_materialized_binding",
            "status <> 'materialized' OR resulting_version_id IS NOT NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("rewrite_proposals") as batch_op:
        batch_op.drop_constraint(
            "ck_rewrite_proposals_materialized_binding", type_="check"
        )
        batch_op.drop_constraint(
            "fk_rewrite_proposals_resulting_version_scope", type_="foreignkey"
        )
        batch_op.drop_column("resulting_version_id")

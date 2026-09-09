"""Bind comment mentions to an exact tenant-scoped revision identity.

Revision ID: 0033_comment_mention_scope
Revises: 0032_comment_mention_revision
Create Date: 2026-09-05 02:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0033_comment_mention_scope"
down_revision: str | None = "0032_comment_mention_revision"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("governed_comment_revisions") as batch_op:
        batch_op.create_unique_constraint(
            "uq_governed_comment_revisions_identity_scope",
            ["id", "org_id", "project_id", "comment_id"],
        )

    with op.batch_alter_table("governed_comment_mentions") as batch_op:
        batch_op.drop_constraint(
            "fk_governed_comment_mentions_revision",
            type_="foreignkey",
        )
        batch_op.create_foreign_key(
            "fk_governed_comment_mentions_revision",
            "governed_comment_revisions",
            ["revision_id", "org_id", "project_id", "comment_id"],
            ["id", "org_id", "project_id", "comment_id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    with op.batch_alter_table("governed_comment_mentions") as batch_op:
        batch_op.drop_constraint(
            "fk_governed_comment_mentions_revision",
            type_="foreignkey",
        )
        batch_op.create_foreign_key(
            "fk_governed_comment_mentions_revision",
            "governed_comment_revisions",
            ["revision_id"],
            ["id"],
            ondelete="CASCADE",
        )

    with op.batch_alter_table("governed_comment_revisions") as batch_op:
        batch_op.drop_constraint(
            "uq_governed_comment_revisions_identity_scope",
            type_="unique",
        )

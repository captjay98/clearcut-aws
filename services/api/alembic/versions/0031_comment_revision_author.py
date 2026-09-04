"""Attribute every immutable comment revision to its author.

Revision ID: 0031_comment_revision_author
Revises: 0030_governed_collaboration
Create Date: 2026-09-05 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031_comment_revision_author"
down_revision: str | None = "0030_governed_collaboration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("governed_comment_revisions") as batch_op:
        batch_op.add_column(sa.Column("author_id", sa.UUID(as_uuid=True), nullable=True))

    op.execute(
        sa.text(
            "UPDATE governed_comment_revisions "
            "SET author_id = ("
            "SELECT governed_comments.author_id FROM governed_comments "
            "WHERE governed_comments.id = governed_comment_revisions.comment_id "
            "AND governed_comments.org_id = governed_comment_revisions.org_id "
            "AND governed_comments.project_id = governed_comment_revisions.project_id"
            ")"
        )
    )

    with op.batch_alter_table("governed_comment_revisions") as batch_op:
        batch_op.alter_column("author_id", existing_type=sa.UUID(as_uuid=True), nullable=False)
        batch_op.create_foreign_key(
            "fk_governed_comment_revisions_author",
            "users",
            ["author_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    with op.batch_alter_table("governed_comment_revisions") as batch_op:
        batch_op.drop_constraint(
            "fk_governed_comment_revisions_author",
            type_="foreignkey",
        )
        batch_op.drop_column("author_id")

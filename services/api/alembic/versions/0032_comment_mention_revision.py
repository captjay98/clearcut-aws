"""Bind each comment mention to its immutable revision.

Revision ID: 0032_comment_mention_revision
Revises: 0031_comment_revision_author
Create Date: 2026-09-05 01:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032_comment_mention_revision"
down_revision: str | None = "0031_comment_revision_author"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns(
            "governed_comment_mentions"
        )
    }
    if "revision_id" not in columns:
        with op.batch_alter_table("governed_comment_mentions") as batch_op:
            batch_op.add_column(sa.Column("revision_id", sa.UUID(as_uuid=True), nullable=True))

    op.execute(
        sa.text(
            "UPDATE governed_comment_mentions "
            "SET revision_id = ("
            "SELECT governed_comment_revisions.id "
            "FROM governed_comment_revisions "
            "WHERE governed_comment_revisions.comment_id = "
            "governed_comment_mentions.comment_id "
            "AND governed_comment_revisions.org_id = governed_comment_mentions.org_id "
            "AND governed_comment_revisions.project_id = "
            "governed_comment_mentions.project_id "
            "ORDER BY governed_comment_revisions.ordinal DESC LIMIT 1"
            ")"
        )
    )

    with op.batch_alter_table("governed_comment_mentions") as batch_op:
        batch_op.drop_constraint(
            "uq_governed_comment_mentions_recipient",
            type_="unique",
        )
        batch_op.alter_column(
            "revision_id",
            existing_type=sa.UUID(as_uuid=True),
            nullable=False,
        )
        batch_op.create_unique_constraint(
            "uq_governed_comment_mentions_revision_recipient",
            [
                "org_id",
                "project_id",
                "comment_id",
                "revision_id",
                "recipient_user_id",
            ],
        )
        batch_op.create_foreign_key(
            "fk_governed_comment_mentions_revision",
            "governed_comment_revisions",
            ["revision_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    # 0031 can represent only one mention per recipient/comment. Revision-aware
    # history may contain the same recipient on several revisions, so retain the
    # latest revision's row deterministically before restoring the legacy key.
    op.execute(
        sa.text(
            "DELETE FROM governed_comment_mentions WHERE id IN ("
            "SELECT mention_id FROM ("
            "SELECT m.id AS mention_id, ROW_NUMBER() OVER ("
            "PARTITION BY m.org_id, m.project_id, m.comment_id, m.recipient_user_id "
            "ORDER BY r.ordinal DESC, m.id DESC"
            ") AS duplicate_rank "
            "FROM governed_comment_mentions m "
            "JOIN governed_comment_revisions r ON r.id = m.revision_id"
            ") ranked WHERE duplicate_rank > 1"
            ")"
        )
    )

    with op.batch_alter_table("governed_comment_mentions") as batch_op:
        batch_op.drop_constraint(
            "fk_governed_comment_mentions_revision",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "uq_governed_comment_mentions_revision_recipient",
            type_="unique",
        )
        batch_op.create_unique_constraint(
            "uq_governed_comment_mentions_recipient",
            ["org_id", "project_id", "comment_id", "recipient_user_id"],
        )
        batch_op.drop_column("revision_id")

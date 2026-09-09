"""Give a clearance item an optional review due date.

The review worklist assigns work with a due date, but ``clearance_items`` had
nowhere to record it: ``:assign`` only set ``assigned_to_user_id``. ``due_at``
adds that column. It is nullable because most items carry no deadline until a
reviewer sets one, and it is a plain timestamp rather than a separate
assignments table because a due date is a property of the item's current review,
not an independent record. Severity and confidence are intentionally NOT stored
here -- they are derived in the read model from category risk and the detection
uncertainty already persisted on ``detection_candidates``.

Revision ID: 0038_item_due_at
Revises: 0037_rewrite_result_binding
Create Date: 2026-09-09 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0038_item_due_at"
down_revision: str | None = "0037_rewrite_result_binding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("clearance_items") as batch_op:
        batch_op.add_column(
            sa.Column("due_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("clearance_items") as batch_op:
        batch_op.drop_column("due_at")

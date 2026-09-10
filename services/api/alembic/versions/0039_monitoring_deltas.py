"""Persist monitoring source deltas (change signals) and their review outcome.

A scheduled or manual monitoring recheck compares the prior source snapshot
against the freshly retrieved one and computes a :class:`SourceDelta`. Until now
that delta was computed and dropped: nothing stored it, so a detected change
never became a pending review item and the review decision lived only in an
in-memory dict that vanished with the process. ``monitoring_source_deltas``
gives the change signal a durable home and folds the review outcome onto the
same row, so one row is the whole review target: it starts ``pending`` with the
outcome columns null, and a governed review decision flips it to ``reviewed``
and stamps ``review_id`` (the accountable decision identity), ``reviewed_by``,
``review_action`` (keep_with_follow_up/reopen/refer), ``review_rationale``, and
``reviewed_at`` in the same transaction as the authoritative audit event.

The prior/current excerpts are denormalized onto the row rather than joined from
``source_snapshots`` on every read: a change signal must remain reviewable as a
self-contained record of what changed even if a snapshot is later pruned, and
the pending-signal list must not depend on a snapshot still existing. The
snapshot ids are kept as nullable references (plain columns, no hard foreign
key) for provenance without making the delta's existence contingent on them.

Revision ID: 0039_monitoring_deltas
Revises: 0038_item_due_at
Create Date: 2026-09-10 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0039_monitoring_deltas"
down_revision: str | None = "0038_item_due_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# JSONB on PostgreSQL, plain JSON elsewhere (e.g. SQLite in tests), matching the
# variant convention used by the later migrations (0035/0036).
_JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "monitoring_source_deltas",
        # The delta id is the review target: one row is one pending change signal.
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "item_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("clearance_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # The watch that produced the signal. SET NULL keeps the delta as a
        # historical change record even if the watch is later removed.
        sa.Column(
            "watch_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("monitoring_watches.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # Snapshot provenance: kept for traceability but deliberately NOT a hard
        # foreign key, so a pruned or not-yet-persisted snapshot never blocks or
        # orphans a change signal. The load-bearing change detail is the
        # denormalized excerpts below, not these ids.
        sa.Column("prior_snapshot_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("new_snapshot_id", sa.UUID(as_uuid=True), nullable=True),
        # The change summary, denormalized so the signal is self-contained.
        sa.Column("prior_excerpt", sa.Text(), nullable=True),
        sa.Column("current_excerpt", sa.Text(), nullable=True),
        # signal_type is the domain materiality (material/non_material/unavailable);
        # change_kind is a coarse human label for the kind of change observed.
        sa.Column("signal_type", sa.String(50), nullable=False),
        sa.Column("change_kind", sa.String(50), nullable=False, server_default="content_changed"),
        sa.Column("change_summary", sa.Text(), nullable=False),
        sa.Column("details", _JSON, nullable=True),
        # Lifecycle: 'pending' until a governed review decision flips it.
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        # Review outcome, all null until reviewed.
        sa.Column("review_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_by", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("review_action", sa.String(50), nullable=True),
        sa.Column("review_rationale", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["org_id", "project_id"],
            ["projects.org_id", "projects.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "idx_monitoring_source_deltas_item",
        "monitoring_source_deltas",
        ["org_id", "project_id", "item_id"],
    )
    # Pending-signal reads scan by scope filtered to status='pending'; this index
    # serves the "list pending deltas for a project" query directly.
    op.create_index(
        "idx_monitoring_source_deltas_pending",
        "monitoring_source_deltas",
        ["org_id", "project_id", "status", "detected_at"],
    )
    # The accountable review identity is unique once assigned; a null review_id
    # (still pending) does not participate in the uniqueness guard.
    op.create_index(
        "uq_monitoring_source_deltas_review_id",
        "monitoring_source_deltas",
        ["review_id"],
        unique=True,
        postgresql_where=sa.text("review_id IS NOT NULL"),
        sqlite_where=sa.text("review_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_monitoring_source_deltas_review_id",
        table_name="monitoring_source_deltas",
    )
    op.drop_index(
        "idx_monitoring_source_deltas_pending",
        table_name="monitoring_source_deltas",
    )
    op.drop_index(
        "idx_monitoring_source_deltas_item",
        table_name="monitoring_source_deltas",
    )
    op.drop_table("monitoring_source_deltas")

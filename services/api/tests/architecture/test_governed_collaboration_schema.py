"""Schema contract tests for the governed collaboration migration chain."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError

API_ROOT = Path(__file__).resolve().parents[2]

HEAD_REVISION = "0036_governance_surfaces"
PREVIOUS_REVISION = "0029_job_list_pagination"


def _config(database_path: Path) -> Config:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    return config


def _engine(database_path: Path) -> sa.Engine:
    engine = sa.create_engine(f"sqlite:///{database_path}")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def _migrate(database_path: Path, revision: str = "head") -> sa.Engine:
    command.upgrade(_config(database_path), revision)
    return _engine(database_path)


def _uniques(inspector: sa.Inspector, table: str) -> dict[str | None, tuple[str, ...]]:
    return {
        constraint["name"]: tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints(table)
    }


def _foreign_keys(
    inspector: sa.Inspector, table: str
) -> dict[str | None, tuple[tuple[str, ...], str, tuple[str | None, ...]]]:
    return {
        foreign_key["name"]: (
            tuple(foreign_key["constrained_columns"]),
            foreign_key["referred_table"],
            tuple(foreign_key["referred_columns"]),
        )
        for foreign_key in inspector.get_foreign_keys(table)
    }


def _indexes(inspector: sa.Inspector, table: str) -> dict[str | None, tuple[str | None, ...]]:
    return {index["name"]: tuple(index["column_names"]) for index in inspector.get_indexes(table)}


def test_head_is_canonical_schema(tmp_path: Path) -> None:
    engine = _migrate(tmp_path / "head.db")
    with engine.connect() as connection:
        revision = connection.execute(
            sa.text("SELECT version_num FROM alembic_version")
        ).scalar_one()
    assert revision == HEAD_REVISION
    engine.dispose()


def test_governed_collaboration_tables_exist(tmp_path: Path) -> None:
    engine = _migrate(tmp_path / "tables.db")
    table_names = set(sa.inspect(engine).get_table_names())
    assert {
        "governed_command_receipts",
        "governed_decision_records",
        "governed_referrals",
        "governed_comments",
        "governed_comment_revisions",
        "governed_comment_mentions",
        "governed_outbox",
    } <= table_names
    # No second audit table is introduced; authoritative_audit_events remains canonical.
    assert "governed_audit_events" not in table_names
    engine.dispose()


def test_clearance_items_version_is_monotonic_optimistic_lock(tmp_path: Path) -> None:
    engine = _migrate(tmp_path / "version.db")
    columns = {
        column["name"]: column for column in sa.inspect(engine).get_columns("clearance_items")
    }
    assert "version" in columns
    assert columns["version"]["nullable"] is False
    engine.dispose()


def test_clearance_items_version_backfills_existing_rows_safely(tmp_path: Path) -> None:
    database_path = tmp_path / "version-backfill.db"
    engine = _migrate(database_path, PREVIOUS_REVISION)
    now = datetime.now(UTC)
    org_id, project_id, script_id, version_id, element_id, item_id = (
        str(uuid4()) for _ in range(6)
    )
    with engine.begin() as connection:
        _seed_item(
            connection,
            org_id=org_id,
            project_id=project_id,
            script_id=script_id,
            version_id=version_id,
            element_id=element_id,
            item_id=item_id,
            now=now,
        )
    engine.dispose()

    command.upgrade(_config(database_path), "head")
    engine = _engine(database_path)
    with engine.connect() as connection:
        version = connection.execute(
            sa.text("SELECT version FROM clearance_items WHERE id = :id"),
            {"id": item_id},
        ).scalar_one()
    assert version == 1
    engine.dispose()


def test_command_receipts_scoped_uniqueness_and_columns(tmp_path: Path) -> None:
    engine = _migrate(tmp_path / "receipts.db")
    inspector = sa.inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("governed_command_receipts")}
    assert {
        "id",
        "org_id",
        "project_id",
        "item_id",
        "actor_id",
        "operation",
        "idempotency_key",
        "expected_version",
        "resulting_version",
        "intent_hash",
        "result_id",
        "occurred_at",
    } <= columns
    uniques = _uniques(inspector, "governed_command_receipts")
    assert (
        "org_id",
        "project_id",
        "actor_id",
        "operation",
        "idempotency_key",
    ) in uniques.values()
    engine.dispose()


def test_decision_records_versioned_and_owned(tmp_path: Path) -> None:
    engine = _migrate(tmp_path / "decisions.db")
    inspector = sa.inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("governed_decision_records")}
    assert {
        "id",
        "org_id",
        "project_id",
        "item_id",
        "actor_id",
        "decision_kind",
        "decision_value",
        "rationale",
        "expected_version",
        "resulting_version",
        "created_at",
    } <= columns
    engine.dispose()


def test_referrals_lifecycle_columns(tmp_path: Path) -> None:
    engine = _migrate(tmp_path / "referrals.db")
    columns = {column["name"] for column in sa.inspect(engine).get_columns("governed_referrals")}
    assert {
        "id",
        "org_id",
        "project_id",
        "item_id",
        "target_role",
        "question",
        "notes",
        "submitted_by_actor_id",
        "acknowledged_by_actor_id",
        "status",
        "submitted_at",
        "acknowledged_at",
        "idempotency_key",
    } <= columns
    engine.dispose()


def test_comments_and_immutable_revisions(tmp_path: Path) -> None:
    engine = _migrate(tmp_path / "comments.db")
    inspector = sa.inspect(engine)
    comment_columns = {column["name"] for column in inspector.get_columns("governed_comments")}
    assert {
        "id",
        "org_id",
        "project_id",
        "item_id",
        "author_id",
        "parent_comment_id",
        "created_at",
    } <= comment_columns
    revision_columns = {
        column["name"] for column in inspector.get_columns("governed_comment_revisions")
    }
    assert {
        "id",
        "org_id",
        "project_id",
        "comment_id",
        "ordinal",
        "body",
        "created_at",
    } <= revision_columns
    engine.dispose()


def test_mentions_reference_user_ids(tmp_path: Path) -> None:
    engine = _migrate(tmp_path / "mentions.db")
    inspector = sa.inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("governed_comment_mentions")}
    assert {
        "id",
        "org_id",
        "project_id",
        "comment_id",
        "recipient_user_id",
    } <= columns
    foreign_keys = _foreign_keys(inspector, "governed_comment_mentions")
    assert any(
        constrained == ("recipient_user_id",) and referred_table == "users"
        for constrained, referred_table, _referred in foreign_keys.values()
    )
    engine.dispose()


def test_outbox_dedupe_and_schema_version(tmp_path: Path) -> None:
    engine = _migrate(tmp_path / "outbox.db")
    inspector = sa.inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("governed_outbox")}
    assert {
        "id",
        "org_id",
        "project_id",
        "event_type",
        "schema_version",
        "dedupe_key",
        "payload",
        "created_at",
        "processed_at",
    } <= columns
    uniques = _uniques(inspector, "governed_outbox")
    assert ("org_id", "project_id", "dedupe_key") in uniques.values()
    indexes = _indexes(inspector, "governed_outbox")
    assert ("org_id", "project_id", "processed_at", "created_at") in indexes.values()
    engine.dispose()


def test_item_history_index_exists(tmp_path: Path) -> None:
    engine = _migrate(tmp_path / "history-index.db")
    indexes = _indexes(sa.inspect(engine), "governed_decision_records")
    assert ("org_id", "project_id", "item_id", "created_at") in indexes.values()
    engine.dispose()


@pytest.mark.parametrize(
    "table",
    [
        "governed_command_receipts",
        "governed_decision_records",
        "governed_referrals",
        "governed_comments",
        "governed_comment_revisions",
        "governed_comment_mentions",
        "governed_outbox",
    ],
)
def test_project_ownership_foreign_key_present(tmp_path: Path, table: str) -> None:
    engine = _migrate(tmp_path / f"ownership-{table}.db")
    foreign_keys = _foreign_keys(sa.inspect(engine), table)
    assert any(
        constrained == ("org_id", "project_id")
        and referred_table == "projects"
        and referred == ("org_id", "id")
        for constrained, referred_table, referred in foreign_keys.values()
    ), f"{table} must own rows by (org_id, project_id) -> projects(org_id, id)"
    engine.dispose()


def test_item_scoped_rows_cannot_cross_project(tmp_path: Path) -> None:
    database_path = tmp_path / "cross-project.db"
    engine = _migrate(database_path)
    now = datetime.now(UTC)
    (
        org_a,
        org_b,
        project_a,
        project_b,
        script_a,
        script_b,
        version_a,
        version_b,
        element_a,
        element_b,
        item_a,
        actor_a,
    ) = (str(uuid4()) for _ in range(12))

    with engine.begin() as connection:
        connection.execute(
            sa.text("INSERT INTO users (id, email, created_at) VALUES (:id, :email, :created)"),
            {"id": actor_a, "email": "governed@example.com", "created": now},
        )
        for org_id, slug in ((org_a, "gov-a"), (org_b, "gov-b")):
            connection.execute(
                sa.text(
                    "INSERT INTO organizations (id, name, slug, created_at) "
                    "VALUES (:id, :name, :slug, :created)"
                ),
                {"id": org_id, "name": slug, "slug": slug, "created": now},
            )
        for project_id, org_id in ((project_a, org_a), (project_b, org_b)):
            connection.execute(
                sa.text(
                    "INSERT INTO projects (id, org_id, title, created_at) "
                    "VALUES (:id, :org, 'Governed', :created)"
                ),
                {"id": project_id, "org": org_id, "created": now},
            )
        _seed_item(
            connection,
            org_id=org_a,
            project_id=project_a,
            script_id=script_a,
            version_id=version_a,
            element_id=element_a,
            item_id=item_a,
            now=now,
            create_project=False,
        )
        # Second project exists but has no item; used to attempt a cross-project write.
        connection.execute(
            sa.text(
                "INSERT INTO scripts (id, org_id, project_id, title, created_at) "
                "VALUES (:id, :org, :project, 'B', :created)"
            ),
            {"id": script_b, "org": org_b, "project": project_b, "created": now},
        )

    # A decision record claiming item_a but scoped to project_b/org_b must be rejected,
    # because the composite ownership FK requires the item to belong to (org_b, project_b).
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO governed_decision_records "
                "(id, org_id, project_id, item_id, actor_id, decision_kind, decision_value, "
                "rationale, expected_version, resulting_version, created_at) VALUES "
                "(:id, :org, :project, :item, :actor, 'evidence', 'accepted', 'x', 1, 2, :created)"
            ),
            {
                "id": str(uuid4()),
                "org": org_b,
                "project": project_b,
                "item": item_a,
                "actor": actor_a,
                "created": now,
            },
        )
    engine.dispose()
    # element_b/version_b/script_b unused placeholders retained for symmetry.
    del element_b, version_b


def _seed_comment(
    connection: sa.Connection,
    *,
    org_id: str,
    project_id: str,
    item_id: str,
    author_id: str,
    comment_id: str,
    parent_comment_id: str | None,
    reply_depth: int,
    now: datetime,
    parent_reply_depth: int | None = None,
) -> None:
    connection.execute(
        sa.text(
            "INSERT INTO governed_comments "
            "(id, org_id, project_id, item_id, author_id, parent_comment_id, "
            "parent_reply_depth, reply_depth, created_at) VALUES "
            "(:id, :org, :project, :item, :author, :parent, :parent_depth, :depth, :created)"
        ),
        {
            "id": comment_id,
            "org": org_id,
            "project": project_id,
            "item": item_id,
            "author": author_id,
            "parent": parent_comment_id,
            "parent_depth": parent_reply_depth,
            "depth": reply_depth,
            "created": now,
        },
    )


def _seed_org_project_item_author(
    connection: sa.Connection, now: datetime
) -> tuple[str, str, str, str]:
    org_id, project_id, script_id, version_id, element_id, item_id, author_id = (
        str(uuid4()) for _ in range(7)
    )
    connection.execute(
        sa.text("INSERT INTO users (id, email, created_at) VALUES (:id, :email, :created)"),
        {"id": author_id, "email": f"author-{author_id[:8]}@example.com", "created": now},
    )
    _seed_item(
        connection,
        org_id=org_id,
        project_id=project_id,
        script_id=script_id,
        version_id=version_id,
        element_id=element_id,
        item_id=item_id,
        now=now,
    )
    return org_id, project_id, item_id, author_id


def test_populated_0030_upgrades_through_0032_and_downgrades(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "comment-migration-backfills.db"
    engine = _migrate(database_path, "0030_governed_collaboration")
    now = datetime.now(UTC)
    first_revision_id = str(uuid4())
    latest_revision_id = str(uuid4())
    mention_id = str(uuid4())
    recipient_id = str(uuid4())
    with engine.begin() as connection:
        org_id, project_id, item_id, author_id = _seed_org_project_item_author(
            connection,
            now,
        )
        connection.execute(
            sa.text("INSERT INTO users (id, email, created_at) VALUES (:id, :email, :created)"),
            {
                "id": recipient_id,
                "email": f"recipient-{recipient_id[:8]}@example.com",
                "created": now,
            },
        )
        comment_id = str(uuid4())
        _seed_comment(
            connection,
            org_id=org_id,
            project_id=project_id,
            item_id=item_id,
            author_id=author_id,
            comment_id=comment_id,
            parent_comment_id=None,
            parent_reply_depth=None,
            reply_depth=0,
            now=now,
        )
        for revision_id, ordinal, body in (
            (first_revision_id, 1, "first pre-0031 body"),
            (latest_revision_id, 2, "latest pre-0031 body"),
        ):
            connection.execute(
                sa.text(
                    "INSERT INTO governed_comment_revisions "
                    "(id, org_id, project_id, comment_id, ordinal, body, created_at) VALUES "
                    "(:id, :org, :project, :comment, :ordinal, :body, :created)"
                ),
                {
                    "id": revision_id,
                    "org": org_id,
                    "project": project_id,
                    "comment": comment_id,
                    "ordinal": ordinal,
                    "body": body,
                    "created": now,
                },
            )
        connection.execute(
            sa.text(
                "INSERT INTO governed_comment_mentions "
                "(id, org_id, project_id, comment_id, recipient_user_id, created_at) VALUES "
                "(:id, :org, :project, :comment, :recipient, :created)"
            ),
            {
                "id": mention_id,
                "org": org_id,
                "project": project_id,
                "comment": comment_id,
                "recipient": recipient_id,
                "created": now,
            },
        )
    engine.dispose()

    command.upgrade(_config(database_path), "0031_comment_revision_author")
    engine = _engine(database_path)
    inspector = sa.inspect(engine)
    columns = {
        column["name"]: column for column in inspector.get_columns("governed_comment_revisions")
    }
    assert columns["author_id"]["nullable"] is False
    foreign_keys = _foreign_keys(inspector, "governed_comment_revisions")
    assert foreign_keys["fk_governed_comment_revisions_author"] == (
        ("author_id",),
        "users",
        ("id",),
    )
    with engine.connect() as connection:
        rows = connection.execute(
            sa.text(
                "SELECT author_id, body FROM governed_comment_revisions "
                "WHERE comment_id = :comment ORDER BY ordinal"
            ),
            {"comment": comment_id},
        ).all()
    assert [(str(row.author_id), row.body) for row in rows] == [
        (author_id, "first pre-0031 body"),
        (author_id, "latest pre-0031 body"),
    ]
    engine.dispose()

    command.upgrade(_config(database_path), "0032_comment_mention_revision")
    engine = _engine(database_path)
    inspector = sa.inspect(engine)
    mention_columns = {
        column["name"]: column for column in inspector.get_columns("governed_comment_mentions")
    }
    assert mention_columns["revision_id"]["nullable"] is False
    mention_uniques = _uniques(inspector, "governed_comment_mentions")
    assert mention_uniques["uq_governed_comment_mentions_revision_recipient"] == (
        "org_id",
        "project_id",
        "comment_id",
        "revision_id",
        "recipient_user_id",
    )
    mention_foreign_keys = _foreign_keys(inspector, "governed_comment_mentions")
    assert mention_foreign_keys["fk_governed_comment_mentions_revision"] == (
        ("revision_id",),
        "governed_comment_revisions",
        ("id",),
    )
    with engine.connect() as connection:
        revision_id = connection.execute(
            sa.text("SELECT revision_id FROM governed_comment_mentions WHERE id = :id"),
            {"id": mention_id},
        ).scalar_one()
    assert str(revision_id) == latest_revision_id
    engine.dispose()

    command.downgrade(_config(database_path), "0030_governed_collaboration")
    engine = _engine(database_path)
    inspector = sa.inspect(engine)
    downgraded_revision_columns = {
        column["name"] for column in inspector.get_columns("governed_comment_revisions")
    }
    downgraded_mention_columns = {
        column["name"] for column in inspector.get_columns("governed_comment_mentions")
    }
    assert "author_id" not in downgraded_revision_columns
    assert "revision_id" not in downgraded_mention_columns
    with engine.connect() as connection:
        bodies = (
            connection.execute(
                sa.text(
                    "SELECT body FROM governed_comment_revisions "
                    "WHERE comment_id = :comment ORDER BY ordinal"
                ),
                {"comment": comment_id},
            )
            .scalars()
            .all()
        )
        mention_count = connection.execute(
            sa.text("SELECT count(*) FROM governed_comment_mentions WHERE id = :id"),
            {"id": mention_id},
        ).scalar_one()
    assert bodies == ["first pre-0031 body", "latest pre-0031 body"]
    assert mention_count == 1
    engine.dispose()


def test_grandchild_reply_is_rejected_at_database(tmp_path: Path) -> None:
    """A reply to a reply (depth 2) must fail with IntegrityError at the DB level."""
    database_path = tmp_path / "grandchild.db"
    engine = _migrate(database_path)
    now = datetime.now(UTC)
    with engine.begin() as connection:
        org_id, project_id, item_id, author_id = _seed_org_project_item_author(connection, now)
        root_id, reply_id = str(uuid4()), str(uuid4())
        _seed_comment(
            connection,
            org_id=org_id,
            project_id=project_id,
            item_id=item_id,
            author_id=author_id,
            comment_id=root_id,
            parent_comment_id=None,
            parent_reply_depth=None,
            reply_depth=0,
            now=now,
        )
        _seed_comment(
            connection,
            org_id=org_id,
            project_id=project_id,
            item_id=item_id,
            author_id=author_id,
            comment_id=reply_id,
            parent_comment_id=root_id,
            parent_reply_depth=0,
            reply_depth=1,
            now=now,
        )

    grandchild_id = str(uuid4())
    # Attempt to reply to a reply. The only value of parent_reply_depth that satisfies
    # the CHECK (=0) contradicts the composite FK, which requires the referenced parent
    # (reply_id) to have reply_depth = 0 when in fact it is 1. Both branches must fail.
    with pytest.raises(IntegrityError), engine.begin() as connection:
        _seed_comment(
            connection,
            org_id=org_id,
            project_id=project_id,
            item_id=item_id,
            author_id=author_id,
            comment_id=grandchild_id,
            parent_comment_id=reply_id,
            parent_reply_depth=0,
            reply_depth=1,
            now=now,
        )
    engine.dispose()


def test_reply_to_root_is_accepted(tmp_path: Path) -> None:
    """A single-level reply (depth 1) to a root (depth 0) must be accepted."""
    database_path = tmp_path / "reply-root.db"
    engine = _migrate(database_path)
    now = datetime.now(UTC)
    with engine.begin() as connection:
        org_id, project_id, item_id, author_id = _seed_org_project_item_author(connection, now)
        root_id, reply_id = str(uuid4()), str(uuid4())
        _seed_comment(
            connection,
            org_id=org_id,
            project_id=project_id,
            item_id=item_id,
            author_id=author_id,
            comment_id=root_id,
            parent_comment_id=None,
            parent_reply_depth=None,
            reply_depth=0,
            now=now,
        )
        _seed_comment(
            connection,
            org_id=org_id,
            project_id=project_id,
            item_id=item_id,
            author_id=author_id,
            comment_id=reply_id,
            parent_comment_id=root_id,
            parent_reply_depth=0,
            reply_depth=1,
            now=now,
        )
    with engine.connect() as connection:
        count = connection.execute(
            sa.text("SELECT count(*) FROM governed_comments WHERE item_id = :item"),
            {"item": item_id},
        ).scalar_one()
    assert count == 2
    engine.dispose()


def test_comment_revision_ordinal_is_unique_per_comment(tmp_path: Path) -> None:
    """Duplicate (org, project, comment_id, ordinal) revisions must be rejected."""
    database_path = tmp_path / "revision-unique.db"
    engine = _migrate(database_path)
    now = datetime.now(UTC)
    with engine.begin() as connection:
        org_id, project_id, item_id, author_id = _seed_org_project_item_author(connection, now)
        comment_id = str(uuid4())
        _seed_comment(
            connection,
            org_id=org_id,
            project_id=project_id,
            item_id=item_id,
            author_id=author_id,
            comment_id=comment_id,
            parent_comment_id=None,
            parent_reply_depth=None,
            reply_depth=0,
            now=now,
        )
        connection.execute(
            sa.text(
                "INSERT INTO governed_comment_revisions "
                "(id, org_id, project_id, comment_id, author_id, ordinal, body, created_at) VALUES "
                "(:id, :org, :project, :comment, :author, 1, 'first', :created)"
            ),
            {
                "id": str(uuid4()),
                "org": org_id,
                "project": project_id,
                "comment": comment_id,
                "author": author_id,
                "created": now,
            },
        )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO governed_comment_revisions "
                "(id, org_id, project_id, comment_id, author_id, ordinal, body, created_at) VALUES "
                "(:id, :org, :project, :comment, :author, 1, 'duplicate', :created)"
            ),
            {
                "id": str(uuid4()),
                "org": org_id,
                "project": project_id,
                "comment": comment_id,
                "author": author_id,
                "created": now,
            },
        )
    engine.dispose()


def test_comment_revision_ordinal_zero_is_rejected(tmp_path: Path) -> None:
    """ordinal=0 must be rejected by ck_governed_comment_revisions_ordinal_positive."""
    database_path = tmp_path / "revision-ordinal-zero.db"
    engine = _migrate(database_path)
    now = datetime.now(UTC)
    with engine.begin() as connection:
        org_id, project_id, item_id, author_id = _seed_org_project_item_author(connection, now)
        comment_id = str(uuid4())
        _seed_comment(
            connection,
            org_id=org_id,
            project_id=project_id,
            item_id=item_id,
            author_id=author_id,
            comment_id=comment_id,
            parent_comment_id=None,
            parent_reply_depth=None,
            reply_depth=0,
            now=now,
        )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO governed_comment_revisions "
                "(id, org_id, project_id, comment_id, author_id, ordinal, body, created_at) VALUES "
                "(:id, :org, :project, :comment, :author, 0, 'zero', :created)"
            ),
            {
                "id": str(uuid4()),
                "org": org_id,
                "project": project_id,
                "comment": comment_id,
                "author": author_id,
                "created": now,
            },
        )
    engine.dispose()


def test_clearance_items_version_zero_is_rejected(tmp_path: Path) -> None:
    """version=0 must fail ck_clearance_items_version_positive."""
    database_path = tmp_path / "version-zero.db"
    engine = _migrate(database_path, PREVIOUS_REVISION)
    now = datetime.now(UTC)
    org_id, project_id, script_id, version_id, element_id, item_id = (
        str(uuid4()) for _ in range(6)
    )
    with engine.begin() as connection:
        _seed_item(
            connection,
            org_id=org_id,
            project_id=project_id,
            script_id=script_id,
            version_id=version_id,
            element_id=element_id,
            item_id=item_id,
            now=now,
        )
    engine.dispose()
    command.upgrade(_config(database_path), "head")
    engine = _engine(database_path)
    new_item_id = str(uuid4())
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO clearance_items "
                "(id, org_id, project_id, script_id, version_id, element_id, category, text, "
                "status, version, created_at) VALUES "
                "(:id, :org, :project, :script, :version, :element, 'brands', 'Brand', "
                "'unresolved', 0, :created)"
            ),
            {
                "id": new_item_id,
                "org": org_id,
                "project": project_id,
                "script": script_id,
                "version": version_id,
                "element": element_id,
                "created": now,
            },
        )
    engine.dispose()


def test_named_constraints_are_present(tmp_path: Path) -> None:
    """Assert named constraints (not mere membership) to catch renames/over-broad scope."""
    engine = _migrate(tmp_path / "named-constraints.db")
    inspector = sa.inspect(engine)

    receipt_uniques = _uniques(inspector, "governed_command_receipts")
    assert receipt_uniques.get("uq_governed_command_receipts_idempotency") == (
        "org_id",
        "project_id",
        "actor_id",
        "operation",
        "idempotency_key",
    )

    revision_uniques = _uniques(inspector, "governed_comment_revisions")
    assert revision_uniques.get("uq_governed_comment_revisions_sequence") == (
        "org_id",
        "project_id",
        "comment_id",
        "ordinal",
    )

    comment_uniques = _uniques(inspector, "governed_comments")
    assert comment_uniques.get("uq_governed_comments_scope") == ("id", "org_id", "project_id")

    outbox_uniques = _uniques(inspector, "governed_outbox")
    assert outbox_uniques.get("uq_governed_outbox_dedupe") == (
        "org_id",
        "project_id",
        "dedupe_key",
    )

    referral_uniques = _uniques(inspector, "governed_referrals")
    assert referral_uniques.get("uq_governed_referrals_idempotency") == (
        "org_id",
        "project_id",
        "idempotency_key",
    )

    check_constraints = {
        constraint["name"]
        for constraint in inspector.get_check_constraints("governed_comment_revisions")
    }
    assert "ck_governed_comment_revisions_ordinal_positive" in check_constraints

    comment_checks = {
        constraint["name"] for constraint in inspector.get_check_constraints("governed_comments")
    }
    assert "ck_governed_comments_single_reply_level" in comment_checks
    assert "ck_governed_comments_parent_is_root" in comment_checks

    item_checks = {
        constraint["name"] for constraint in inspector.get_check_constraints("clearance_items")
    }
    assert "ck_clearance_items_version_positive" in item_checks
    engine.dispose()


def test_referral_idempotency_scope_is_documented_asymmetry(tmp_path: Path) -> None:
    """Referral idempotency is (org, project, key); receipts add (actor, operation).

    This asymmetry is intentional: a referral idempotency key is unique per project,
    while a command receipt key is unique per (actor, operation) within a project.
    Assert both scopes explicitly so a future accidental convergence is caught.
    """
    engine = _migrate(tmp_path / "idempotency-scope.db")
    inspector = sa.inspect(engine)
    referral_uniques = _uniques(inspector, "governed_referrals")
    receipt_uniques = _uniques(inspector, "governed_command_receipts")
    assert referral_uniques.get("uq_governed_referrals_idempotency") == (
        "org_id",
        "project_id",
        "idempotency_key",
    )
    assert receipt_uniques.get("uq_governed_command_receipts_idempotency") == (
        "org_id",
        "project_id",
        "actor_id",
        "operation",
        "idempotency_key",
    )
    # The referral scope is deliberately narrower (no actor/operation dimensions).
    assert "actor_id" not in referral_uniques.get("uq_governed_referrals_idempotency", ())
    engine.dispose()


def test_downgrade_and_round_trip_to_previous_and_back(tmp_path: Path) -> None:
    database_path = tmp_path / "round-trip.db"
    engine = _migrate(database_path, PREVIOUS_REVISION)
    now = datetime.now(UTC)
    org_id, project_id, script_id, version_id, element_id, item_id = (
        str(uuid4()) for _ in range(6)
    )
    with engine.begin() as connection:
        _seed_item(
            connection,
            org_id=org_id,
            project_id=project_id,
            script_id=script_id,
            version_id=version_id,
            element_id=element_id,
            item_id=item_id,
            now=now,
        )
    engine.dispose()

    # Upgrade to head, then downgrade to 0029, then re-upgrade to head.
    command.upgrade(_config(database_path), "head")
    engine = _engine(database_path)
    assert "version" in {
        column["name"] for column in sa.inspect(engine).get_columns("clearance_items")
    }
    engine.dispose()

    command.downgrade(_config(database_path), PREVIOUS_REVISION)
    engine = _engine(database_path)
    inspector = sa.inspect(engine)
    table_names = set(inspector.get_table_names())
    assert "governed_command_receipts" not in table_names
    assert "governed_decision_records" not in table_names
    assert "governed_referrals" not in table_names
    assert "governed_comments" not in table_names
    assert "governed_comment_revisions" not in table_names
    assert "governed_comment_mentions" not in table_names
    assert "governed_outbox" not in table_names
    assert "version" not in {column["name"] for column in inspector.get_columns("clearance_items")}
    with engine.connect() as connection:
        # No data fabrication: the pre-existing item survives the round trip unchanged.
        assert (
            connection.execute(
                sa.text("SELECT count(*) FROM clearance_items WHERE id = :id"),
                {"id": item_id},
            ).scalar_one()
            == 1
        )
    engine.dispose()

    command.upgrade(_config(database_path), "head")
    engine = _engine(database_path)
    inspector = sa.inspect(engine)
    assert "version" in {column["name"] for column in inspector.get_columns("clearance_items")}
    assert {
        "governed_command_receipts",
        "governed_decision_records",
        "governed_referrals",
        "governed_comments",
        "governed_comment_revisions",
        "governed_comment_mentions",
        "governed_outbox",
    } <= set(inspector.get_table_names())
    with engine.connect() as connection:
        assert (
            connection.execute(
                sa.text("SELECT count(*) FROM clearance_items WHERE id = :id"),
                {"id": item_id},
            ).scalar_one()
            == 1
        )
    engine.dispose()


def _seed_item(
    connection: sa.Connection,
    *,
    org_id: str,
    project_id: str,
    script_id: str,
    version_id: str,
    element_id: str,
    item_id: str,
    now: datetime,
    create_project: bool = True,
) -> None:
    if create_project:
        connection.execute(
            sa.text(
                "INSERT INTO organizations (id, name, slug, created_at) "
                "VALUES (:id, 'Org', :slug, :created)"
            ),
            {"id": org_id, "slug": f"org-{org_id[:8]}", "created": now},
        )
        connection.execute(
            sa.text(
                "INSERT INTO projects (id, org_id, title, created_at) "
                "VALUES (:id, :org, 'Project', :created)"
            ),
            {"id": project_id, "org": org_id, "created": now},
        )
    connection.execute(
        sa.text(
            "INSERT INTO scripts (id, org_id, project_id, title, created_at) "
            "VALUES (:id, :org, :project, 'Script', :created)"
        ),
        {"id": script_id, "org": org_id, "project": project_id, "created": now},
    )
    connection.execute(
        sa.text(
            "INSERT INTO script_versions "
            "(id, script_id, org_id, project_id, ordinal, source_hash, parser_version, "
            "created_at) VALUES (:id, :script, :org, :project, 1, :hash, '1', :created)"
        ),
        {
            "id": version_id,
            "script": script_id,
            "org": org_id,
            "project": project_id,
            "hash": f"hash-{version_id[:8]}",
            "created": now,
        },
    )
    connection.execute(
        sa.text(
            "INSERT INTO script_elements (id, version_id, ordinal, element_type, text) "
            "VALUES (:id, :version, 1, 'action', 'Body')"
        ),
        {"id": element_id, "version": version_id},
    )
    connection.execute(
        sa.text(
            "INSERT INTO clearance_items "
            "(id, org_id, project_id, script_id, version_id, element_id, category, text, "
            "status, created_at) VALUES "
            "(:id, :org, :project, :script, :version, :element, 'brands', 'Brand', "
            "'unresolved', :created)"
        ),
        {
            "id": item_id,
            "org": org_id,
            "project": project_id,
            "script": script_id,
            "version": version_id,
            "element": element_id,
            "created": now,
        },
    )


def test_0032_downgrade_deduplicates_repeated_recipient_by_latest_revision(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "mention-downgrade-dedup.db"
    engine = _migrate(database_path, "0032_comment_mention_revision")
    now = datetime.now(UTC)
    recipient_id = str(uuid4())
    first_revision_id = str(uuid4())
    latest_revision_id = str(uuid4())
    first_mention_id = str(uuid4())
    latest_mention_id = str(uuid4())
    with engine.begin() as connection:
        org_id, project_id, item_id, author_id = _seed_org_project_item_author(
            connection,
            now,
        )
        connection.execute(
            sa.text("INSERT INTO users (id, email, created_at) VALUES (:id, :email, :created)"),
            {
                "id": recipient_id,
                "email": f"recipient-{recipient_id[:8]}@example.com",
                "created": now,
            },
        )
        comment_id = str(uuid4())
        _seed_comment(
            connection,
            org_id=org_id,
            project_id=project_id,
            item_id=item_id,
            author_id=author_id,
            comment_id=comment_id,
            parent_comment_id=None,
            parent_reply_depth=None,
            reply_depth=0,
            now=now,
        )
        for revision_id, ordinal in (
            (first_revision_id, 1),
            (latest_revision_id, 2),
        ):
            connection.execute(
                sa.text(
                    "INSERT INTO governed_comment_revisions "
                    "(id, org_id, project_id, comment_id, author_id, ordinal, body, created_at) "
                    "VALUES (:id, :org, :project, :comment, :author, :ordinal, :body, :created)"
                ),
                {
                    "id": revision_id,
                    "org": org_id,
                    "project": project_id,
                    "comment": comment_id,
                    "author": author_id,
                    "ordinal": ordinal,
                    "body": f"revision {ordinal}",
                    "created": now,
                },
            )
        for mention_id, revision_id in (
            (first_mention_id, first_revision_id),
            (latest_mention_id, latest_revision_id),
        ):
            connection.execute(
                sa.text(
                    "INSERT INTO governed_comment_mentions "
                    "(id, org_id, project_id, comment_id, revision_id, "
                    "recipient_user_id, created_at) VALUES "
                    "(:id, :org, :project, :comment, :revision, :recipient, :created)"
                ),
                {
                    "id": mention_id,
                    "org": org_id,
                    "project": project_id,
                    "comment": comment_id,
                    "revision": revision_id,
                    "recipient": recipient_id,
                    "created": now,
                },
            )
    engine.dispose()

    command.downgrade(_config(database_path), "0031_comment_revision_author")
    engine = _engine(database_path)
    with engine.connect() as connection:
        remaining_ids = (
            connection.execute(
                sa.text(
                    "SELECT id FROM governed_comment_mentions "
                    "WHERE comment_id = :comment AND recipient_user_id = :recipient"
                ),
                {"comment": comment_id, "recipient": recipient_id},
            )
            .scalars()
            .all()
        )
    assert [str(mention_id) for mention_id in remaining_ids] == [latest_mention_id]
    assert "revision_id" not in {
        column["name"] for column in sa.inspect(engine).get_columns("governed_comment_mentions")
    }
    engine.dispose()


def test_revision_mention_rejects_cross_comment_revision_scope(tmp_path: Path) -> None:
    database_path = tmp_path / "mention-revision-scope.db"
    engine = _migrate(database_path)
    now = datetime.now(UTC)
    recipient_id = str(uuid4())
    with engine.begin() as connection:
        org_id, project_id, item_id, author_id = _seed_org_project_item_author(
            connection,
            now,
        )
        connection.execute(
            sa.text("INSERT INTO users (id, email, created_at) VALUES (:id, :email, :created)"),
            {
                "id": recipient_id,
                "email": f"recipient-{recipient_id[:8]}@example.com",
                "created": now,
            },
        )
        first_comment_id = str(uuid4())
        second_comment_id = str(uuid4())
        for comment_id in (first_comment_id, second_comment_id):
            _seed_comment(
                connection,
                org_id=org_id,
                project_id=project_id,
                item_id=item_id,
                author_id=author_id,
                comment_id=comment_id,
                parent_comment_id=None,
                parent_reply_depth=None,
                reply_depth=0,
                now=now,
            )
        first_revision_id = str(uuid4())
        connection.execute(
            sa.text(
                "INSERT INTO governed_comment_revisions "
                "(id, org_id, project_id, comment_id, author_id, ordinal, body, created_at) "
                "VALUES (:id, :org, :project, :comment, :author, 1, 'first', :created)"
            ),
            {
                "id": first_revision_id,
                "org": org_id,
                "project": project_id,
                "comment": first_comment_id,
                "author": author_id,
                "created": now,
            },
        )

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO governed_comment_mentions "
                "(id, org_id, project_id, comment_id, revision_id, "
                "recipient_user_id, created_at) VALUES "
                "(:id, :org, :project, :comment, :revision, :recipient, :created)"
            ),
            {
                "id": str(uuid4()),
                "org": org_id,
                "project": project_id,
                "comment": second_comment_id,
                "revision": first_revision_id,
                "recipient": recipient_id,
                "created": now,
            },
        )

    revision_foreign_key = _foreign_keys(
        sa.inspect(engine),
        "governed_comment_mentions",
    )["fk_governed_comment_mentions_revision"]
    assert revision_foreign_key == (
        ("revision_id", "org_id", "project_id", "comment_id"),
        "governed_comment_revisions",
        ("id", "org_id", "project_id", "comment_id"),
    )
    engine.dispose()

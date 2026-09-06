"""Schema contract tests for databases managed by the Alembic chain."""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from clearcut.init_db import UnversionedLegacySchemaError, _validate_database_bootstrap
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError

API_ROOT = Path(__file__).resolve().parents[2]


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


def test_empty_database_migrates_to_canonical_runtime_schema(tmp_path: Path) -> None:
    engine = _migrate(tmp_path / "runtime-schema.db")
    inspector = sa.inspect(engine)

    with engine.connect() as connection:
        revision = connection.execute(
            sa.text("SELECT version_num FROM alembic_version")
        ).scalar_one()
    assert revision == "0034_report_artifacts"

    project_columns = {column["name"]: column for column in inspector.get_columns("projects")}
    for column_name in (
        "production_type",
        "production_stage",
        "jurisdiction",
        "target_lock_date",
        "review_brief",
    ):
        assert column_name in project_columns
        assert project_columns[column_name]["nullable"] is True

    job_columns = {column["name"]: column for column in inspector.get_columns("jobs")}
    assert set(job_columns) == {
        "id",
        "org_id",
        "project_id",
        "job_type",
        "status",
        "idempotency_key",
        "payload",
        "result",
        "error",
        "progress",
        "stage",
        "actor_id",
        "correlation_id",
        "attempt_count",
        "available_at",
        "created_at",
        "updated_at",
        "lease_owner",
        "lease_expires_at",
    }
    assert job_columns["payload"]["nullable"] is False
    assert job_columns["result"]["nullable"] is True
    assert job_columns["actor_id"]["nullable"] is True
    assert job_columns["correlation_id"]["nullable"] is False
    assert job_columns["updated_at"]["nullable"] is False

    unique_constraints = {
        constraint["name"]: tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("jobs")
    }
    assert unique_constraints["uq_jobs_idempotency"] == (
        "org_id",
        "project_id",
        "idempotency_key",
    )
    indexes = {
        index["name"]: tuple(index["column_names"]) for index in inspector.get_indexes("jobs")
    }
    assert indexes["idx_jobs_lease"] == (
        "status",
        "available_at",
        "lease_expires_at",
        "id",
    )
    assert indexes["idx_jobs_project_created"] == (
        "org_id",
        "project_id",
        "created_at",
        "id",
    )

    assert {
        "research_runs",
        "research_queries",
        "provider_attempts",
        "search_result_authorizations",
        "extract_target_authorizations",
        "source_snapshots",
        "evidence_claims",
        "deterministic_gate_results",
        "agent_evaluations",
        "judge_verdicts",
        "ai_judge_invocations",
        "ai_provider_attempts",
        "detection_invocations",
        "detection_candidates",
        "authoritative_audit_events",
        "decision_receipts",
        "report_snapshots",
        "report_releases",
        "export_artifacts",
    } <= set(inspector.get_table_names())

    artifact_columns = {
        column["name"]: column for column in inspector.get_columns("export_artifacts")
    }
    assert set(artifact_columns) == {
        "id",
        "snapshot_id",
        "org_id",
        "project_id",
        "media_type",
        "content_hash",
        "content",
        "status",
        "created_at",
    }
    assert artifact_columns["content"]["nullable"] is False
    artifact_uniques = {
        constraint["name"]: tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("export_artifacts")
    }
    assert artifact_uniques["uq_export_artifacts_snapshot_media_type"] == (
        "snapshot_id",
        "media_type",
    )
    release_uniques = {
        constraint["name"]: tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("report_releases")
    }
    assert release_uniques["uq_report_releases_snapshot"] == ("snapshot_id",)

    research_run_columns = {column["name"] for column in inspector.get_columns("research_runs")}
    assert {
        "job_id",
        "version_id",
        "job_attempt_number",
        "lease_owner",
        "correlation_id",
        "objective",
        "input_sha256",
        "safe_error",
        "completed_at",
    } <= research_run_columns
    research_run_uniques = {
        constraint["name"]: tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("research_runs")
    }
    assert research_run_uniques["uq_research_runs_job_attempt"] == (
        "job_id",
        "job_attempt_number",
    )
    research_query_columns = {
        column["name"] for column in inspector.get_columns("research_queries")
    }
    assert {"org_id", "project_id", "item_id", "version_id", "created_at"} <= (
        research_query_columns
    )
    provider_attempt_columns = {
        column["name"] for column in inspector.get_columns("provider_attempts")
    }
    assert {
        "item_id",
        "query_id",
        "job_attempt_number",
        "lease_owner",
        "correlation_id",
        "requested_model",
        "returned_model",
        "response_id",
        "provider_session_id",
        "input_sha256",
        "duration_ms",
        "warnings",
        "safe_error",
        "completed_at",
        "authorizing_search_attempt_id",
        "authorizing_operation_kind",
    } <= provider_attempt_columns
    provider_attempt_foreign_keys = {
        foreign_key["name"]: (
            tuple(foreign_key["constrained_columns"]),
            tuple(foreign_key["referred_columns"]),
        )
        for foreign_key in inspector.get_foreign_keys("provider_attempts")
    }
    assert provider_attempt_foreign_keys["fk_provider_attempts_authorizing_search_provenance"] == (
        (
            "authorizing_search_attempt_id",
            "run_id",
            "org_id",
            "project_id",
            "item_id",
            "query_id",
            "authorizing_operation_kind",
        ),
        (
            "id",
            "run_id",
            "org_id",
            "project_id",
            "item_id",
            "query_id",
            "operation_kind",
        ),
    )
    authorization_columns = {
        column["name"] for column in inspector.get_columns("search_result_authorizations")
    }
    assert {
        "org_id",
        "project_id",
        "item_id",
        "run_id",
        "query_id",
        "search_attempt_id",
        "search_operation_kind",
        "url",
        "canonical_url",
        "excerpt",
    } <= authorization_columns
    authorization_foreign_keys = {
        foreign_key["name"]: (
            tuple(foreign_key["constrained_columns"]),
            tuple(foreign_key["referred_columns"]),
        )
        for foreign_key in inspector.get_foreign_keys("search_result_authorizations")
    }
    assert authorization_foreign_keys["fk_search_authorizations_attempt_provenance"] == (
        (
            "search_attempt_id",
            "run_id",
            "org_id",
            "project_id",
            "item_id",
            "query_id",
            "search_operation_kind",
        ),
        (
            "id",
            "run_id",
            "org_id",
            "project_id",
            "item_id",
            "query_id",
            "operation_kind",
        ),
    )
    extract_target_columns = {
        column["name"] for column in inspector.get_columns("extract_target_authorizations")
    }
    assert {
        "org_id",
        "project_id",
        "item_id",
        "run_id",
        "query_id",
        "extract_attempt_id",
        "extract_operation_kind",
        "authorization_id",
        "authorizing_search_attempt_id",
        "canonical_url",
        "ordinal",
    } <= extract_target_columns
    extract_target_foreign_keys = {
        foreign_key["name"]: (
            tuple(foreign_key["constrained_columns"]),
            tuple(foreign_key["referred_columns"]),
        )
        for foreign_key in inspector.get_foreign_keys("extract_target_authorizations")
    }
    assert extract_target_foreign_keys["fk_extract_targets_attempt_provenance"] == (
        (
            "extract_attempt_id",
            "run_id",
            "org_id",
            "project_id",
            "item_id",
            "query_id",
            "authorizing_search_attempt_id",
            "extract_operation_kind",
        ),
        (
            "id",
            "run_id",
            "org_id",
            "project_id",
            "item_id",
            "query_id",
            "authorizing_search_attempt_id",
            "operation_kind",
        ),
    )
    assert extract_target_foreign_keys["fk_extract_targets_authorization_provenance"] == (
        (
            "authorization_id",
            "run_id",
            "org_id",
            "project_id",
            "item_id",
            "query_id",
            "authorizing_search_attempt_id",
            "canonical_url",
        ),
        (
            "id",
            "run_id",
            "org_id",
            "project_id",
            "item_id",
            "query_id",
            "search_attempt_id",
            "canonical_url",
        ),
    )
    source_snapshot_columns = {
        column["name"] for column in inspector.get_columns("source_snapshots")
    }
    assert {
        "query_id",
        "provider_attempt_id",
        "authorization_id",
        "authorizing_search_attempt_id",
    } <= source_snapshot_columns
    source_snapshot_foreign_keys = {
        foreign_key["name"]: (
            tuple(foreign_key["constrained_columns"]),
            tuple(foreign_key["referred_columns"]),
        )
        for foreign_key in inspector.get_foreign_keys("source_snapshots")
    }
    assert source_snapshot_foreign_keys["fk_source_snapshots_attempt_provenance"] == (
        (
            "provider_attempt_id",
            "run_id",
            "org_id",
            "project_id",
            "item_id",
            "query_id",
            "authorizing_search_attempt_id",
        ),
        (
            "id",
            "run_id",
            "org_id",
            "project_id",
            "item_id",
            "query_id",
            "authorizing_search_attempt_id",
        ),
    )
    assert source_snapshot_foreign_keys["fk_source_snapshots_authorization_provenance"] == (
        (
            "authorization_id",
            "run_id",
            "org_id",
            "project_id",
            "item_id",
            "query_id",
            "authorizing_search_attempt_id",
        ),
        (
            "id",
            "run_id",
            "org_id",
            "project_id",
            "item_id",
            "query_id",
            "search_attempt_id",
        ),
    )
    evidence_claim_columns = {column["name"] for column in inspector.get_columns("evidence_claims")}
    assert {"run_id", "query_id", "provider_attempt_id"} <= evidence_claim_columns
    evidence_claim_foreign_keys = {
        foreign_key["name"]: (
            tuple(foreign_key["constrained_columns"]),
            tuple(foreign_key["referred_columns"]),
        )
        for foreign_key in inspector.get_foreign_keys("evidence_claims")
    }
    assert evidence_claim_foreign_keys["fk_evidence_claims_snapshot_research_provenance"] == (
        (
            "snapshot_id",
            "org_id",
            "project_id",
            "item_id",
            "run_id",
            "query_id",
            "provider_attempt_id",
        ),
        (
            "id",
            "org_id",
            "project_id",
            "item_id",
            "run_id",
            "query_id",
            "provider_attempt_id",
        ),
    )

    evaluation_columns = {
        column["name"]: column for column in inspector.get_columns("agent_evaluations")
    }
    assert {
        "critique",
        "rubric_version",
        "prompt_version",
        "policy_version",
        "requested_model",
        "returned_model",
        "input_sha256",
        "response_id",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "latency_ms",
        "repair_count",
        "attempt_group_id",
    } <= set(evaluation_columns)
    assert evaluation_columns["requested_model"]["nullable"] is False
    assert evaluation_columns["returned_model"]["nullable"] is True
    invocation_columns = {
        column["name"]: column for column in inspector.get_columns("ai_judge_invocations")
    }
    assert {
        "id",
        "org_id",
        "project_id",
        "run_id",
        "job_attempt_number",
        "lease_owner",
        "stage",
        "status",
        "requested_model",
        "rubric_version",
        "prompt_version",
        "policy_version",
        "input_sha256",
        "evaluation_id",
        "safe_error",
        "created_at",
        "completed_at",
    } == set(invocation_columns)
    assert invocation_columns["evaluation_id"]["nullable"] is True
    attempt_columns = {
        column["name"]: column for column in inspector.get_columns("ai_provider_attempts")
    }
    assert {
        "org_id",
        "project_id",
        "run_id",
        "evaluation_id",
        "attempt_group_id",
        "ordinal",
        "role",
        "status",
        "requested_model",
        "returned_model",
        "rubric_version",
        "prompt_version",
        "policy_version",
        "input_sha256",
        "response_id",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "latency_ms",
        "safe_error",
        "created_at",
        "completed_at",
    } <= set(attempt_columns)
    evaluation_uniques = {
        constraint["name"]: tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("agent_evaluations")
    }
    assert evaluation_uniques["uq_agent_evaluations_invocation_provenance"] == (
        "id",
        "org_id",
        "project_id",
        "run_id",
        "attempt_group_id",
    )
    invocation_uniques = {
        constraint["name"]: tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("ai_judge_invocations")
    }
    assert invocation_uniques["uq_ai_judge_invocations_run_scope"] == (
        "id",
        "org_id",
        "project_id",
        "run_id",
    )
    invocation_foreign_keys = {
        foreign_key["name"]: (
            tuple(foreign_key["constrained_columns"]),
            tuple(foreign_key["referred_columns"]),
        )
        for foreign_key in inspector.get_foreign_keys("ai_judge_invocations")
    }
    assert invocation_foreign_keys["fk_ai_judge_invocations_evaluation_provenance"] == (
        ("evaluation_id", "org_id", "project_id", "run_id", "id"),
        ("id", "org_id", "project_id", "run_id", "attempt_group_id"),
    )
    attempt_foreign_keys = {
        foreign_key["name"]: (
            tuple(foreign_key["constrained_columns"]),
            tuple(foreign_key["referred_columns"]),
        )
        for foreign_key in inspector.get_foreign_keys("ai_provider_attempts")
    }
    assert attempt_foreign_keys["fk_ai_provider_attempts_invocation_provenance"] == (
        ("attempt_group_id", "org_id", "project_id", "run_id"),
        ("id", "org_id", "project_id", "run_id"),
    )
    assert attempt_foreign_keys["fk_ai_provider_attempts_evaluation_provenance"] == (
        ("evaluation_id", "org_id", "project_id", "run_id", "attempt_group_id"),
        ("id", "org_id", "project_id", "run_id", "attempt_group_id"),
    )

    detection_invocation_columns = {
        column["name"]: column for column in inspector.get_columns("detection_invocations")
    }
    assert {
        "id",
        "org_id",
        "project_id",
        "run_id",
        "job_attempt_number",
        "lease_owner",
        "script_version_id",
        "element_id",
        "status",
        "requested_model",
        "returned_model",
        "input_sha256",
        "response_id",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "latency_ms",
        "candidate_count",
        "safe_error",
        "created_at",
        "completed_at",
    } == set(detection_invocation_columns)
    detection_candidate_columns = {
        column["name"]: column for column in inspector.get_columns("detection_candidates")
    }
    assert {
        "id",
        "org_id",
        "project_id",
        "run_id",
        "invocation_id",
        "script_version_id",
        "element_id",
        "ordinal",
        "category",
        "span_start",
        "span_end",
        "text",
        "rationale",
        "uncertainty",
        "candidate_fingerprint",
        "created_at",
    } == set(detection_candidate_columns)

    candidate_foreign_keys = {
        foreign_key["name"]: (
            tuple(foreign_key["constrained_columns"]),
            tuple(foreign_key["referred_columns"]),
        )
        for foreign_key in inspector.get_foreign_keys("detection_candidates")
    }
    assert candidate_foreign_keys["fk_detection_candidates_invocation_provenance"] == (
        (
            "invocation_id",
            "org_id",
            "project_id",
            "run_id",
            "script_version_id",
            "element_id",
        ),
        (
            "id",
            "org_id",
            "project_id",
            "run_id",
            "script_version_id",
            "element_id",
        ),
    )
    gate_foreign_keys = {
        foreign_key["name"]: (
            tuple(foreign_key["constrained_columns"]),
            tuple(foreign_key["referred_columns"]),
        )
        for foreign_key in inspector.get_foreign_keys("deterministic_gate_results")
    }
    assert gate_foreign_keys["fk_gate_results_detection_candidate_scope"] == (
        ("candidate_id", "org_id", "project_id", "run_id"),
        ("id", "org_id", "project_id", "run_id"),
    )
    candidate_uniques = {
        constraint["name"]: tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("detection_candidates")
    }
    assert candidate_uniques["uq_detection_candidates_item_provenance"] == (
        "id",
        "org_id",
        "project_id",
        "run_id",
        "script_version_id",
        "element_id",
        "candidate_fingerprint",
    )
    item_columns = {column["name"]: column for column in inspector.get_columns("clearance_items")}
    assert item_columns["detection_run_id"]["nullable"] is True
    item_foreign_keys = {
        foreign_key["name"]: (
            tuple(foreign_key["constrained_columns"]),
            tuple(foreign_key["referred_columns"]),
        )
        for foreign_key in inspector.get_foreign_keys("clearance_items")
    }
    assert item_foreign_keys["fk_clearance_items_script_version_provenance"] == (
        ("version_id", "org_id", "project_id", "script_id"),
        ("id", "org_id", "project_id", "script_id"),
    )
    assert item_foreign_keys["fk_clearance_items_detection_candidate_provenance"] == (
        (
            "detection_candidate_id",
            "org_id",
            "project_id",
            "detection_run_id",
            "version_id",
            "element_id",
            "candidate_fingerprint",
        ),
        (
            "id",
            "org_id",
            "project_id",
            "run_id",
            "script_version_id",
            "element_id",
            "candidate_fingerprint",
        ),
    )

    engine.dispose()


def test_populated_0021_database_upgrades_and_downgrades_without_data_loss(tmp_path: Path) -> None:
    database_path = tmp_path / "populated-0021.db"
    engine = _migrate(database_path, "0021_report_releases")
    now = datetime.now(UTC)
    user_id, org_id, project_id, job_id, event_id = (str(uuid4()) for _ in range(5))

    with engine.begin() as connection:
        connection.execute(
            sa.text("INSERT INTO users (id, email, created_at) VALUES (:id, :email, :created)"),
            {"id": user_id, "email": "migration@example.com", "created": now},
        )
        connection.execute(
            sa.text(
                "INSERT INTO organizations (id, name, slug, created_at) "
                "VALUES (:id, 'Migration Org', 'migration-org', :created)"
            ),
            {"id": org_id, "created": now},
        )
        connection.execute(
            sa.text(
                "INSERT INTO projects (id, org_id, title, created_at) "
                "VALUES (:id, :org, 'Migration Project', :created)"
            ),
            {"id": project_id, "org": org_id, "created": now},
        )
        connection.execute(
            sa.text(
                "INSERT INTO jobs (id, org_id, project_id, job_type, status, idempotency_key, "
                "payload, created_at, available_at) VALUES "
                "(:id, :org, :project, 'detection', 'queued', 'migration-job', :payload, "
                ":created, :available)"
            ),
            {
                "id": job_id,
                "org": org_id,
                "project": project_id,
                "payload": json.dumps({"schemaVersion": 1}),
                "created": now,
                "available": now,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO authoritative_audit_events "
                "(id, org_id, project_id, actor_id, action, target_type, target_id, "
                "payload_redacted, occurred_at) VALUES "
                "(:id, :org, :project, :actor, 'migration.test', 'job', :target, '{}', :at)"
            ),
            {
                "id": event_id,
                "org": org_id,
                "project": project_id,
                "actor": user_id,
                "target": job_id,
                "at": now,
            },
        )
    engine.dispose()

    command.upgrade(_config(database_path), "head")
    engine = _engine(database_path)
    with engine.connect() as connection:
        job = (
            connection.execute(
                sa.text(
                    "SELECT progress, stage, correlation_id, attempt_count, updated_at "
                    "FROM jobs WHERE id = :id"
                ),
                {"id": job_id},
            )
            .mappings()
            .one()
        )
        event_correlation = connection.execute(
            sa.text("SELECT correlation_id FROM authoritative_audit_events WHERE id = :id"),
            {"id": event_id},
        ).scalar_one()
        assert job["progress"] == 0
        assert job["stage"] == "queued"
        assert job["correlation_id"] == job_id
        assert job["attempt_count"] == 0
        assert job["updated_at"] is not None
        assert event_correlation == event_id
    engine.dispose()

    command.downgrade(_config(database_path), "0021_report_releases")
    engine = _engine(database_path)
    inspector = sa.inspect(engine)
    assert "progress" not in {column["name"] for column in inspector.get_columns("jobs")}
    with engine.connect() as connection:
        assert (
            connection.execute(
                sa.text("SELECT count(*) FROM jobs WHERE id = :id"), {"id": job_id}
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                sa.text("SELECT count(*) FROM authoritative_audit_events WHERE id = :id"),
                {"id": event_id},
            ).scalar_one()
            == 1
        )
    engine.dispose()


def test_tenant_scoped_provenance_foreign_keys_are_enforced(tmp_path: Path) -> None:
    database_path = tmp_path / "tenant-scope.db"
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
        research_run_a,
        job_a,
        evaluation_a,
    ) = (str(uuid4()) for _ in range(14))

    with engine.begin() as connection:
        for org_id, slug in ((org_a, "org-a"), (org_b, "org-b")):
            connection.execute(
                sa.text(
                    "INSERT INTO organizations (id, name, slug, created_at) "
                    "VALUES (:id, :name, :slug, :created)"
                ),
                {"id": org_id, "name": slug, "slug": slug, "created": now},
            )
        for project_id, org_id, title in (
            (project_a, org_a, "A"),
            (project_b, org_b, "B"),
        ):
            connection.execute(
                sa.text(
                    "INSERT INTO projects (id, org_id, title, created_at) "
                    "VALUES (:id, :org, :title, :created)"
                ),
                {"id": project_id, "org": org_id, "title": title, "created": now},
            )
        for script_id, version_id, element_id, org_id, project_id, title in (
            (script_a, version_a, element_a, org_a, project_a, "Script A"),
            (script_b, version_b, element_b, org_b, project_b, "Script B"),
        ):
            connection.execute(
                sa.text(
                    "INSERT INTO scripts (id, org_id, project_id, title, created_at) "
                    "VALUES (:id, :org, :project, :title, :created)"
                ),
                {
                    "id": script_id,
                    "org": org_id,
                    "project": project_id,
                    "title": title,
                    "created": now,
                },
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
                    "hash": f"hash-{title}",
                    "created": now,
                },
            )
            connection.execute(
                sa.text(
                    "INSERT INTO script_elements "
                    "(id, version_id, ordinal, element_type, text) "
                    "VALUES (:id, :version, 1, 'action', :text)"
                ),
                {"id": element_id, "version": version_id, "text": title},
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
                "id": item_a,
                "org": org_a,
                "project": project_a,
                "script": script_a,
                "version": version_a,
                "element": element_a,
                "created": now,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO research_runs (id, org_id, project_id, item_id, status, created_at) "
                "VALUES (:id, :org, :project, :item, 'running', :created)"
            ),
            {
                "id": research_run_a,
                "org": org_a,
                "project": project_a,
                "item": item_a,
                "created": now,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO jobs "
                "(id, org_id, project_id, job_type, status, idempotency_key, payload, progress, "
                "stage, correlation_id, attempt_count, available_at, created_at, updated_at) "
                "VALUES (:id, :org, :project, 'detection', 'running', 'scope-job', '{}', 50, "
                "'running', :correlation, 1, :available, :created, :updated)"
            ),
            {
                "id": job_a,
                "org": org_a,
                "project": project_a,
                "correlation": job_a,
                "available": now,
                "created": now,
                "updated": now,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO agent_evaluations "
                "(id, org_id, project_id, run_id, stage, scored_dimensions_count, "
                "blockers_count, created_at, critique, rubric_version, prompt_version, "
                "policy_version, requested_model, returned_model, input_sha256, "
                "response_id, latency_ms, repair_count, attempt_group_id) VALUES "
                "(:id, :org, :project, :run, 'detection', 1, 0, :created, "
                "'Scoped evaluation', 'rubric-v1', 'prompt-v1', 'policy-v1', "
                "'gemini-3.1-pro-preview', 'gemini-3.1-pro-preview-20260815', "
                ":input_hash, 'scope-response', 1, 0, :attempt_group_id)"
            ),
            {
                "id": evaluation_a,
                "org": org_a,
                "project": project_a,
                "run": job_a,
                "created": now,
                "input_hash": "a" * 64,
                "attempt_group_id": evaluation_a,
            },
        )

    inspector = sa.inspect(engine)
    for table_name, expected_fk in (
        ("clearance_items", "fk_clearance_items_element_version"),
        ("research_queries", "fk_research_queries_run_scope"),
        ("provider_attempts", "fk_provider_attempts_run_scope"),
        ("evidence_conflicts", "fk_evidence_conflicts_item_scope"),
        ("judge_verdicts", "fk_judge_verdicts_evaluation_scope"),
    ):
        assert expected_fk in {
            foreign_key["name"] for foreign_key in inspector.get_foreign_keys(table_name)
        }

    invalid_statements = (
        (
            "INSERT INTO report_snapshots "
            "(id, org_id, project_id, script_version_id, status, content_hash, "
            "binding_manifest, created_at) VALUES "
            "(:id, :org, :project, :parent, 'draft', 'hash', '{}', :created)",
            version_a,
        ),
        (
            "INSERT INTO deterministic_gate_results "
            "(id, org_id, project_id, run_id, gate_name, passed, severity, details, created_at) "
            "VALUES (:id, :org, :project, :parent, 'scope', 0, 'blocker', 'mismatch', :created)",
            job_a,
        ),
        (
            "INSERT INTO clearance_items "
            "(id, org_id, project_id, script_id, version_id, element_id, category, text, "
            "status, created_at) VALUES "
            "(:id, :org, :project, :script, :version, :parent, 'brands', 'Mismatch', "
            "'unresolved', :created)",
            element_b,
        ),
        (
            "INSERT INTO research_queries (id, run_id, query, ordinal, org_id, project_id) "
            "VALUES (:id, :parent, 'query', 1, :org, :project)",
            research_run_a,
        ),
        (
            "INSERT INTO evidence_conflicts "
            "(id, item_id, description, created_at, org_id, project_id) "
            "VALUES (:id, :parent, 'conflict', :created, :org, :project)",
            item_a,
        ),
        (
            "INSERT INTO judge_verdicts "
            "(id, evaluation_id, dimension, status, rationale, created_at, org_id, project_id) "
            "VALUES (:id, :parent, 'grounding', 'failed', 'mismatch', :created, :org, :project)",
            evaluation_a,
        ),
    )
    for statement, parent_id in invalid_statements:
        with pytest.raises(IntegrityError), engine.begin() as connection:
            parameters = {
                "id": str(uuid4()),
                "org": org_b,
                "project": project_b,
                "parent": parent_id,
                "script": script_a,
                "version": version_a,
                "created": now,
            }
            connection.execute(sa.text(statement), parameters)
    engine.dispose()


@pytest.mark.parametrize(
    ("legacy_table", "create_version_table", "version_value"),
    [
        ("users", False, None),
        ("protected_configurations", True, None),
        ("users", True, "unknown_revision"),
    ],
)
def test_unversioned_or_unknown_schema_is_refused_without_mutation(
    tmp_path: Path,
    legacy_table: str,
    create_version_table: bool,
    version_value: str | None,
) -> None:
    suffix = version_value or ("empty-version" if create_version_table else "no-version")
    engine = sa.create_engine(f"sqlite:///{tmp_path / f'legacy-{legacy_table}-{suffix}.db'}")
    with engine.begin() as connection:
        connection.execute(
            sa.text(f"CREATE TABLE {legacy_table} (id TEXT PRIMARY KEY, value TEXT)")
        )
        connection.execute(
            sa.text(f"INSERT INTO {legacy_table} (id, value) VALUES ('legacy-row', 'preserve-me')")
        )
        if create_version_table:
            connection.execute(
                sa.text("CREATE TABLE alembic_version (version_num VARCHAR(64) PRIMARY KEY)")
            )
            if version_value is not None:
                connection.execute(
                    sa.text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
                    {"revision": version_value},
                )

    with (
        engine.connect() as connection,
        pytest.raises(UnversionedLegacySchemaError, match="startup stopped before modifying"),
    ):
        _validate_database_bootstrap(connection)

    with engine.connect() as connection:
        assert (
            connection.execute(sa.text(f"SELECT value FROM {legacy_table}")).scalar_one()
            == "preserve-me"
        )
        table_names = sa.inspect(connection).get_table_names()
        if create_version_table:
            revisions = (
                connection.execute(sa.text("SELECT version_num FROM alembic_version"))
                .scalars()
                .all()
            )
            assert revisions == ([version_value] if version_value is not None else [])
        else:
            assert "alembic_version" not in table_names
    engine.dispose()


@pytest.mark.asyncio
async def test_api_worker_lifespan_does_not_run_migrations_or_seed(monkeypatch) -> None:
    from clearcut import init_db
    from clearcut.main import app

    async def fail_if_called(*_args, **_kwargs) -> None:
        raise AssertionError("API worker startup must not migrate or seed")

    monkeypatch.setattr(init_db, "init_and_seed_db", fail_if_called)
    async with app.router.lifespan_context(app):
        pass


def test_0023_preserves_historical_multi_script_projects(tmp_path: Path) -> None:
    database_path = tmp_path / "multi-script-0022.db"
    engine = _migrate(database_path, "0022_runtime_alignment")
    now = datetime.now(UTC)
    org_id, project_id, first_script, second_script, first_version, second_version = (
        str(uuid4()) for _ in range(6)
    )

    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO organizations (id, name, slug, created_at) "
                "VALUES (:id, 'History Org', 'history-org', :created)"
            ),
            {"id": org_id, "created": now},
        )
        connection.execute(
            sa.text(
                "INSERT INTO projects (id, org_id, title, created_at) "
                "VALUES (:id, :org_id, 'Historical Project', :created)"
            ),
            {"id": project_id, "org_id": org_id, "created": now},
        )
        for script_id, version_id, title in (
            (first_script, first_version, "First Script"),
            (second_script, second_version, "Second Script"),
        ):
            connection.execute(
                sa.text(
                    "INSERT INTO scripts (id, org_id, project_id, title, created_at) "
                    "VALUES (:id, :org_id, :project_id, :title, :created)"
                ),
                {
                    "id": script_id,
                    "org_id": org_id,
                    "project_id": project_id,
                    "title": title,
                    "created": now,
                },
            )
            connection.execute(
                sa.text(
                    "INSERT INTO script_versions "
                    "(id, script_id, org_id, project_id, ordinal, source_hash, "
                    "parser_version, created_at) VALUES "
                    "(:id, :script_id, :org_id, :project_id, 1, :source_hash, 'legacy', :created)"
                ),
                {
                    "id": version_id,
                    "script_id": script_id,
                    "org_id": org_id,
                    "project_id": project_id,
                    "source_hash": version_id.replace("-", "")[:64],
                    "created": now,
                },
            )
    engine.dispose()

    command.upgrade(_config(database_path), "head")
    engine = _engine(database_path)
    with engine.connect() as connection:
        scripts = (
            connection.execute(
                sa.text(
                    "SELECT id, current_slot FROM scripts "
                    "WHERE org_id = :org_id AND project_id = :project_id ORDER BY id"
                ),
                {"org_id": org_id, "project_id": project_id},
            )
            .mappings()
            .all()
        )
        version_ids = set(
            connection.execute(
                sa.text(
                    "SELECT id FROM script_versions "
                    "WHERE org_id = :org_id AND project_id = :project_id"
                ),
                {"org_id": org_id, "project_id": project_id},
            ).scalars()
        )
    assert {row["id"] for row in scripts} == {first_script, second_script}
    assert [row["current_slot"] for row in scripts].count("current") == 1
    assert version_ids == {first_version, second_version}
    engine.dispose()


def test_0024_preserves_duplicate_evaluation_history_and_closes_score_matrix(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "duplicate-evaluation-history-0023.db"
    engine = _migrate(database_path, "0023_persistent_script_import")
    now = datetime.now(UTC)
    org_id, project_id, run_id, first_evaluation_id, second_evaluation_id = (
        str(uuid4()) for _ in range(5)
    )
    first_verdict_id, duplicate_verdict_id = str(uuid4()), str(uuid4())

    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO organizations (id, name, slug, created_at) "
                "VALUES (:id, 'Evaluation History Org', 'evaluation-history-org', :created)"
            ),
            {"id": org_id, "created": now},
        )
        connection.execute(
            sa.text(
                "INSERT INTO projects (id, org_id, title, created_at) "
                "VALUES (:id, :org_id, 'Evaluation History', :created)"
            ),
            {"id": project_id, "org_id": org_id, "created": now},
        )
        connection.execute(
            sa.text(
                "INSERT INTO jobs "
                "(id, org_id, project_id, job_type, status, idempotency_key, payload, "
                "progress, stage, correlation_id, attempt_count, available_at, created_at, "
                "updated_at) VALUES "
                "(:id, :org_id, :project_id, 'detection', 'succeeded', 'history-job', '{}', "
                "100, 'succeeded', :id, 1, :created, :created, :created)"
            ),
            {
                "id": run_id,
                "org_id": org_id,
                "project_id": project_id,
                "created": now,
            },
        )
        for evaluation_id in (first_evaluation_id, second_evaluation_id):
            connection.execute(
                sa.text(
                    "INSERT INTO agent_evaluations "
                    "(id, org_id, project_id, run_id, stage, headline_score, "
                    "scored_dimensions_count, blockers_count, created_at) VALUES "
                    "(:id, :org_id, :project_id, :run_id, 'detection', 80, 1, 0, :created)"
                ),
                {
                    "id": evaluation_id,
                    "org_id": org_id,
                    "project_id": project_id,
                    "run_id": run_id,
                    "created": now,
                },
            )
        for verdict_id in (first_verdict_id, duplicate_verdict_id):
            connection.execute(
                sa.text(
                    "INSERT INTO judge_verdicts "
                    "(id, evaluation_id, dimension, status, score, rationale, created_at, "
                    "org_id, project_id) VALUES "
                    "(:id, :evaluation_id, 'detection_recall', 'scored', 80, "
                    "'Historical duplicate', :created, :org_id, :project_id)"
                ),
                {
                    "id": verdict_id,
                    "evaluation_id": first_evaluation_id,
                    "created": now,
                    "org_id": org_id,
                    "project_id": project_id,
                },
            )
    engine.dispose()

    command.upgrade(_config(database_path), "head")
    engine = _engine(database_path)
    inspector = sa.inspect(engine)
    evaluation_uniques = {
        constraint["name"] for constraint in inspector.get_unique_constraints("agent_evaluations")
    }
    verdict_uniques = {
        constraint["name"] for constraint in inspector.get_unique_constraints("judge_verdicts")
    }
    with engine.connect() as connection:
        assert (
            connection.execute(
                sa.text(
                    "SELECT count(*) FROM agent_evaluations "
                    "WHERE org_id = :org_id AND project_id = :project_id AND run_id = :run_id"
                ),
                {"org_id": org_id, "project_id": project_id, "run_id": run_id},
            ).scalar_one()
            == 2
        )
        assert (
            connection.execute(
                sa.text(
                    "SELECT count(*) FROM judge_verdicts "
                    "WHERE evaluation_id = :evaluation_id AND dimension = 'detection_recall'"
                ),
                {"evaluation_id": first_evaluation_id},
            ).scalar_one()
            == 2
        )

    assert "uq_agent_evaluations_run_stage" not in evaluation_uniques
    assert "uq_judge_verdicts_evaluation_dimension" not in verdict_uniques
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO judge_verdicts "
                "(id, evaluation_id, dimension, status, score, rationale, created_at, "
                "org_id, project_id) VALUES "
                "(:id, :evaluation_id, 'legal_boundary', 'failed', 95, "
                "'Invalid failed score', :created, :org_id, :project_id)"
            ),
            {
                "id": str(uuid4()),
                "evaluation_id": second_evaluation_id,
                "created": now,
                "org_id": org_id,
                "project_id": project_id,
            },
        )
    engine.dispose()


def test_0027_preserves_legacy_completed_run_and_downgrades_symmetrically(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "legacy-completed-research.db"
    engine = _migrate(database_path, "0026_full_provenance")
    assert "uq_research_runs_scope" in {
        constraint["name"]
        for constraint in sa.inspect(engine).get_unique_constraints("research_runs")
    }
    now = datetime.now(UTC)
    org_id, project_id, script_id, version_id, element_id, item_id, run_id = (
        str(uuid4()) for _ in range(7)
    )

    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO organizations (id, name, slug, created_at) "
                "VALUES (:id, 'Legacy Research Org', 'legacy-research-org', :created)"
            ),
            {"id": org_id, "created": now},
        )
        connection.execute(
            sa.text(
                "INSERT INTO projects (id, org_id, title, created_at) "
                "VALUES (:id, :org_id, 'Legacy Research', :created)"
            ),
            {"id": project_id, "org_id": org_id, "created": now},
        )
        connection.execute(
            sa.text(
                "INSERT INTO scripts (id, org_id, project_id, title, created_at) "
                "VALUES (:id, :org_id, :project_id, 'Legacy Script', :created)"
            ),
            {
                "id": script_id,
                "org_id": org_id,
                "project_id": project_id,
                "created": now,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO script_versions "
                "(id, script_id, org_id, project_id, ordinal, source_hash, "
                "parser_version, created_at) VALUES "
                "(:id, :script_id, :org_id, :project_id, 1, :source_hash, "
                "'legacy', :created)"
            ),
            {
                "id": version_id,
                "script_id": script_id,
                "org_id": org_id,
                "project_id": project_id,
                "source_hash": "legacy-research-hash",
                "created": now,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO script_elements "
                "(id, version_id, ordinal, element_type, text) "
                "VALUES (:id, :version_id, 1, 'action', 'Legacy Mark')"
            ),
            {"id": element_id, "version_id": version_id},
        )
        connection.execute(
            sa.text(
                "INSERT INTO clearance_items "
                "(id, org_id, project_id, script_id, version_id, element_id, "
                "category, text, status, created_at) VALUES "
                "(:id, :org_id, :project_id, :script_id, :version_id, "
                ":element_id, 'brands', 'Legacy Mark', 'unresolved', :created)"
            ),
            {
                "id": item_id,
                "org_id": org_id,
                "project_id": project_id,
                "script_id": script_id,
                "version_id": version_id,
                "element_id": element_id,
                "created": now,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO research_runs "
                "(id, org_id, project_id, item_id, status, created_at) VALUES "
                "(:id, :org_id, :project_id, :item_id, 'completed', :created)"
            ),
            {
                "id": run_id,
                "org_id": org_id,
                "project_id": project_id,
                "item_id": item_id,
                "created": now,
            },
        )
    engine.dispose()

    command.upgrade(_config(database_path), "head")
    engine = _engine(database_path)
    with engine.connect() as connection:
        run = (
            connection.execute(
                sa.text("SELECT status, version_id FROM research_runs WHERE id = :run_id"),
                {"run_id": run_id},
            )
            .mappings()
            .one()
        )
    assert run["status"] == "completed"
    assert run["version_id"] == version_id
    assert "uq_clearance_items_research_scope" in {
        constraint["name"]
        for constraint in sa.inspect(engine).get_unique_constraints("clearance_items")
    }
    engine.dispose()

    command.downgrade(_config(database_path), "0026_full_provenance")
    engine = _engine(database_path)
    inspector = sa.inspect(engine)
    with engine.connect() as connection:
        assert (
            connection.execute(
                sa.text("SELECT status FROM research_runs WHERE id = :run_id"),
                {"run_id": run_id},
            ).scalar_one()
            == "completed"
        )
    assert "version_id" not in {column["name"] for column in inspector.get_columns("research_runs")}
    assert "uq_clearance_items_research_scope" not in {
        constraint["name"] for constraint in inspector.get_unique_constraints("clearance_items")
    }
    assert "uq_research_runs_scope" in {
        constraint["name"] for constraint in inspector.get_unique_constraints("research_runs")
    }
    engine.dispose()

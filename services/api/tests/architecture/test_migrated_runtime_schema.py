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
    assert revision == "0037_rewrite_result_binding"

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


def _named_uniques(inspector: sa.Inspector, table_name: str) -> dict[str | None, tuple[str, ...]]:
    return {
        constraint["name"]: tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints(table_name)
    }


def _named_foreign_keys(
    inspector: sa.Inspector,
    table_name: str,
) -> dict[str | None, tuple[tuple[str, ...], str, tuple[str | None, ...]]]:
    return {
        foreign_key["name"]: (
            tuple(foreign_key["constrained_columns"]),
            foreign_key["referred_table"],
            tuple(foreign_key["referred_columns"]),
        )
        for foreign_key in inspector.get_foreign_keys(table_name)
    }


def test_revision_lineage_and_selective_rescan_schema_contract(tmp_path: Path) -> None:
    engine = _migrate(tmp_path / "revision-lineage-schema.db")
    inspector = sa.inspect(engine)

    assert {
        "script_element_lineage",
        "evidence_carry_forwards",
        "selective_rescan_checkpoints",
    } <= set(inspector.get_table_names())

    version_columns = {
        column["name"]: column for column in inspector.get_columns("script_versions")
    }
    assert {
        "predecessor_version_id",
        "predecessor_ordinal",
        "committed_by_actor_id",
    } <= set(version_columns)
    assert version_columns["predecessor_version_id"]["nullable"] is True
    assert version_columns["committed_by_actor_id"]["nullable"] is True
    version_uniques = _named_uniques(inspector, "script_versions")
    assert version_uniques["uq_script_versions_ordinal"] == (
        "org_id",
        "project_id",
        "script_id",
        "ordinal",
    )
    assert version_uniques["uq_script_versions_revision_provenance"] == (
        "id",
        "org_id",
        "project_id",
        "script_id",
        "ordinal",
    )
    version_foreign_keys = _named_foreign_keys(inspector, "script_versions")
    assert version_foreign_keys["fk_script_versions_predecessor_scope"] == (
        (
            "predecessor_version_id",
            "org_id",
            "project_id",
            "script_id",
            "predecessor_ordinal",
        ),
        "script_versions",
        ("id", "org_id", "project_id", "script_id", "ordinal"),
    )
    version_indexes = {
        index["name"]: tuple(index["column_names"])
        for index in inspector.get_indexes("script_versions")
    }
    assert version_indexes["uq_script_versions_checkpoint_scope"] == (
        "id",
        "org_id",
        "project_id",
    )
    assert version_foreign_keys["fk_script_versions_committing_actor_membership"] == (
        ("org_id", "committed_by_actor_id"),
        "memberships",
        ("org_id", "user_id"),
    )

    diff_columns = {column["name"]: column for column in inspector.get_columns("script_diffs")}
    assert {
        "script_id",
        "before_ordinal",
        "after_ordinal",
        "algorithm_version",
        "summary_payload",
        "diff_payload",
    } <= set(diff_columns)
    for column_name in (
        "script_id",
        "before_ordinal",
        "after_ordinal",
        "algorithm_version",
        "summary_payload",
        "diff_payload",
    ):
        assert diff_columns[column_name]["nullable"] is False
    diff_uniques = _named_uniques(inspector, "script_diffs")
    assert diff_uniques["uq_script_diffs_adjacent"] == (
        "org_id",
        "project_id",
        "script_id",
        "before_version_id",
        "after_version_id",
    )
    assert diff_uniques["uq_script_diffs_after_version"] == (
        "org_id",
        "project_id",
        "script_id",
        "after_version_id",
    )
    diff_foreign_keys = _named_foreign_keys(inspector, "script_diffs")
    assert diff_foreign_keys["fk_script_diffs_before_version_scope"] == (
        (
            "before_version_id",
            "org_id",
            "project_id",
            "script_id",
            "before_ordinal",
        ),
        "script_versions",
        ("id", "org_id", "project_id", "script_id", "ordinal"),
    )
    assert diff_foreign_keys["fk_script_diffs_after_version_scope"] == (
        (
            "after_version_id",
            "org_id",
            "project_id",
            "script_id",
            "after_ordinal",
        ),
        "script_versions",
        ("id", "org_id", "project_id", "script_id", "ordinal"),
    )

    lineage_columns = {
        column["name"]: column for column in inspector.get_columns("script_element_lineage")
    }
    assert {
        "id",
        "org_id",
        "project_id",
        "script_id",
        "diff_id",
        "before_version_id",
        "after_version_id",
        "before_element_id",
        "after_element_id",
        "change_kind",
        "confidence",
        "algorithm_version",
        "created_at",
    } == set(lineage_columns)
    assert lineage_columns["before_element_id"]["nullable"] is True
    assert lineage_columns["after_element_id"]["nullable"] is True
    lineage_uniques = _named_uniques(inspector, "script_element_lineage")
    assert lineage_uniques["uq_script_element_lineage_before"] == (
        "diff_id",
        "before_element_id",
    )
    assert lineage_uniques["uq_script_element_lineage_after"] == (
        "diff_id",
        "after_element_id",
    )
    lineage_checks = {
        constraint["name"]
        for constraint in inspector.get_check_constraints("script_element_lineage")
    }
    assert {
        "ck_script_element_lineage_change_kind",
        "ck_script_element_lineage_confidence",
        "ck_script_element_lineage_endpoints",
    } <= lineage_checks

    item_columns = {column["name"]: column for column in inspector.get_columns("clearance_items")}
    assert {
        "predecessor_item_id",
        "predecessor_version_id",
        "lineage_kind",
        "carried_forward_confirmation_required",
    } <= set(item_columns)
    assert item_columns["predecessor_item_id"]["nullable"] is True
    assert item_columns["predecessor_version_id"]["nullable"] is True
    assert item_columns["lineage_kind"]["nullable"] is True
    assert item_columns["carried_forward_confirmation_required"]["nullable"] is False
    item_uniques = _named_uniques(inspector, "clearance_items")
    assert item_uniques["uq_clearance_items_successor_projection"] == (
        "org_id",
        "project_id",
        "predecessor_item_id",
        "version_id",
    )
    item_foreign_keys = _named_foreign_keys(inspector, "clearance_items")
    assert item_foreign_keys["fk_clearance_items_predecessor_item_scope"] == (
        (
            "predecessor_item_id",
            "org_id",
            "project_id",
            "script_id",
            "predecessor_version_id",
        ),
        "clearance_items",
        ("id", "org_id", "project_id", "script_id", "version_id"),
    )
    assert item_foreign_keys["fk_clearance_items_predecessor_version_scope"] == (
        (
            "version_id",
            "org_id",
            "project_id",
            "script_id",
            "predecessor_version_id",
        ),
        "script_versions",
        (
            "id",
            "org_id",
            "project_id",
            "script_id",
            "predecessor_version_id",
        ),
    )

    carry_columns = {
        column["name"]: column for column in inspector.get_columns("evidence_carry_forwards")
    }
    assert {
        "id",
        "org_id",
        "project_id",
        "new_item_id",
        "source_item_id",
        "original_claim_id",
        "snapshot_id",
        "run_id",
        "query_id",
        "provider_attempt_id",
        "new_item_lineage_kind",
        "confirmation_required",
        "created_at",
    } == set(carry_columns)
    carry_uniques = _named_uniques(inspector, "evidence_carry_forwards")
    assert carry_uniques["uq_evidence_carry_forwards_item_claim"] == (
        "org_id",
        "project_id",
        "new_item_id",
        "original_claim_id",
    )
    carry_foreign_keys = _named_foreign_keys(inspector, "evidence_carry_forwards")
    assert carry_foreign_keys["fk_evidence_carry_forwards_new_item_lineage"] == (
        (
            "new_item_id",
            "org_id",
            "project_id",
            "source_item_id",
            "new_item_lineage_kind",
            "confirmation_required",
        ),
        "clearance_items",
        (
            "id",
            "org_id",
            "project_id",
            "predecessor_item_id",
            "lineage_kind",
            "carried_forward_confirmation_required",
        ),
    )
    assert carry_foreign_keys["fk_evidence_carry_forwards_claim_provenance"] == (
        (
            "original_claim_id",
            "org_id",
            "project_id",
            "source_item_id",
            "snapshot_id",
            "run_id",
            "query_id",
            "provider_attempt_id",
        ),
        "evidence_claims",
        (
            "id",
            "org_id",
            "project_id",
            "item_id",
            "snapshot_id",
            "run_id",
            "query_id",
            "provider_attempt_id",
        ),
    )

    checkpoint_columns = {
        column["name"]: column for column in inspector.get_columns("selective_rescan_checkpoints")
    }
    assert {
        "id",
        "org_id",
        "project_id",
        "job_id",
        "stage",
        "script_version_id",
        "item_id",
        "status",
        "result",
        "safe_error",
        "attempt_number",
        "created_at",
        "completed_at",
    } == set(checkpoint_columns)
    assert checkpoint_columns["script_version_id"]["nullable"] is True
    assert checkpoint_columns["item_id"]["nullable"] is True
    checkpoint_indexes = {
        index["name"]: tuple(index["column_names"])
        for index in inspector.get_indexes("selective_rescan_checkpoints")
    }
    assert checkpoint_indexes["uq_selective_rescan_checkpoints_job_stage"] == (
        "org_id",
        "project_id",
        "job_id",
        "stage",
    )
    assert checkpoint_indexes["uq_selective_rescan_checkpoints_script_version"] == (
        "org_id",
        "project_id",
        "job_id",
        "stage",
        "script_version_id",
    )
    assert checkpoint_indexes["uq_selective_rescan_checkpoints_item"] == (
        "org_id",
        "project_id",
        "job_id",
        "stage",
        "item_id",
    )
    checkpoint_foreign_keys = _named_foreign_keys(
        inspector,
        "selective_rescan_checkpoints",
    )
    assert checkpoint_foreign_keys["fk_selective_rescan_checkpoints_job_scope"] == (
        ("job_id", "org_id", "project_id"),
        "jobs",
        ("id", "org_id", "project_id"),
    )
    assert checkpoint_foreign_keys["fk_selective_rescan_checkpoints_script_version_scope"] == (
        ("script_version_id", "org_id", "project_id"),
        "script_versions",
        ("id", "org_id", "project_id"),
    )
    assert checkpoint_foreign_keys["fk_selective_rescan_checkpoints_item_scope"] == (
        ("item_id", "org_id", "project_id"),
        "clearance_items",
        ("id", "org_id", "project_id"),
    )

    evidence_claim_foreign_keys = _named_foreign_keys(inspector, "evidence_claims")
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
        "source_snapshots",
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
    assert {column["name"] for column in inspector.get_columns("rescan_jobs")} == {
        "id",
        "org_id",
        "project_id",
        "after_version_id",
        "affected_count",
        "saved_calls_count",
        "status",
        "created_at",
    }
    engine.dispose()


def test_0035_backfills_existing_diff_without_fabricating_lineage(tmp_path: Path) -> None:
    database_path = tmp_path / "revision-lineage-backfill.db"
    engine = _migrate(database_path, "0034_report_artifacts")
    now = datetime.now(UTC)
    org_id, project_id, script_id, before_id, after_id, diff_id = (str(uuid4()) for _ in range(6))
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO organizations (id, name, slug, created_at) "
                "VALUES (:id, 'Revision Org', 'revision-org', :created)"
            ),
            {"id": org_id, "created": now},
        )
        connection.execute(
            sa.text(
                "INSERT INTO projects (id, org_id, title, created_at) "
                "VALUES (:id, :org, 'Revision Project', :created)"
            ),
            {"id": project_id, "org": org_id, "created": now},
        )
        connection.execute(
            sa.text(
                "INSERT INTO scripts (id, org_id, project_id, title, created_at) "
                "VALUES (:id, :org, :project, 'Revision Script', :created)"
            ),
            {
                "id": script_id,
                "org": org_id,
                "project": project_id,
                "created": now,
            },
        )
        for version_id, ordinal in ((before_id, 1), (after_id, 2)):
            connection.execute(
                sa.text(
                    "INSERT INTO script_versions "
                    "(id, script_id, org_id, project_id, ordinal, source_hash, "
                    "parser_version, created_at) VALUES "
                    "(:id, :script, :org, :project, :ordinal, :hash, 'legacy', :created)"
                ),
                {
                    "id": version_id,
                    "script": script_id,
                    "org": org_id,
                    "project": project_id,
                    "ordinal": ordinal,
                    "hash": version_id.replace("-", ""),
                    "created": now,
                },
            )
        connection.execute(
            sa.text(
                "INSERT INTO script_diffs "
                "(id, org_id, project_id, before_version_id, after_version_id, "
                "diff_payload, created_at) VALUES "
                "(:id, :org, :project, :before, :after, '{}', :created)"
            ),
            {
                "id": diff_id,
                "org": org_id,
                "project": project_id,
                "before": before_id,
                "after": after_id,
                "created": now,
            },
        )
    engine.dispose()

    command.upgrade(_config(database_path), "head")
    engine = _engine(database_path)
    with engine.connect() as connection:
        diff = (
            connection.execute(
                sa.text(
                    "SELECT script_id, before_ordinal, after_ordinal, algorithm_version, "
                    "summary_payload FROM script_diffs WHERE id = :id"
                ),
                {"id": diff_id},
            )
            .mappings()
            .one()
        )
        version_rows = connection.execute(
            sa.text(
                "SELECT predecessor_version_id, committed_by_actor_id "
                "FROM script_versions WHERE script_id = :script"
            ),
            {"script": script_id},
        ).all()
        lineage_count = connection.execute(
            sa.text("SELECT count(*) FROM script_element_lineage")
        ).scalar_one()
    assert diff["script_id"] == script_id
    assert (diff["before_ordinal"], diff["after_ordinal"]) == (1, 2)
    assert diff["algorithm_version"] == "legacy"
    assert diff["summary_payload"] is not None
    assert version_rows == [(None, None), (None, None)]
    assert lineage_count == 0
    engine.dispose()

    command.downgrade(_config(database_path), "0034_report_artifacts")
    engine = _engine(database_path)
    inspector = sa.inspect(engine)
    assert "script_element_lineage" not in inspector.get_table_names()
    assert "predecessor_version_id" not in {
        column["name"] for column in inspector.get_columns("script_versions")
    }
    with engine.connect() as connection:
        assert (
            connection.execute(
                sa.text("SELECT count(*) FROM script_diffs WHERE id = :id"),
                {"id": diff_id},
            ).scalar_one()
            == 1
        )
    engine.dispose()


def _seed_revision_project(
    connection: sa.Connection,
    *,
    org_id: str,
    project_id: str,
    script_id: str,
    before_version_id: str,
    after_version_id: str,
    before_element_id: str,
    after_element_id: str,
    now: datetime,
    slug: str,
) -> None:
    connection.execute(
        sa.text(
            "INSERT INTO organizations (id, name, slug, created_at) "
            "VALUES (:id, :slug, :slug, :created)"
        ),
        {"id": org_id, "slug": slug, "created": now},
    )
    connection.execute(
        sa.text(
            "INSERT INTO projects (id, org_id, title, created_at) "
            "VALUES (:id, :org, :slug, :created)"
        ),
        {"id": project_id, "org": org_id, "slug": slug, "created": now},
    )
    connection.execute(
        sa.text(
            "INSERT INTO scripts (id, org_id, project_id, title, created_at) "
            "VALUES (:id, :org, :project, :slug, :created)"
        ),
        {
            "id": script_id,
            "org": org_id,
            "project": project_id,
            "slug": slug,
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
            "id": before_version_id,
            "script": script_id,
            "org": org_id,
            "project": project_id,
            "hash": before_version_id.replace("-", ""),
            "created": now,
        },
    )
    connection.execute(
        sa.text(
            "INSERT INTO script_versions "
            "(id, script_id, org_id, project_id, ordinal, source_hash, parser_version, "
            "predecessor_version_id, predecessor_ordinal, created_at) VALUES "
            "(:id, :script, :org, :project, 2, :hash, '1', :before, 1, :created)"
        ),
        {
            "id": after_version_id,
            "script": script_id,
            "org": org_id,
            "project": project_id,
            "hash": after_version_id.replace("-", ""),
            "before": before_version_id,
            "created": now,
        },
    )
    for element_id, version_id in (
        (before_element_id, before_version_id),
        (after_element_id, after_version_id),
    ):
        connection.execute(
            sa.text(
                "INSERT INTO script_elements "
                "(id, version_id, ordinal, element_type, text) "
                "VALUES (:id, :version, 1, 'action', 'Body')"
            ),
            {"id": element_id, "version": version_id},
        )


def test_revision_lineage_constraints_fail_closed_and_are_replay_safe(
    tmp_path: Path,
) -> None:
    engine = _migrate(tmp_path / "revision-lineage-integrity.db")
    now = datetime.now(UTC)
    ids = [str(uuid4()) for _ in range(25)]
    (
        org_a,
        project_a,
        script_a,
        before_a,
        after_a,
        before_element_a,
        after_element_a,
        org_b,
        project_b,
        script_b,
        before_b,
        after_b,
        before_element_b,
        after_element_b,
        diff_a,
        old_item_a,
        new_item_a,
        item_b,
        job_a,
        run_a,
        query_a,
        attempt_a,
        authorization_a,
        snapshot_a,
        claim_a,
    ) = ids

    with engine.begin() as connection:
        _seed_revision_project(
            connection,
            org_id=org_a,
            project_id=project_a,
            script_id=script_a,
            before_version_id=before_a,
            after_version_id=after_a,
            before_element_id=before_element_a,
            after_element_id=after_element_a,
            now=now,
            slug="revision-a",
        )
        _seed_revision_project(
            connection,
            org_id=org_b,
            project_id=project_b,
            script_id=script_b,
            before_version_id=before_b,
            after_version_id=after_b,
            before_element_id=before_element_b,
            after_element_id=after_element_b,
            now=now,
            slug="revision-b",
        )
        connection.execute(
            sa.text(
                "INSERT INTO script_diffs "
                "(id, org_id, project_id, script_id, before_version_id, after_version_id, "
                "before_ordinal, after_ordinal, algorithm_version, summary_payload, "
                "diff_payload, created_at) VALUES "
                "(:id, :org, :project, :script, :before, :after, 1, 2, "
                "'element-lineage-v1', '{}', '{}', :created)"
            ),
            {
                "id": diff_a,
                "org": org_a,
                "project": project_a,
                "script": script_a,
                "before": before_a,
                "after": after_a,
                "created": now,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO script_element_lineage "
                "(id, org_id, project_id, script_id, diff_id, before_version_id, "
                "after_version_id, before_element_id, after_element_id, change_kind, "
                "confidence, algorithm_version, created_at) VALUES "
                "(:id, :org, :project, :script, :diff, :before_version, :after_version, "
                ":before_element, :after_element, 'unchanged', 'exact', "
                "'element-lineage-v1', :created)"
            ),
            {
                "id": str(uuid4()),
                "org": org_a,
                "project": project_a,
                "script": script_a,
                "diff": diff_a,
                "before_version": before_a,
                "after_version": after_a,
                "before_element": before_element_a,
                "after_element": after_element_a,
                "created": now,
            },
        )
        for item_id, version_id, element_id, predecessor_id, lineage_kind, confirmation in (
            (old_item_a, before_a, before_element_a, None, None, 0),
            (new_item_a, after_a, after_element_a, old_item_a, "carried_forward", 1),
        ):
            connection.execute(
                sa.text(
                    "INSERT INTO clearance_items "
                    "(id, org_id, project_id, script_id, version_id, element_id, category, "
                    "text, status, predecessor_item_id, predecessor_version_id, lineage_kind, "
                    "carried_forward_confirmation_required, created_at) VALUES "
                    "(:id, :org, :project, :script, :version, :element, 'brands', 'Brand', "
                    "'unresolved', :predecessor, :predecessor_version, :lineage, "
                    ":confirmation, :created)"
                ),
                {
                    "id": item_id,
                    "org": org_a,
                    "project": project_a,
                    "script": script_a,
                    "version": version_id,
                    "element": element_id,
                    "predecessor": predecessor_id,
                    "predecessor_version": before_a if predecessor_id else None,
                    "lineage": lineage_kind,
                    "confirmation": confirmation,
                    "created": now,
                },
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
                "id": item_b,
                "org": org_b,
                "project": project_b,
                "script": script_b,
                "version": after_b,
                "element": after_element_b,
                "created": now,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO jobs "
                "(id, org_id, project_id, job_type, status, idempotency_key, payload, "
                "progress, stage, correlation_id, attempt_count, available_at, created_at, "
                "updated_at) VALUES "
                "(:id, :org, :project, 'selective_rescan', 'running', 'revision-rescan', "
                "'{}', 0, 'lineage', :id, 1, :created, :created, :created)"
            ),
            {"id": job_a, "org": org_a, "project": project_a, "created": now},
        )
        connection.execute(
            sa.text(
                "INSERT INTO research_runs "
                "(id, org_id, project_id, item_id, version_id, status, created_at) VALUES "
                "(:id, :org, :project, :item, :version, 'running', :created)"
            ),
            {
                "id": run_a,
                "org": org_a,
                "project": project_a,
                "item": old_item_a,
                "version": before_a,
                "created": now,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO research_queries "
                "(id, run_id, query, ordinal, org_id, project_id, item_id, version_id, "
                "created_at) VALUES "
                "(:id, :run, 'query', 1, :org, :project, :item, :version, :created)"
            ),
            {
                "id": query_a,
                "run": run_a,
                "org": org_a,
                "project": project_a,
                "item": old_item_a,
                "version": before_a,
                "created": now,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO provider_attempts "
                "(id, run_id, operation_kind, status, receipt_id, created_at, org_id, "
                "project_id, item_id, query_id, job_attempt_number, "
                "authorizing_search_attempt_id, authorizing_operation_kind) VALUES "
                "(:id, :run, 'search', 'succeeded', 'receipt', :created, :org, :project, "
                ":item, :query, 1, :id, 'search')"
            ),
            {
                "id": attempt_a,
                "run": run_a,
                "created": now,
                "org": org_a,
                "project": project_a,
                "item": old_item_a,
                "query": query_a,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO search_result_authorizations "
                "(id, org_id, project_id, item_id, run_id, query_id, search_attempt_id, "
                "ordinal, url, canonical_url, title, publisher, excerpt, created_at) VALUES "
                "(:id, :org, :project, :item, :run, :query, :attempt, 1, "
                "'https://example.test/source', 'https://example.test/source', 'Title', "
                "'Publisher', 'Attributable excerpt', :created)"
            ),
            {
                "id": authorization_a,
                "org": org_a,
                "project": project_a,
                "item": old_item_a,
                "run": run_a,
                "query": query_a,
                "attempt": attempt_a,
                "created": now,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO source_snapshots "
                "(id, org_id, project_id, item_id, run_id, url, title, publisher, excerpt, "
                "origin, sha256_hash, retrieved_at, query_id, provider_attempt_id, "
                "authorization_id, authorizing_search_attempt_id) VALUES "
                "(:id, :org, :project, :item, :run, 'https://example.test/source', 'Title', "
                "'Publisher', 'Attributable excerpt', 'parallel', :hash, :retrieved, :query, "
                ":attempt, :authorization, :attempt)"
            ),
            {
                "id": snapshot_a,
                "org": org_a,
                "project": project_a,
                "item": old_item_a,
                "run": run_a,
                "hash": "a" * 64,
                "retrieved": now,
                "query": query_a,
                "attempt": attempt_a,
                "authorization": authorization_a,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO evidence_claims "
                "(id, org_id, project_id, item_id, snapshot_id, stance, authority_tier, "
                "claim_text, provenance_excerpt, created_at, run_id, query_id, "
                "provider_attempt_id) VALUES "
                "(:id, :org, :project, :item, :snapshot, 'supports', 'primary', 'Claim', "
                "'Attributable excerpt', :created, :run, :query, :attempt)"
            ),
            {
                "id": claim_a,
                "org": org_a,
                "project": project_a,
                "item": old_item_a,
                "snapshot": snapshot_a,
                "created": now,
                "run": run_a,
                "query": query_a,
                "attempt": attempt_a,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO evidence_carry_forwards "
                "(id, org_id, project_id, new_item_id, source_item_id, original_claim_id, "
                "snapshot_id, run_id, query_id, provider_attempt_id, created_at) VALUES "
                "(:id, :org, :project, :new_item, :source_item, :claim, :snapshot, :run, "
                ":query, :attempt, :created)"
            ),
            {
                "id": str(uuid4()),
                "org": org_a,
                "project": project_a,
                "new_item": new_item_a,
                "source_item": old_item_a,
                "claim": claim_a,
                "snapshot": snapshot_a,
                "run": run_a,
                "query": query_a,
                "attempt": attempt_a,
                "created": now,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO selective_rescan_checkpoints "
                "(id, org_id, project_id, job_id, stage, item_id, status, "
                "attempt_number, created_at, completed_at) VALUES "
                "(:id, :org, :project, :job, 'carrying_evidence', :item, "
                "'succeeded', 1, :created, :created)"
            ),
            {
                "id": str(uuid4()),
                "org": org_a,
                "project": project_a,
                "job": job_a,
                "item": new_item_a,
                "created": now,
            },
        )

    invalid_statements = (
        (
            "INSERT INTO script_versions "
            "(id, script_id, org_id, project_id, ordinal, source_hash, parser_version, "
            "predecessor_version_id, predecessor_ordinal, created_at) VALUES "
            "(:id, :script, :org, :project, 3, :hash, '1', :foreign, 2, :created)",
            {"script": script_b, "org": org_b, "project": project_b, "foreign": after_a},
        ),
        (
            "INSERT INTO script_versions "
            "(id, script_id, org_id, project_id, ordinal, source_hash, parser_version, "
            "created_at) VALUES "
            "(:id, :script, :org, :project, 2, :hash, '1', :created)",
            {"script": script_a, "org": org_a, "project": project_a},
        ),
        (
            "INSERT INTO script_diffs "
            "(id, org_id, project_id, script_id, before_version_id, after_version_id, "
            "before_ordinal, after_ordinal, algorithm_version, summary_payload, diff_payload, "
            "created_at) VALUES "
            "(:id, :org, :project, :script, :before, :after, 1, 2, 'v1', '{}', '{}', :created)",
            {
                "org": org_a,
                "project": project_a,
                "script": script_a,
                "before": before_a,
                "after": after_a,
            },
        ),
        (
            "INSERT INTO script_diffs "
            "(id, org_id, project_id, script_id, before_version_id, after_version_id, "
            "before_ordinal, after_ordinal, algorithm_version, summary_payload, diff_payload, "
            "created_at) VALUES "
            "(:id, :org, :project, :script, :before, :after, 1, 2, 'v1', '{}', '{}', :created)",
            {
                "org": org_b,
                "project": project_b,
                "script": script_b,
                "before": before_a,
                "after": after_b,
            },
        ),
        (
            "INSERT INTO script_element_lineage "
            "(id, org_id, project_id, script_id, diff_id, before_version_id, "
            "after_version_id, before_element_id, after_element_id, change_kind, confidence, "
            "algorithm_version, created_at) VALUES "
            "(:id, :org, :project, :script, :diff, :before_version, :after_version, "
            ":before_element, :after_element, 'added', 'unmatched', 'v1', :created)",
            {
                "org": org_a,
                "project": project_a,
                "script": script_a,
                "diff": diff_a,
                "before_version": before_a,
                "after_version": after_a,
                "before_element": before_element_b,
                "after_element": str(uuid4()),
            },
        ),
        (
            "INSERT INTO clearance_items "
            "(id, org_id, project_id, script_id, version_id, element_id, category, text, "
            "status, predecessor_item_id, predecessor_version_id, lineage_kind, "
            "carried_forward_confirmation_required, created_at) VALUES "
            "(:id, :org, :project, :script, :version, :element, 'brands', 'Brand', "
            "'unresolved', :foreign, :predecessor_version, 'carried_forward', 1, :created)",
            {
                "org": org_b,
                "project": project_b,
                "script": script_b,
                "version": after_b,
                "element": after_element_b,
                "foreign": old_item_a,
                "predecessor_version": before_a,
            },
        ),
        (
            "INSERT INTO clearance_items "
            "(id, org_id, project_id, script_id, version_id, element_id, category, text, "
            "status, predecessor_item_id, predecessor_version_id, lineage_kind, "
            "carried_forward_confirmation_required, created_at) VALUES "
            "(:id, :org, :project, :script, :version, :element, 'brands', 'Brand', "
            "'unresolved', :predecessor, :predecessor_version, 'carried_forward', 1, "
            ":created)",
            {
                "org": org_a,
                "project": project_a,
                "script": script_a,
                "version": after_a,
                "element": after_element_a,
                "predecessor": old_item_a,
                "predecessor_version": before_a,
            },
        ),
        (
            "INSERT INTO clearance_items "
            "(id, org_id, project_id, script_id, version_id, element_id, category, text, "
            "status, predecessor_item_id, predecessor_version_id, lineage_kind, "
            "carried_forward_confirmation_required, created_at) VALUES "
            "(:id, :org, :project, :script, :version, :element, 'brands', 'Brand', "
            "'unresolved', :id, :predecessor_version, 'carried_forward', 1, :created)",
            {
                "org": org_a,
                "project": project_a,
                "script": script_a,
                "version": after_a,
                "element": after_element_a,
                "predecessor_version": before_a,
            },
        ),
        (
            "INSERT INTO clearance_items "
            "(id, org_id, project_id, script_id, version_id, element_id, category, text, "
            "status, predecessor_item_id, predecessor_version_id, lineage_kind, "
            "carried_forward_confirmation_required, created_at) VALUES "
            "(:id, :org, :project, :script, :version, :element, 'brands', 'Brand', "
            "'unresolved', :predecessor, :predecessor_version, 'carried_forward', 1, "
            ":created)",
            {
                "org": org_a,
                "project": project_a,
                "script": script_a,
                "version": before_a,
                "element": before_element_a,
                "predecessor": old_item_a,
                "predecessor_version": before_a,
            },
        ),
        (
            "INSERT INTO evidence_carry_forwards "
            "(id, org_id, project_id, new_item_id, source_item_id, original_claim_id, "
            "snapshot_id, run_id, query_id, provider_attempt_id, created_at) VALUES "
            "(:id, :org, :project, :new_item, :source_item, :claim, :snapshot, :run, "
            ":query, :attempt, :created)",
            {
                "org": org_a,
                "project": project_a,
                "new_item": old_item_a,
                "source_item": old_item_a,
                "claim": claim_a,
                "snapshot": snapshot_a,
                "run": run_a,
                "query": query_a,
                "attempt": attempt_a,
            },
        ),
        (
            "INSERT INTO evidence_carry_forwards "
            "(id, org_id, project_id, new_item_id, source_item_id, original_claim_id, "
            "snapshot_id, run_id, query_id, provider_attempt_id, created_at) VALUES "
            "(:id, :org, :project, :new_item, :source_item, :claim, :snapshot, :run, "
            ":query, :attempt, :created)",
            {
                "org": org_b,
                "project": project_b,
                "new_item": item_b,
                "source_item": old_item_a,
                "claim": claim_a,
                "snapshot": snapshot_a,
                "run": run_a,
                "query": query_a,
                "attempt": attempt_a,
            },
        ),
        (
            "INSERT INTO evidence_carry_forwards "
            "(id, org_id, project_id, new_item_id, source_item_id, original_claim_id, "
            "snapshot_id, run_id, query_id, provider_attempt_id, created_at) VALUES "
            "(:id, :org, :project, :new_item, :source_item, :claim, :snapshot, :run, "
            ":query, :attempt, :created)",
            {
                "org": org_a,
                "project": project_a,
                "new_item": new_item_a,
                "source_item": old_item_a,
                "claim": claim_a,
                "snapshot": snapshot_a,
                "run": run_a,
                "query": query_a,
                "attempt": attempt_a,
            },
        ),
        (
            "INSERT INTO selective_rescan_checkpoints "
            "(id, org_id, project_id, job_id, stage, item_id, status, "
            "attempt_number, created_at, completed_at) VALUES "
            "(:id, :org, :project, :job, 'carrying_evidence', :item, "
            "'succeeded', 2, :created, :created)",
            {
                "org": org_a,
                "project": project_a,
                "job": job_a,
                "item": new_item_a,
            },
        ),
        (
            "INSERT INTO selective_rescan_checkpoints "
            "(id, org_id, project_id, job_id, stage, item_id, status, "
            "attempt_number, created_at) VALUES "
            "(:id, :org, :project, :job, 'detecting_affected_passages', :item, "
            "'running', 1, :created)",
            {
                "org": org_b,
                "project": project_b,
                "job": job_a,
                "item": item_b,
            },
        ),
    )
    for statement, values in invalid_statements:
        parameters = {
            "id": str(uuid4()),
            "hash": uuid4().hex,
            "created": now,
            **values,
        }
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(sa.text(statement), parameters)

    engine.dispose()


def test_0035_refuses_duplicate_historical_diffs_before_mutation(tmp_path: Path) -> None:
    database_path = tmp_path / "duplicate-historical-diffs.db"
    engine = _migrate(database_path, "0034_report_artifacts")
    now = datetime.now(UTC)
    org_id, project_id, script_id, before_id, after_id = (str(uuid4()) for _ in range(5))
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO organizations (id, name, slug, created_at) "
                "VALUES (:id, 'Duplicate Diff Org', 'duplicate-diff-org', :created)"
            ),
            {"id": org_id, "created": now},
        )
        connection.execute(
            sa.text(
                "INSERT INTO projects (id, org_id, title, created_at) "
                "VALUES (:id, :org, 'Duplicate Diff', :created)"
            ),
            {"id": project_id, "org": org_id, "created": now},
        )
        connection.execute(
            sa.text(
                "INSERT INTO scripts (id, org_id, project_id, title, created_at) "
                "VALUES (:id, :org, :project, 'Duplicate Diff', :created)"
            ),
            {
                "id": script_id,
                "org": org_id,
                "project": project_id,
                "created": now,
            },
        )
        for version_id, ordinal in ((before_id, 1), (after_id, 2)):
            connection.execute(
                sa.text(
                    "INSERT INTO script_versions "
                    "(id, script_id, org_id, project_id, ordinal, source_hash, "
                    "parser_version, created_at) VALUES "
                    "(:id, :script, :org, :project, :ordinal, :hash, 'legacy', :created)"
                ),
                {
                    "id": version_id,
                    "script": script_id,
                    "org": org_id,
                    "project": project_id,
                    "ordinal": ordinal,
                    "hash": version_id.replace("-", ""),
                    "created": now,
                },
            )
        for diff_id in (str(uuid4()), str(uuid4())):
            connection.execute(
                sa.text(
                    "INSERT INTO script_diffs "
                    "(id, org_id, project_id, before_version_id, after_version_id, "
                    "diff_payload, created_at) VALUES "
                    "(:id, :org, :project, :before, :after, '{}', :created)"
                ),
                {
                    "id": diff_id,
                    "org": org_id,
                    "project": project_id,
                    "before": before_id,
                    "after": after_id,
                    "created": now,
                },
            )
    engine.dispose()

    with pytest.raises(RuntimeError, match="duplicate adjacent script_diffs"):
        command.upgrade(_config(database_path), "head")

    engine = _engine(database_path)
    inspector = sa.inspect(engine)
    with engine.connect() as connection:
        revision = connection.execute(
            sa.text("SELECT version_num FROM alembic_version")
        ).scalar_one()
        diff_count = connection.execute(sa.text("SELECT count(*) FROM script_diffs")).scalar_one()
    assert revision == "0034_report_artifacts"
    assert diff_count == 2
    assert "predecessor_version_id" not in {
        column["name"] for column in inspector.get_columns("script_versions")
    }
    assert "script_id" not in {column["name"] for column in inspector.get_columns("script_diffs")}
    engine.dispose()


def _seed_scoped_revision_fixture(engine: sa.Engine) -> dict[str, str]:
    now = datetime.now(UTC)
    names = (
        "org_a",
        "project_a",
        "script_a",
        "before_a",
        "after_a",
        "before_element_a",
        "after_element_a",
        "org_b",
        "project_b",
        "script_b",
        "before_b",
        "after_b",
        "before_element_b",
        "after_element_b",
        "actor_a",
        "actor_b",
        "item_a",
        "item_b",
        "job_a",
        "job_b",
    )
    values: dict[str, str] = dict(zip(names, (str(uuid4()) for _ in names), strict=True))

    with engine.begin() as connection:
        for suffix in ("a", "b"):
            _seed_revision_project(
                connection,
                org_id=values[f"org_{suffix}"],
                project_id=values[f"project_{suffix}"],
                script_id=values[f"script_{suffix}"],
                before_version_id=values[f"before_{suffix}"],
                after_version_id=values[f"after_{suffix}"],
                before_element_id=values[f"before_element_{suffix}"],
                after_element_id=values[f"after_element_{suffix}"],
                now=now,
                slug=f"scoped-revision-{suffix}",
            )
            connection.execute(
                sa.text("INSERT INTO users (id, email, created_at) VALUES (:id, :email, :created)"),
                {
                    "id": values[f"actor_{suffix}"],
                    "email": f"actor-{suffix}@example.test",
                    "created": now,
                },
            )
            connection.execute(
                sa.text(
                    "INSERT INTO memberships "
                    "(id, org_id, user_id, role, status, created_at) VALUES "
                    "(:id, :org, :user, 'owner', 'active', :created)"
                ),
                {
                    "id": str(uuid4()),
                    "org": values[f"org_{suffix}"],
                    "user": values[f"actor_{suffix}"],
                    "created": now,
                },
            )
            connection.execute(
                sa.text(
                    "INSERT INTO clearance_items "
                    "(id, org_id, project_id, script_id, version_id, element_id, category, "
                    "text, status, created_at) VALUES "
                    "(:id, :org, :project, :script, :version, :element, 'brands', "
                    "'Scoped item', 'unresolved', :created)"
                ),
                {
                    "id": values[f"item_{suffix}"],
                    "org": values[f"org_{suffix}"],
                    "project": values[f"project_{suffix}"],
                    "script": values[f"script_{suffix}"],
                    "version": values[f"after_{suffix}"],
                    "element": values[f"after_element_{suffix}"],
                    "created": now,
                },
            )
            connection.execute(
                sa.text(
                    "INSERT INTO jobs "
                    "(id, org_id, project_id, job_type, status, idempotency_key, payload, "
                    "progress, stage, correlation_id, attempt_count, available_at, "
                    "created_at, updated_at) VALUES "
                    "(:id, :org, :project, 'selective_rescan', 'running', :key, '{}', 0, "
                    "'materializing_lineage', :id, 1, :created, :created, :created)"
                ),
                {
                    "id": values[f"job_{suffix}"],
                    "org": values[f"org_{suffix}"],
                    "project": values[f"project_{suffix}"],
                    "key": f"selective-rescan-{suffix}",
                    "created": now,
                },
            )
    values["created"] = now.isoformat()
    return values


def test_script_version_accepts_committing_actor_from_same_org(tmp_path: Path) -> None:
    engine = _migrate(tmp_path / "same-org-committing-actor.db")
    fixture = _seed_scoped_revision_fixture(engine)

    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "UPDATE script_versions SET committed_by_actor_id = :actor WHERE id = :version"
            ),
            {"actor": fixture["actor_a"], "version": fixture["after_a"]},
        )

    engine.dispose()


def test_script_version_rejects_committing_actor_from_another_org(tmp_path: Path) -> None:
    engine = _migrate(tmp_path / "cross-org-committing-actor.db")
    fixture = _seed_scoped_revision_fixture(engine)

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.text(
                "UPDATE script_versions SET committed_by_actor_id = :actor WHERE id = :version"
            ),
            {"actor": fixture["actor_b"], "version": fixture["after_a"]},
        )

    engine.dispose()


def _insert_checkpoint(
    connection: sa.Connection,
    *,
    fixture: dict[str, str],
    stage: str,
    status: str = "pending",
    script_version_id: str | None = None,
    item_id: str | None = None,
    completed: bool = False,
    safe_error: str | None = None,
) -> None:
    connection.execute(
        sa.text(
            "INSERT INTO selective_rescan_checkpoints "
            "(id, org_id, project_id, job_id, stage, script_version_id, item_id, status, "
            "result, safe_error, attempt_number, created_at, completed_at) VALUES "
            "(:id, :org, :project, :job, :stage, :version, :item, :status, NULL, "
            ":safe_error, 1, :created, :completed)"
        ),
        {
            "id": str(uuid4()),
            "org": fixture["org_a"],
            "project": fixture["project_a"],
            "job": fixture["job_a"],
            "stage": stage,
            "version": script_version_id,
            "item": item_id,
            "status": status,
            "safe_error": safe_error,
            "created": fixture["created"],
            "completed": fixture["created"] if completed else None,
        },
    )


@pytest.mark.parametrize(
    "stage",
    [
        "queued",
        "materializing_lineage",
        "carrying_evidence",
        "detecting_affected_passages",
        "researching_affected_items",
        "awaiting_confirmation",
        "completed",
    ],
)
def test_selective_rescan_checkpoint_accepts_approved_stage(
    tmp_path: Path,
    stage: str,
) -> None:
    engine = _migrate(tmp_path / f"approved-checkpoint-stage-{stage}.db")
    fixture = _seed_scoped_revision_fixture(engine)

    with engine.begin() as connection:
        _insert_checkpoint(connection, fixture=fixture, stage=stage)

    engine.dispose()


def test_selective_rescan_checkpoint_rejects_unknown_stage(tmp_path: Path) -> None:
    engine = _migrate(tmp_path / "unknown-checkpoint-stage.db")
    fixture = _seed_scoped_revision_fixture(engine)

    with pytest.raises(IntegrityError), engine.begin() as connection:
        _insert_checkpoint(connection, fixture=fixture, stage="arbitrary_stage")

    engine.dispose()


@pytest.mark.parametrize(
    ("status", "completed", "safe_error"),
    [
        ("pending", False, None),
        ("running", False, None),
        ("succeeded", True, None),
        ("failed", True, "{}"),
    ],
)
def test_selective_rescan_checkpoint_accepts_approved_status(
    tmp_path: Path,
    status: str,
    completed: bool,
    safe_error: str | None,
) -> None:
    engine = _migrate(tmp_path / f"approved-checkpoint-status-{status}.db")
    fixture = _seed_scoped_revision_fixture(engine)

    with engine.begin() as connection:
        _insert_checkpoint(
            connection,
            fixture=fixture,
            stage="materializing_lineage",
            status=status,
            completed=completed,
            safe_error=safe_error,
        )

    engine.dispose()


def test_selective_rescan_checkpoint_rejects_unknown_status(tmp_path: Path) -> None:
    engine = _migrate(tmp_path / "unknown-checkpoint-status.db")
    fixture = _seed_scoped_revision_fixture(engine)

    with pytest.raises(IntegrityError), engine.begin() as connection:
        _insert_checkpoint(
            connection,
            fixture=fixture,
            stage="materializing_lineage",
            status="unknown",
        )

    engine.dispose()


@pytest.mark.parametrize(
    ("target_column", "foreign_key"),
    [
        ("script_version_id", "after_b"),
        ("item_id", "item_b"),
    ],
)
def test_selective_rescan_checkpoint_rejects_cross_org_target(
    tmp_path: Path,
    target_column: str,
    foreign_key: str,
) -> None:
    engine = _migrate(tmp_path / f"cross-org-checkpoint-{target_column}.db")
    fixture = _seed_scoped_revision_fixture(engine)
    script_version_id = fixture[foreign_key] if target_column == "script_version_id" else None
    item_id = fixture[foreign_key] if target_column == "item_id" else None

    with pytest.raises(IntegrityError), engine.begin() as connection:
        _insert_checkpoint(
            connection,
            fixture=fixture,
            stage="materializing_lineage",
            script_version_id=script_version_id,
            item_id=item_id,
        )

    engine.dispose()


@pytest.mark.parametrize("target_column", ["script_version_id", "item_id"])
def test_selective_rescan_checkpoint_rejects_cross_project_target_in_same_org(
    tmp_path: Path,
    target_column: str,
) -> None:
    engine = _migrate(tmp_path / f"cross-project-checkpoint-{target_column}.db")
    fixture = _seed_scoped_revision_fixture(engine)
    project_id, script_id, version_id, element_id, item_id = (str(uuid4()) for _ in range(5))

    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO projects (id, org_id, title, created_at) "
                "VALUES (:id, :org, 'Peer project', :created)"
            ),
            {
                "id": project_id,
                "org": fixture["org_a"],
                "created": fixture["created"],
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO scripts (id, org_id, project_id, title, created_at) "
                "VALUES (:id, :org, :project, 'Peer script', :created)"
            ),
            {
                "id": script_id,
                "org": fixture["org_a"],
                "project": project_id,
                "created": fixture["created"],
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
                "org": fixture["org_a"],
                "project": project_id,
                "hash": version_id.replace("-", ""),
                "created": fixture["created"],
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO script_elements "
                "(id, version_id, ordinal, element_type, text) "
                "VALUES (:id, :version, 1, 'action', 'Peer body')"
            ),
            {"id": element_id, "version": version_id},
        )
        connection.execute(
            sa.text(
                "INSERT INTO clearance_items "
                "(id, org_id, project_id, script_id, version_id, element_id, category, "
                "text, status, created_at) VALUES "
                "(:id, :org, :project, :script, :version, :element, 'brands', "
                "'Peer item', 'unresolved', :created)"
            ),
            {
                "id": item_id,
                "org": fixture["org_a"],
                "project": project_id,
                "script": script_id,
                "version": version_id,
                "element": element_id,
                "created": fixture["created"],
            },
        )

    with pytest.raises(IntegrityError), engine.begin() as connection:
        _insert_checkpoint(
            connection,
            fixture=fixture,
            stage="materializing_lineage",
            script_version_id=version_id if target_column == "script_version_id" else None,
            item_id=item_id if target_column == "item_id" else None,
        )

    engine.dispose()


@pytest.mark.parametrize(
    ("script_version_key", "item_key"),
    [("after_a", None), (None, "item_a")],
)
def test_selective_rescan_checkpoint_accepts_same_project_typed_target(
    tmp_path: Path,
    script_version_key: str | None,
    item_key: str | None,
) -> None:
    target_name = script_version_key or item_key
    engine = _migrate(tmp_path / f"same-project-checkpoint-{target_name}.db")
    fixture = _seed_scoped_revision_fixture(engine)

    with engine.begin() as connection:
        _insert_checkpoint(
            connection,
            fixture=fixture,
            stage="materializing_lineage",
            script_version_id=fixture[script_version_key] if script_version_key else None,
            item_id=fixture[item_key] if item_key else None,
        )

    engine.dispose()


@pytest.mark.parametrize("target_kind", ["job", "script_version", "item"])
def test_selective_rescan_checkpoint_replay_identity_is_typed_and_deterministic(
    tmp_path: Path,
    target_kind: str,
) -> None:
    engine = _migrate(tmp_path / f"checkpoint-replay-{target_kind}.db")
    fixture = _seed_scoped_revision_fixture(engine)
    script_version_id = fixture["after_a"] if target_kind == "script_version" else None
    item_id = fixture["item_a"] if target_kind == "item" else None

    with engine.begin() as connection:
        _insert_checkpoint(
            connection,
            fixture=fixture,
            stage="materializing_lineage",
            script_version_id=script_version_id,
            item_id=item_id,
        )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        _insert_checkpoint(
            connection,
            fixture=fixture,
            stage="materializing_lineage",
            script_version_id=script_version_id,
            item_id=item_id,
        )

    engine.dispose()


def _seed_element_lineage_fixture(engine: sa.Engine) -> dict[str, str]:
    now = datetime.now(UTC)
    names = (
        "org",
        "project",
        "script",
        "before_version",
        "after_version",
        "before_element",
        "after_element",
        "diff",
    )
    values: dict[str, str] = dict(zip(names, (str(uuid4()) for _ in names), strict=True))
    with engine.begin() as connection:
        _seed_revision_project(
            connection,
            org_id=values["org"],
            project_id=values["project"],
            script_id=values["script"],
            before_version_id=values["before_version"],
            after_version_id=values["after_version"],
            before_element_id=values["before_element"],
            after_element_id=values["after_element"],
            now=now,
            slug=f"lineage-{values['diff']}",
        )
        connection.execute(
            sa.text(
                "INSERT INTO script_diffs "
                "(id, org_id, project_id, script_id, before_version_id, after_version_id, "
                "before_ordinal, after_ordinal, algorithm_version, summary_payload, "
                "diff_payload, created_at) VALUES "
                "(:id, :org, :project, :script, :before, :after, 1, 2, "
                "'element-lineage-v1', '{}', '{}', :created)"
            ),
            {
                "id": values["diff"],
                "org": values["org"],
                "project": values["project"],
                "script": values["script"],
                "before": values["before_version"],
                "after": values["after_version"],
                "created": now,
            },
        )
    values["created"] = now.isoformat()
    return values


def _insert_element_lineage(
    connection: sa.Connection,
    *,
    fixture: dict[str, str],
    change_kind: str,
    confidence: str,
    before_element_id: str | None,
    after_element_id: str | None,
) -> None:
    connection.execute(
        sa.text(
            "INSERT INTO script_element_lineage "
            "(id, org_id, project_id, script_id, diff_id, before_version_id, "
            "after_version_id, before_element_id, after_element_id, change_kind, "
            "confidence, algorithm_version, created_at) VALUES "
            "(:id, :org, :project, :script, :diff, :before_version, :after_version, "
            ":before_element, :after_element, :change_kind, :confidence, "
            "'element-lineage-v1', :created)"
        ),
        {
            "id": str(uuid4()),
            "org": fixture["org"],
            "project": fixture["project"],
            "script": fixture["script"],
            "diff": fixture["diff"],
            "before_version": fixture["before_version"],
            "after_version": fixture["after_version"],
            "before_element": before_element_id,
            "after_element": after_element_id,
            "change_kind": change_kind,
            "confidence": confidence,
            "created": fixture["created"],
        },
    )


@pytest.mark.parametrize(
    ("change_kind", "confidence", "has_before", "has_after"),
    [
        ("unchanged", "exact", True, True),
        ("moved", "contextual", True, True),
        ("modified", "similar", True, True),
        ("added", "unmatched", False, True),
        ("removed", "unmatched", True, False),
    ],
)
def test_script_element_lineage_accepts_each_kind_and_confidence(
    tmp_path: Path,
    change_kind: str,
    confidence: str,
    has_before: bool,
    has_after: bool,
) -> None:
    engine = _migrate(tmp_path / f"valid-lineage-{change_kind}-{confidence}.db")
    fixture = _seed_element_lineage_fixture(engine)

    with engine.begin() as connection:
        _insert_element_lineage(
            connection,
            fixture=fixture,
            change_kind=change_kind,
            confidence=confidence,
            before_element_id=fixture["before_element"] if has_before else None,
            after_element_id=fixture["after_element"] if has_after else None,
        )

    engine.dispose()


@pytest.mark.parametrize(
    ("change_kind", "confidence"),
    [("unknown", "exact"), ("unchanged", "unknown")],
)
def test_script_element_lineage_rejects_unknown_kind_or_confidence(
    tmp_path: Path,
    change_kind: str,
    confidence: str,
) -> None:
    engine = _migrate(tmp_path / f"unknown-lineage-{change_kind}-{confidence}.db")
    fixture = _seed_element_lineage_fixture(engine)

    with pytest.raises(IntegrityError), engine.begin() as connection:
        _insert_element_lineage(
            connection,
            fixture=fixture,
            change_kind=change_kind,
            confidence=confidence,
            before_element_id=fixture["before_element"],
            after_element_id=fixture["after_element"],
        )

    engine.dispose()


@pytest.mark.parametrize(
    ("case_name", "change_kind", "confidence", "has_before", "has_after"),
    [
        ("added-has-before", "added", "unmatched", True, True),
        ("added-misses-after", "added", "unmatched", False, False),
        ("removed-misses-before", "removed", "unmatched", False, False),
        ("removed-has-after", "removed", "unmatched", True, True),
        ("unchanged-misses-before", "unchanged", "exact", False, True),
        ("unchanged-misses-after", "unchanged", "exact", True, False),
        ("moved-misses-before", "moved", "contextual", False, True),
        ("moved-misses-after", "moved", "contextual", True, False),
        ("modified-misses-before", "modified", "similar", False, True),
        ("modified-misses-after", "modified", "similar", True, False),
    ],
)
def test_script_element_lineage_rejects_each_invalid_endpoint_shape(
    tmp_path: Path,
    case_name: str,
    change_kind: str,
    confidence: str,
    has_before: bool,
    has_after: bool,
) -> None:
    engine = _migrate(tmp_path / f"invalid-lineage-endpoints-{case_name}.db")
    fixture = _seed_element_lineage_fixture(engine)

    with pytest.raises(IntegrityError), engine.begin() as connection:
        _insert_element_lineage(
            connection,
            fixture=fixture,
            change_kind=change_kind,
            confidence=confidence,
            before_element_id=fixture["before_element"] if has_before else None,
            after_element_id=fixture["after_element"] if has_after else None,
        )

    engine.dispose()

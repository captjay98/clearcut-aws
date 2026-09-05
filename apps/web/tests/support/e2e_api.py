"""Playwright-only API composition with deterministic, non-paid model adapters."""

from __future__ import annotations

import asyncio
import hashlib
import os
import socket
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
import uuid6
from clearcut.database import session_scope
from clearcut.detection.adapters.hermetic_runtime import HermeticDetectionRuntime
from clearcut.detection.adapters.sql_candidate_repository import SqlCandidateRepository
from clearcut.detection.application.run_detection_job import RunDetectionJobService
from clearcut.detection.runtime_provider import get_detection_runtime
from clearcut.evaluation.adapters.hermetic_judge import HermeticJudgeAdapter
from clearcut.evaluation.application.evaluate import EvaluationService
from clearcut.identity.delivery.http import verify_csrf_origin
from clearcut.identity.delivery.scope import get_request_scope
from clearcut.main import app
from clearcut.operations.application.local_dispatcher import LocalJobDispatcher
from clearcut.operations.application.run_job import RunJobService
from clearcut.organizations.domain.capabilities import has_capability
from clearcut.scripts.domain.elements import ScriptElement
from fastapi import HTTPException, Request, status


class PlaywrightDetectionRuntime(HermeticDetectionRuntime):
    """Deterministic adapter with one explicit marker used to test cancellation."""

    async def detect_element(self, element: ScriptElement):
        if "E2E HOLD" in element.text:
            await asyncio.sleep(8)
        return await super().detect_element(element)


class PlaywrightCandidateRepository(SqlCandidateRepository):
    """Use explicit test bindings without weakening production policy lookup."""

    async def load_active_judge_configuration(self, *, org_id: UUID) -> tuple[str, str]:
        del org_id
        return "playwright-policy-v1", "playwright-prompt-v1"


detection_runtime = PlaywrightDetectionRuntime()
candidate_repository = PlaywrightCandidateRepository()
evaluation_service = EvaluationService(
    judge=HermeticJudgeAdapter(),
    repository=app.state.evaluation_repository,
)
run_detection_job = RunDetectionJobService(
    repository=candidate_repository,
    job_repository=app.state.job_repository,
    runtime=detection_runtime,
    evaluation=evaluation_service,
)
job_runner = RunJobService(
    repository=app.state.job_repository,
    processors={
        "detection": run_detection_job,
        "research": app.state.run_research_job,
    },
    lease_owner=f"playwright:{socket.gethostname()}:{os.getpid()}",
)
job_dispatcher = LocalJobDispatcher(
    runner=job_runner,
    mode="local",
    worker_count=1,
)

if app.state.job_dispatcher.mode == "local":
    app.dependency_overrides[get_detection_runtime] = lambda: detection_runtime
    app.state.candidate_repository = candidate_repository
    app.state.run_detection_job = run_detection_job
    app.state.job_runner = job_runner
    app.state.job_dispatcher = job_dispatcher


@app.post(
    "/e2e/organizations/{org_id}/projects/{project_id}/evidence-fixture",
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def create_evidence_fixture(
    org_id: UUID,
    project_id: UUID,
    request: Request,
) -> dict[str, object]:
    """Create deterministic evidence records for browser tests without provider calls."""
    verify_csrf_origin(request)
    scope = await get_request_scope(
        request,
        org_id=str(org_id),
        project_id=str(project_id),
    )
    if scope.org_id != org_id or scope.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found in organization",
        )
    if not has_capability(scope.role or "", "project:update"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Project update capability is required",
        )

    script_id, version_id, element_id = (uuid6.uuid7() for _ in range(3))
    cited_item_id, zero_evidence_item_id = (uuid6.uuid7() for _ in range(2))
    research_run_id, query_id = (uuid6.uuid7() for _ in range(2))
    search_attempt_id, extract_attempt_id = (uuid6.uuid7() for _ in range(2))
    authorization_id, extract_target_id = (uuid6.uuid7() for _ in range(2))
    source_snapshot_id, evidence_claim_id = (uuid6.uuid7() for _ in range(2))
    now = datetime.now(UTC)

    script_text = "A Vega Camera rests beside an unverified Northstar Drone prototype."
    source_hash = hashlib.sha256(script_text.encode()).hexdigest()
    source_url = "https://example.com/e2e-fixtures/vega-camera"
    source_title = "Deterministic Vega Camera fixture record"
    source_publisher = "ClearCut E2E Fixture Publisher"
    source_excerpt = (
        "This deterministic fixture record supplies cited context for browser testing only."
    )
    snapshot_hash = hashlib.sha256(
        f"{source_url}|{source_title}|{source_excerpt}".encode()
    ).hexdigest()

    values = {
        "org": str(org_id),
        "project": str(project_id),
        "script": str(script_id),
        "version": str(version_id),
        "element": str(element_id),
        "cited_item": str(cited_item_id),
        "zero_item": str(zero_evidence_item_id),
        "run": str(research_run_id),
        "query": str(query_id),
        "search_attempt": str(search_attempt_id),
        "extract_attempt": str(extract_attempt_id),
        "authorization": str(authorization_id),
        "extract_target": str(extract_target_id),
        "snapshot": str(source_snapshot_id),
        "claim": str(evidence_claim_id),
        "now": now,
        "source_hash": source_hash,
        "source_url": source_url,
        "source_title": source_title,
        "source_publisher": source_publisher,
        "source_excerpt": source_excerpt,
        "snapshot_hash": snapshot_hash,
    }

    async with session_scope() as session:
        existing = await session.execute(
            sa.text("SELECT id FROM scripts WHERE org_id = :org AND project_id = :project LIMIT 1"),
            values,
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Evidence fixture already exists for project",
            )

        await session.execute(
            sa.text(
                "INSERT INTO scripts "
                "(id, org_id, project_id, title, current_slot, created_at) VALUES "
                "(:script, :org, :project, 'Task 11 Evidence Fixture', 'current', :now)"
            ),
            values,
        )
        await session.execute(
            sa.text(
                "INSERT INTO script_versions "
                "(id, script_id, org_id, project_id, ordinal, source_hash, "
                "parser_version, created_at) VALUES "
                "(:version, :script, :org, :project, 1, :source_hash, "
                "'e2e-fixture-v1', :now)"
            ),
            values,
        )
        await session.execute(
            sa.text(
                "INSERT INTO script_elements "
                "(id, version_id, ordinal, element_type, text, scene_number, page_number) "
                "VALUES (:element, :version, 1, 'action', "
                "'A Vega Camera rests beside an unverified Northstar Drone prototype.', 7, 11)"
            ),
            values,
        )
        await session.execute(
            sa.text(
                "INSERT INTO clearance_items "
                "(id, org_id, project_id, script_id, version_id, element_id, category, text, "
                "status, workflow_status, research_status, disposition_status, version, "
                "created_at) VALUES "
                "(:cited_item, :org, :project, :script, :version, :element, "
                "'products_and_trademarks', 'Vega Camera', 'unresolved', 'open', "
                "'completed', 'undisposed', 1, :now), "
                "(:zero_item, :org, :project, :script, :version, :element, "
                "'products_and_trademarks', 'Northstar Drone', 'unresolved', 'open', "
                "'not_started', 'undisposed', 1, :now)"
            ),
            values,
        )
        await session.execute(
            sa.text(
                "INSERT INTO research_runs "
                "(id, org_id, project_id, item_id, version_id, status, objective, "
                "created_at, completed_at) VALUES "
                "(:run, :org, :project, :cited_item, :version, 'succeeded', "
                "'Create deterministic cited browser-test context without provider access.', "
                ":now, :now)"
            ),
            values,
        )
        await session.execute(
            sa.text(
                "INSERT INTO research_queries "
                "(id, run_id, org_id, project_id, item_id, version_id, query, ordinal, "
                "created_at) VALUES "
                "(:query, :run, :org, :project, :cited_item, :version, "
                "'deterministic e2e fixture Vega Camera context', 1, :now)"
            ),
            values,
        )
        await session.execute(
            sa.text(
                "INSERT INTO provider_attempts "
                "(id, run_id, org_id, project_id, item_id, query_id, operation_kind, status, "
                "receipt_id, provider_session_id, duration_ms, authorizing_search_attempt_id, "
                "authorizing_operation_kind, created_at, completed_at) VALUES "
                "(:search_attempt, :run, :org, :project, :cited_item, :query, 'search', "
                "'succeeded', 'e2e-fixture-not-a-provider-receipt', "
                "'e2e-fixture-no-provider-session', 0, :search_attempt, 'search', :now, :now)"
            ),
            values,
        )
        await session.execute(
            sa.text(
                "INSERT INTO search_result_authorizations "
                "(id, org_id, project_id, item_id, run_id, query_id, search_attempt_id, "
                "search_operation_kind, ordinal, url, canonical_url, title, publisher, "
                "excerpt, created_at) VALUES "
                "(:authorization, :org, :project, :cited_item, :run, :query, "
                ":search_attempt, 'search', 1, :source_url, :source_url, :source_title, "
                ":source_publisher, :source_excerpt, :now)"
            ),
            values,
        )
        await session.execute(
            sa.text(
                "INSERT INTO provider_attempts "
                "(id, run_id, org_id, project_id, item_id, query_id, operation_kind, status, "
                "receipt_id, provider_session_id, duration_ms, authorizing_search_attempt_id, "
                "authorizing_operation_kind, created_at, completed_at) VALUES "
                "(:extract_attempt, :run, :org, :project, :cited_item, :query, 'extract', "
                "'succeeded', 'e2e-fixture-not-a-provider-receipt', "
                "'e2e-fixture-no-provider-session', 0, :search_attempt, 'search', :now, :now)"
            ),
            values,
        )
        await session.execute(
            sa.text(
                "INSERT INTO extract_target_authorizations "
                "(id, org_id, project_id, item_id, run_id, query_id, extract_attempt_id, "
                "extract_operation_kind, authorization_id, authorizing_search_attempt_id, "
                "canonical_url, ordinal, created_at) VALUES "
                "(:extract_target, :org, :project, :cited_item, :run, :query, "
                ":extract_attempt, 'extract', :authorization, :search_attempt, :source_url, "
                "1, :now)"
            ),
            values,
        )
        await session.execute(
            sa.text(
                "INSERT INTO source_snapshots "
                "(id, org_id, project_id, item_id, run_id, url, title, publisher, excerpt, "
                "origin, sha256_hash, retrieved_at, query_id, provider_attempt_id, "
                "authorization_id, authorizing_search_attempt_id) VALUES "
                "(:snapshot, :org, :project, :cited_item, :run, :source_url, :source_title, "
                ":source_publisher, :source_excerpt, 'extract', :snapshot_hash, :now, :query, "
                ":extract_attempt, :authorization, :search_attempt)"
            ),
            values,
        )
        await session.execute(
            sa.text(
                "INSERT INTO evidence_claims "
                "(id, org_id, project_id, item_id, snapshot_id, stance, authority_tier, "
                "claim_text, provenance_excerpt, run_id, query_id, provider_attempt_id, "
                "created_at) VALUES "
                "(:claim, :org, :project, :cited_item, :snapshot, 'context', "
                "'secondary_informal', :source_excerpt, :source_excerpt, :run, :query, "
                ":extract_attempt, :now)"
            ),
            values,
        )

    return {
        "data": {
            "orgId": str(org_id),
            "projectId": str(project_id),
            "scriptId": str(script_id),
            "versionId": str(version_id),
            "elementId": str(element_id),
            "citedItemId": str(cited_item_id),
            "zeroEvidenceItemId": str(zero_evidence_item_id),
            "researchRunId": str(research_run_id),
            "sourceSnapshotId": str(source_snapshot_id),
            "evidenceClaimId": str(evidence_claim_id),
        },
        "meta": {"requestId": str(uuid6.uuid7())},
    }

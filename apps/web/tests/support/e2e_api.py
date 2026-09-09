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
from clearcut.detection.adapters.sql_rescan_lineage import SqlItemLineageAdapter
from clearcut.detection.application.run_detection_job import RunDetectionJobService
from clearcut.detection.runtime_provider import get_detection_runtime
from clearcut.evaluation.adapters.hermetic_judge import HermeticJudgeAdapter
from clearcut.evaluation.application.evaluate import EvaluationService
from clearcut.identity.delivery.http import verify_csrf_origin
from clearcut.identity.delivery.scope import get_request_scope
from clearcut.main import (
    _SelectiveRescanChildWorkCoordinator,
    _SelectiveRescanItemLineageCoordinator,
    app,
)
from clearcut.operations.application.local_dispatcher import LocalJobDispatcher
from clearcut.operations.application.run_job import RunJobService
from clearcut.operations.domain.jobs import RunStatus
from clearcut.organizations.domain.capabilities import has_capability
from clearcut.rescan.application.run_rescan_job import RunSelectiveRescanJobService
from clearcut.research.adapters.hermetic_extract import HermeticExtractAdapter
from clearcut.research.adapters.hermetic_search import HermeticSearchAdapter
from clearcut.research.adapters.sql_evidence_lineage import SqlEvidenceLineageAdapter
from clearcut.research.adapters.sql_research_repository import SqlResearchRepository
from clearcut.research.application.run_research_job import RunResearchJobService
from clearcut.research.domain.queries import ResearchPlan
from clearcut.research.ports.planner import (
    PlanningAttemptMetadata,
    PlanningTokenUsage,
    ResearchPlanningRequest,
    ResearchPlanningResult,
    ResearchPlanningSuccess,
)
from clearcut.scripts.adapters.sql_import_repository import SqlImportRepository
from clearcut.scripts.adapters.sql_revision_plan import SqlRevisionPlanAdapter
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


class _HermeticResearchPlanner:
    """A typed ``ResearchPlannerPort`` double that never calls a paid model.

    The production planner resolves a gated Gemini/Flash-Lite model. This double
    returns a deterministic, schema-valid plan so the affected/added items reach
    research through the real research job without any provider or network call.
    It is explicitly an E2E-only identity and is not a Parallel/Gemini receipt.
    """

    @property
    def requested_model(self) -> str:
        return "hermetic-planner-e2e-only"

    async def plan_research(self, request: ResearchPlanningRequest) -> ResearchPlanningResult:
        del request
        return ResearchPlanningSuccess(
            plan=ResearchPlan(
                objective=(
                    "Gather cited public context for the affected clearance item "
                    "using deterministic hermetic sources only."
                ),
                search_queries=[
                    "affected item public records",
                    "affected item authority coverage",
                ],
            ),
            metadata=PlanningAttemptMetadata(
                status="succeeded",
                requested_model=self.requested_model,
                returned_model=self.requested_model,
                response_id="hermetic-planner-e2e-only",
                usage=PlanningTokenUsage(input_tokens=0, output_tokens=0, total_tokens=0),
                latency_ms=0,
                error=None,
            ),
        )


class _AlwaysEnabledProviderGate:
    """A typed provider gate that reports the paid provider available.

    The local/test profile disables paid providers, so the production start
    route returns 503 before enqueuing a durable rescan job. Swapping this gate
    onto the mounted start service lets the governed start path run to a durable
    queued job. This is safe precisely because the child detection/research
    processors composed below are hermetic doubles: the provider I/O boundary
    is replaced entirely, so "enabled" never translates into a real network,
    Parallel, Gemini, or cloud call.
    """

    def is_enabled(self, provider: str) -> bool:
        del provider
        return True


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

# Hermetic research: a typed fake planner plus the in-repo deterministic
# Search/Extract doubles. This replaces the production provider-gated research
# job so that every research child triggered by the rescan reaches the real
# research job logic without any paid Parallel/Gemini call.
research_planner = _HermeticResearchPlanner()
research_search = HermeticSearchAdapter()
research_extract = HermeticExtractAdapter()
run_research_job = RunResearchJobService(
    repository=SqlResearchRepository(),
    planner=research_planner,
    search=research_search,
    extract=research_extract,
    evaluation=evaluation_service,
)

# Hermetic selective rescan: mirror the production composition exactly, but pass
# the HERMETIC detection processor into the child-work coordinator. The
# coordinator runs an inline detection job for added passages, and enqueues
# durable detection/research child jobs for affected items. Both the inline run
# (via detection_processor) and the queued children (via job_runner below) must
# resolve to hermetic doubles for the whole chain to be provider-free.
_import_repository = SqlImportRepository()
_item_lineage_adapter = SqlItemLineageAdapter()
rescan_child_work = _SelectiveRescanChildWorkCoordinator(
    item_lineage=_item_lineage_adapter,
    job_repository=app.state.job_repository,
    detection_processor=run_detection_job,
)
run_rescan_job = RunSelectiveRescanJobService(
    revision_plan=SqlRevisionPlanAdapter(_import_repository),
    materialize_items=_SelectiveRescanItemLineageCoordinator(_item_lineage_adapter),
    carry_evidence=SqlEvidenceLineageAdapter(),
    child_work=rescan_child_work,
    repository=app.state.rescan_repository,
    job_repository=app.state.job_repository,
)

job_runner = RunJobService(
    repository=app.state.job_repository,
    processors={
        "detection": run_detection_job,
        "research": run_research_job,
        "selective_rescan": run_rescan_job,
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
    app.state.run_research_job = run_research_job
    app.state.run_rescan_job = run_rescan_job
    app.state.job_runner = job_runner
    app.state.job_dispatcher = job_dispatcher
    # Enable the governed start path without any paid provider. The hermetic
    # child processors above are the real provider-free boundary.
    app.state.start_selective_rescan_service._provider_gate = _AlwaysEnabledProviderGate()


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



@app.post(
    "/e2e/organizations/{org_id}/projects/{project_id}/predecessor-evidence-fixture",
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def create_predecessor_evidence_fixture(
    org_id: UUID,
    project_id: UUID,
    request: Request,
) -> dict[str, object]:
    """Attach cited predecessor evidence + a governed historical decision to a v1 item.

    Browser tests import v1 through the real upload/parse/commit UI, so the
    project's clearance items are freshly detected. This schema-hidden,
    authenticated fixture attaches complete synthetic-but-attributable
    provenance (a Parallel-shaped ``SourceSnapshot`` and one ``EvidenceClaim``
    with URL, retrieval time, attributable excerpt, publisher, stance, and
    query/run identity) plus a prior governed decision to the predecessor
    clearance item that sits on an *unchanged* v1 element. That item therefore
    carries forward through a selective rescan, letting the browser proof assert
    that carried evidence references the ORIGINAL provenance and that the prior
    decision remains historical on the predecessor.

    All identities are explicit E2E-only markers. This is not a Parallel receipt
    or provider session, and it invents NO fallback claim for any zero-evidence
    item: only the single named predecessor item receives a claim.
    """
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

    # The unchanged VERA dialogue line ("Every case leaves a mark...") appears
    # verbatim in both fixture versions, so a clearance item bound to its v1
    # element carries forward through the rescan. It carries no brand, so real
    # detection creates no item there; this fixture is the sole, explicit source
    # of both the carryable predecessor item and its cited evidence.
    carryable_text = "Every case leaves a mark. This one left a scar."

    cited_item_id = uuid6.uuid7()
    run_id, query_id = (uuid6.uuid7() for _ in range(2))
    search_attempt_id, extract_attempt_id = (uuid6.uuid7() for _ in range(2))
    authorization_id, extract_target_id = (uuid6.uuid7() for _ in range(2))
    source_snapshot_id, evidence_claim_id = (uuid6.uuid7() for _ in range(2))
    decision_id = uuid6.uuid7()
    now = datetime.now(UTC)

    source_url = "https://register.example/e2e-fixtures/borrowed-light-predecessor"
    source_title = "Deterministic predecessor evidence fixture record"
    source_publisher = "ClearCut E2E Fixture Authority"
    source_excerpt = (
        "This deterministic fixture record supplies cited predecessor context for "
        "browser testing only; it is not a provider receipt."
    )
    snapshot_hash = hashlib.sha256(
        f"{source_url}|{source_title}|{source_excerpt}".encode()
    ).hexdigest()

    async with session_scope() as session:
        # A selective rescan is a governed action that the production start
        # service refuses unless an active organization policy governs the org
        # (StartSelectiveRescanService step 3 -> POLICY_INACTIVE -> 409). The
        # public registration/org-creation flow the browser drives does not
        # activate a policy, so this hermetic, org-scoped fixture provisions the
        # same active governing configuration the backend E2E test seeds. It is
        # an explicit e2e-only marker, not a promoted production policy, and it
        # is inserted only when the org has none.
        has_active_policy = (
            await session.execute(
                sa.text(
                    "SELECT 1 FROM protected_configurations "
                    "WHERE org_id = :org AND lifecycle = 'active' LIMIT 1"
                ),
                {"org": str(org_id)},
            )
        ).first()
        if has_active_policy is None:
            await session.execute(
                sa.text(
                    "INSERT INTO protected_configurations "
                    "(id, org_id, lifecycle, policy_version, prompt_version, created_at) "
                    "VALUES (:id, :org, 'active', 'e2e-policy-v1', 'e2e-prompt-v1', :now)"
                ),
                {"id": str(uuid6.uuid7()), "org": str(org_id), "now": now},
            )

        # Resolve the committed v1 script + the unchanged element by its verbatim
        # text. Scope every lookup by org + project so no cross-tenant record can
        # be reached.
        version_row = (
            await session.execute(
                sa.text(
                    "SELECT sv.id AS version_id, sv.script_id AS script_id, "
                    "se.id AS element_id "
                    "FROM script_versions sv "
                    "JOIN script_elements se ON se.version_id = sv.id "
                    "WHERE sv.org_id = :org AND sv.project_id = :project "
                    "AND sv.ordinal = 1 AND se.text = :element_text "
                    "ORDER BY se.ordinal LIMIT 1"
                ),
                {
                    "org": str(org_id),
                    "project": str(project_id),
                    "element_text": carryable_text,
                },
            )
        ).mappings().first()
        if version_row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No committed v1 carryable element is available to attach evidence to.",
            )
        version_id = UUID(str(version_row["version_id"]))
        script_id = UUID(str(version_row["script_id"]))
        carryable_element_id = UUID(str(version_row["element_id"]))

        existing_claim = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM clearance_items "
                    "WHERE org_id = :org AND project_id = :project "
                    "AND version_id = :version AND element_id = :element "
                    "AND category = 'products_and_trademarks' AND text = 'Heirloom Watch'"
                ),
                {
                    "org": str(org_id),
                    "project": str(project_id),
                    "version": str(version_id),
                    "element": str(carryable_element_id),
                },
            )
        ).scalar_one()
        if int(existing_claim) > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Predecessor evidence fixture already exists for this project",
            )

        values = {
            "org": str(org_id),
            "project": str(project_id),
            "script": str(script_id),
            "cited_item": str(cited_item_id),
            "version": str(version_id),
            "element": str(carryable_element_id),
            "run": str(run_id),
            "query": str(query_id),
            "search_attempt": str(search_attempt_id),
            "extract_attempt": str(extract_attempt_id),
            "authorization": str(authorization_id),
            "extract_target": str(extract_target_id),
            "snapshot": str(source_snapshot_id),
            "claim": str(evidence_claim_id),
            "decision": str(decision_id),
            "actor": str(scope.user_id),
            "now": now,
            "source_url": source_url,
            "source_title": source_title,
            "source_publisher": source_publisher,
            "source_excerpt": source_excerpt,
            "snapshot_hash": snapshot_hash,
        }

        # A resolved, research-complete predecessor clearance item bound to the
        # unchanged v1 element. It carries forward on rescan.
        await session.execute(
            sa.text(
                "INSERT INTO clearance_items "
                "(id, org_id, project_id, script_id, version_id, element_id, category, text, "
                "status, workflow_status, research_status, disposition_status, version, "
                "created_at) VALUES "
                "(:cited_item, :org, :project, :script, :version, :element, "
                "'products_and_trademarks', 'Heirloom Watch', 'resolved', 'resolved', "
                "'completed', 'approved_as_is', 1, :now)"
            ),
            values,
        )
        await session.execute(
            sa.text(
                "INSERT INTO research_runs "
                "(id, org_id, project_id, item_id, version_id, status, objective, "
                "created_at, completed_at) VALUES "
                "(:run, :org, :project, :cited_item, :version, 'succeeded', "
                "'Create deterministic cited predecessor context without provider access.', "
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
                "'deterministic e2e predecessor Rolex context', 1, :now)"
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
                "(:claim, :org, :project, :cited_item, :snapshot, 'supports', "
                "'primary_official', :source_excerpt, :source_excerpt, :run, :query, "
                ":extract_attempt, :now)"
            ),
            values,
        )
        # A prior governed decision on v1 that must remain historical on the
        # predecessor and must never be copied to the carried-forward item.
        await session.execute(
            sa.text(
                "INSERT INTO governed_decision_records "
                "(id, org_id, project_id, item_id, actor_id, decision_kind, decision_value, "
                "rationale, expected_version, resulting_version, created_at) VALUES "
                "(:decision, :org, :project, :cited_item, :actor, 'evidence', 'accepted', "
                "'Prior clearance decision recorded on version one.', 1, 2, :now)"
            ),
            values,
        )

    return {
        "data": {
            "orgId": str(org_id),
            "projectId": str(project_id),
            "citedItemId": str(cited_item_id),
            "versionId": str(version_id),
            "elementId": str(carryable_element_id),
            "researchRunId": str(run_id),
            "sourceSnapshotId": str(source_snapshot_id),
            "evidenceClaimId": str(evidence_claim_id),
            "decisionId": str(decision_id),
            "sourceUrl": source_url,
            "sourceExcerpt": source_excerpt,
            "retrievedAt": now.isoformat(),
        },
        "meta": {"requestId": str(uuid6.uuid7())},
    }



@app.post(
    "/e2e/organizations/{org_id}/projects/{project_id}/drain-child-jobs",
    include_in_schema=False,
)
async def drain_child_jobs(
    org_id: UUID,
    project_id: UUID,
    request: Request,
) -> dict[str, object]:
    """Run every queued detection/research child job through hermetic doubles.

    The local job composition intentionally never runs a queue-draining worker:
    ``_SelectiveRescanChildWorkCoordinator`` only ENQUEUES durable detection and
    research child jobs, and the periodic local recovery loop recovers only
    expired ``claimed``/``running`` leases — never fresh ``queued`` rows. In the
    hosted target a durable dispatcher (Cloud Tasks) pulls those queued children;
    locally there is no such worker. So after a selective rescan reaches terminal
    success, its enqueued research children remain ``queued`` and affected items
    never reach ``research_status = 'completed'`` on their own.

    This schema-hidden, authenticated, org+project-scoped fixture is the browser
    proof's explicit, deterministic substitute for that hosted worker. It mirrors
    the repository-level drain in
    ``services/api/tests/e2e/test_revision_selective_rescan.py`` exactly: it
    selects every ``detection``/``research`` job row for this tenant in creation
    order and runs each through a ``RunJobService`` wired to the SAME module-level
    hermetic detection/research processors composed above. No paid provider,
    network, or cloud call is ever made — the child processors are the real
    provider-free boundary. It invents no evidence: it only executes the durable
    child jobs the production rescan already enqueued, and returns their typed
    terminal outcomes so the test can assert them honestly.
    """
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

    child_runner = RunJobService(
        repository=app.state.job_repository,
        processors={
            "detection": run_detection_job,
            "research": run_research_job,
        },
        lease_owner=f"playwright-child-drain:{socket.gethostname()}:{os.getpid()}",
    )

    async with session_scope() as session:
        rows = (
            (
                await session.execute(
                    sa.text(
                        "SELECT id, job_type FROM jobs "
                        "WHERE org_id = :org AND project_id = :project "
                        "AND job_type IN ('detection', 'research') "
                        "ORDER BY created_at"
                    ),
                    {"org": str(org_id), "project": str(project_id)},
                )
            )
            .mappings()
            .all()
        )

    outcomes: list[dict[str, object]] = []
    for row in rows:
        record = await child_runner.run(UUID(str(row["id"])), org_id, project_id)
        outcomes.append(
            {
                "jobId": str(row["id"]),
                "jobType": str(row["job_type"]),
                "status": record.status.value
                if isinstance(record.status, RunStatus)
                else str(record.status),
            }
        )

    return {
        "data": {
            "drainedCount": len(outcomes),
            "outcomes": outcomes,
        },
        "meta": {"requestId": str(uuid6.uuid7())},
    }

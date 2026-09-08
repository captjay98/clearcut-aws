"""Provider-free API acceptance for the full revision + selective-rescan journey.

This test drives the durable selective-rescan vertical slice end to end against
the real migrated schema with the real SQL lineage adapters (revision plan, item
lineage, evidence lineage, and the scoped ``selective_rescan_checkpoints``
repository). It is honest about its boundary: no Parallel, Gemini, network, or
cloud dependency is touched. The child detection/research provider ports are the
in-repo hermetic doubles plus a typed fake research planner, so the "affected
items reach research" journey is exercised without a paid provider.

What it proves (local, provider-free):

* a v1 with cited evidence and a governed *historical* decision, and a full-file
  v2 whose adjacent diff carries all five change kinds (unchanged, moved,
  modified, added, removed) with the impact counts the diff API exposes;
* starting a selective rescan enqueues exactly one durable job with an
  authoritative ``selective_rescan.started`` audit event in the same
  transaction, and the two commit atomically;
* running the durable job materializes carried items only for
  unchanged/moved (exact/contextual) elements, carries their evidence forward
  referencing the ORIGINAL provenance verbatim, enqueues child detection and
  research only for the resulting affected items, and reaches the human
  confirmation stage;
* the prior governed decision is NOT copied to the carried item and remains
  historical on the predecessor; carried-only evidence does not satisfy the
  item's direct cited-claim gate so the carried item stays unresolved; a
  zero-evidence item stays unresolved with no fabricated fallback claim; removed
  before-elements stay historical;
* start, commit, stage processing, and child enqueue are replay-safe (a reload
  through a fresh service reconstructs parent/child state and duplicates no job,
  item, evidence, or provider call);
* a typed provider failure in the child research job is visible as a failed run
  and creates no fallback claim;
* a cross-org/project actor and an unauthorized actor fail before repository
  access.

What it does NOT prove: hosted Cloud SQL/Storage/Tasks durability, live Parallel
Search/Extract quality, paid-provider reliability, or any legal clearance. Those
require separate attributable evidence from the real environment.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
import uuid6
from clearcut.database import session_scope
from clearcut.detection.adapters.hermetic_runtime import HermeticDetectionRuntime
from clearcut.detection.adapters.sql_candidate_repository import SqlCandidateRepository
from clearcut.detection.adapters.sql_rescan_lineage import SqlItemLineageAdapter
from clearcut.detection.application.run_detection_job import RunDetectionJobService
from clearcut.detection.ports.model_runtime import (
    DetectionAttemptMetadata,
    DetectionFailure,
    DetectionSafeError,
    DetectionTokenUsage,
)
from clearcut.evaluation.adapters.hermetic_judge import HermeticJudgeAdapter
from clearcut.evaluation.adapters.sql_evaluation_repository import SqlEvaluationRepository
from clearcut.evaluation.application.evaluate import EvaluationService
from clearcut.main import app
from clearcut.operations.adapters.sql_job_repository import SqlJobRepository
from clearcut.operations.application.run_job import RunJobService
from clearcut.operations.domain.jobs import RunStatus
from clearcut.operations.ports.job_repository import EnqueueJob
from clearcut.rescan.adapters.sql_repository import SqlSelectiveRescanRepository
from clearcut.rescan.application.models import RescanStage
from clearcut.rescan.application.run_rescan_job import RunSelectiveRescanJobService
from clearcut.rescan.ports.repository import RescanChildWorkTicket
from clearcut.research.adapters.hermetic_extract import HermeticExtractAdapter
from clearcut.research.adapters.hermetic_search import HermeticSearchAdapter
from clearcut.research.adapters.sql_evidence_lineage import SqlEvidenceLineageAdapter
from clearcut.research.adapters.sql_research_repository import SqlResearchRepository
from clearcut.research.application.run_research_job import RunResearchJobService
from clearcut.research.domain.queries import ResearchPlan
from clearcut.research.domain.snapshots import ProviderFailure
from clearcut.research.ports.planner import (
    PlanningAttemptMetadata,
    PlanningTokenUsage,
    ResearchPlanningRequest,
    ResearchPlanningResult,
    ResearchPlanningSuccess,
)
from clearcut.scripts.adapters.sql_import_repository import SqlImportRepository
from clearcut.scripts.adapters.sql_revision_plan import SqlRevisionPlanAdapter
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.asyncio

_ORIGIN = {"origin": "http://test"}


class _EnabledGate:
    """A typed provider gate that reports the paid provider available.

    The local/test profile disables paid providers, so the production start
    route returns 503. Swapping this gate keeps the composition provider-free
    (no Parallel/Gemini/network/cloud call is ever made) while letting the
    governed start path run to a durable queued job — exactly the swap the
    existing selective-rescan HTTP test uses.
    """

    def is_enabled(self, provider: str) -> bool:
        del provider
        return True


class _EnableProviderGate:
    """Temporarily enable the paid-provider gate on the mounted start service."""

    def __enter__(self):
        self._service = app.state.start_selective_rescan_service
        self._original = self._service._provider_gate
        self._service._provider_gate = _EnabledGate()
        return self._service

    def __exit__(self, *exc) -> None:
        self._service._provider_gate = self._original


# --------------------------------------------------------------------------- #
# Typed provider-free doubles (no Parallel / Gemini / network / cloud)
# --------------------------------------------------------------------------- #


class _FakeResearchPlanner:
    """A typed ResearchPlannerPort that never calls a paid model."""

    def __init__(self, *, calls: list[UUID] | None = None) -> None:
        self.calls: list[UUID] = calls if calls is not None else []

    @property
    def requested_model(self) -> str:
        return "hermetic-planner-e2e-only"

    async def plan_research(self, request: ResearchPlanningRequest) -> ResearchPlanningResult:
        self.calls.append(request.item_id)
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


class _FailingSearch(HermeticSearchAdapter):
    """A typed WebSearchPort that returns a visible provider failure."""

    def search(self, request):  # type: ignore[override]
        return ProviderFailure(
            kind="retryable",
            message="Hermetic provider failure injected for the E2E honesty test.",
        )


class _FailingDetectionRuntime:
    """A typed ModelRuntimePort that returns a visible detection failure.

    Proves fresh detection of an added passage that fails surfaces as a VISIBLE
    failed rescan, never a silent "0 added items" that drops the added passage
    from clearance and research.
    """

    @property
    def requested_model(self) -> str:
        return "hermetic-detection-fail-e2e-only"

    async def detect_element(self, element):  # type: ignore[override]
        del element
        return DetectionFailure(
            error=DetectionSafeError(
                code="detection_provider_unavailable",
                message="Hermetic detection failure injected for the E2E honesty test.",
                retryable=True,
            ),
            attempt=DetectionAttemptMetadata(
                status="failed",
                requested_model=self.requested_model,
                returned_model=None,
                response_id=None,
                usage=DetectionTokenUsage(input_tokens=0, output_tokens=0, total_tokens=0),
                latency_ms=0,
                error=DetectionSafeError(
                    code="detection_provider_unavailable",
                    message="Hermetic detection failure injected for the E2E honesty test.",
                    retryable=True,
                ),
            ),
        )


class _CountingChildWork:
    """Wraps the production child-work coordinator to record what is requested.

    Delegates to the real coordinator so child detection/research jobs are
    enqueued through the durable job repository with the production idempotency
    keys, while recording the affected-item scope for assertions.
    """

    def __init__(self, inner) -> None:
        self._inner = inner
        self.detect_calls: list[frozenset[UUID]] = []
        self.research_calls: list[frozenset[UUID]] = []
        self.added_detect_calls: list[frozenset[UUID]] = []

    async def list_affected_items(self, **kwargs) -> tuple[UUID, ...]:
        return await self._inner.list_affected_items(**kwargs)

    async def detect_added_items(self, *, added_after_element_ids, **kwargs) -> tuple[UUID, ...]:
        self.added_detect_calls.append(frozenset(added_after_element_ids))
        return await self._inner.detect_added_items(
            added_after_element_ids=added_after_element_ids, **kwargs
        )

    async def request_detection(
        self, *, affected_item_ids, **kwargs
    ) -> tuple[RescanChildWorkTicket, ...]:
        self.detect_calls.append(frozenset(affected_item_ids))
        return await self._inner.request_detection(affected_item_ids=affected_item_ids, **kwargs)

    async def request_research(
        self, *, affected_item_ids, **kwargs
    ) -> tuple[RescanChildWorkTicket, ...]:
        self.research_calls.append(frozenset(affected_item_ids))
        return await self._inner.request_research(affected_item_ids=affected_item_ids, **kwargs)


# --------------------------------------------------------------------------- #
# Seeded revision fixture: two adjacent versions with all five change kinds
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SeededRevision:
    org_id: UUID
    project_id: UUID
    actor_id: UUID
    script_id: UUID
    before_version_id: UUID
    after_version_id: UUID
    # element ids by change kind
    unchanged_before: UUID
    unchanged_after: UUID
    moved_before: UUID
    moved_after: UUID
    modified_before: UUID
    modified_after: UUID
    added_after: UUID
    removed_before: UUID
    # An unchanged NARRATIVE line that legitimately never held a clearance item
    # (detection only creates items on brand/entity lines). It is carryable by
    # lineage but item-less, so it must be skipped by carry-forward, never fatal.
    narrative_unchanged_before: UUID
    narrative_unchanged_after: UUID
    # predecessor items + evidence
    cited_item_id: UUID
    zero_evidence_item_id: UUID
    modified_item_id: UUID
    removed_item_id: UUID
    original_claim_id: UUID
    snapshot_id: UUID
    run_id: UUID
    query_id: UUID
    provider_attempt_id: UUID
    decision_id: UUID


async def _register_owner(client: AsyncClient) -> tuple[UUID, UUID, UUID]:
    registration = await client.post(
        "/api/v1/users",
        json={
            "name": "Revision Owner",
            "email": f"revision-{uuid4().hex}@example.com",
            "password": "Password123!",
        },
    )
    assert registration.status_code == 201, registration.text
    context = await client.get("/api/v1/session-context")
    actor_id = UUID(context.json()["data"]["userId"])
    organization = await client.post(
        "/api/v1/organizations",
        json={"name": "Revision Studio", "slug": f"revision-{uuid4().hex[:8]}"},
    )
    assert organization.status_code == 201, organization.text
    org_id = UUID(organization.json()["data"]["orgId"])
    project = await client.post(
        f"/api/v1/organizations/{org_id}/projects",
        json={"title": "Revision Rescan Project"},
    )
    assert project.status_code == 201, project.text
    return org_id, UUID(project.json()["data"]["projectId"]), actor_id


async def _seed_active_policy(org_id: UUID) -> None:
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO protected_configurations "
                "(id, org_id, lifecycle, policy_version, prompt_version, created_at) "
                "VALUES (:id, :org_id, 'active', 'policy-v1', 'prompt-v1', CURRENT_TIMESTAMP)"
            ),
            {"id": str(uuid4()), "org_id": str(org_id)},
        )


async def _seed_version(
    *,
    org_id: UUID,
    project_id: UUID,
    script_id: UUID,
    version_id: UUID,
    ordinal: int,
    predecessor_version_id: UUID | None,
    predecessor_ordinal: int | None,
    create_script: bool,
) -> None:
    now = datetime.now(UTC)
    async with session_scope() as session:
        if create_script:
            await session.execute(
                sa.text(
                    "INSERT INTO scripts (id, org_id, project_id, title, created_at, "
                    "current_slot) VALUES (:id, :org_id, :project_id, 'Borrowed Light', "
                    ":created_at, 'current')"
                ),
                {
                    "id": str(script_id),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                    "created_at": now,
                },
            )
        await session.execute(
            sa.text(
                "INSERT INTO script_versions "
                "(id, script_id, org_id, project_id, ordinal, source_hash, parser_version, "
                "created_at, predecessor_version_id, predecessor_ordinal) VALUES "
                "(:id, :script_id, :org_id, :project_id, :ordinal, :source_hash, 'v1', "
                ":created_at, :predecessor_version_id, :predecessor_ordinal)"
            ),
            {
                "id": str(version_id),
                "script_id": str(script_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "ordinal": ordinal,
                "source_hash": f"{ordinal:064d}",
                "created_at": now,
                "predecessor_version_id": (
                    str(predecessor_version_id) if predecessor_version_id else None
                ),
                "predecessor_ordinal": predecessor_ordinal,
            },
        )


async def _seed_element(*, version_id: UUID, element_id: UUID, ordinal: int, text: str) -> None:
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO script_elements (id, version_id, ordinal, element_type, text) "
                "VALUES (:id, :version_id, :ordinal, 'action', :text)"
            ),
            {
                "id": str(element_id),
                "version_id": str(version_id),
                "ordinal": ordinal,
                "text": text,
            },
        )


async def _seed_item(
    *,
    org_id: UUID,
    project_id: UUID,
    script_id: UUID,
    version_id: UUID,
    element_id: UUID,
    item_id: UUID,
    category: str,
    text: str,
    status: str,
    research_status: str,
    workflow_status: str,
    disposition_status: str,
) -> None:
    now = datetime.now(UTC)
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO clearance_items "
                "(id, org_id, project_id, script_id, version_id, element_id, category, text, "
                "status, research_status, workflow_status, disposition_status, created_at, "
                "version) VALUES "
                "(:id, :org_id, :project_id, :script_id, :version_id, :element_id, :category, "
                ":text, :status, :research_status, :workflow_status, :disposition_status, "
                ":created_at, 1)"
            ),
            {
                "id": str(item_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "script_id": str(script_id),
                "version_id": str(version_id),
                "element_id": str(element_id),
                "category": category,
                "text": text,
                "status": status,
                "research_status": research_status,
                "workflow_status": workflow_status,
                "disposition_status": disposition_status,
                "created_at": now,
            },
        )


async def _seed_full_provenance_claim(
    *, org_id: UUID, project_id: UUID, item_id: UUID, version_id: UUID
) -> tuple[UUID, UUID, UUID, UUID, UUID]:
    now = datetime.now(UTC)
    run_id = uuid6.uuid7()
    query_id = uuid6.uuid7()
    attempt_id = uuid6.uuid7()
    authorization_id = uuid6.uuid7()
    snapshot_id = uuid6.uuid7()
    claim_id = uuid6.uuid7()
    canonical_url = "https://register.example/borrowed-light"
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO research_runs "
                "(id, org_id, project_id, item_id, version_id, status, created_at) VALUES "
                "(:id, :org_id, :project_id, :item_id, :version_id, 'completed', :created_at)"
            ),
            {
                "id": str(run_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "item_id": str(item_id),
                "version_id": str(version_id),
                "created_at": now,
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO research_queries "
                "(id, run_id, query, ordinal, org_id, project_id, item_id, version_id, "
                "created_at) VALUES "
                "(:id, :run_id, 'borrowed light rolex', 1, :org_id, :project_id, :item_id, "
                ":version_id, :created_at)"
            ),
            {
                "id": str(query_id),
                "run_id": str(run_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "item_id": str(item_id),
                "version_id": str(version_id),
                "created_at": now,
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO provider_attempts "
                "(id, run_id, operation_kind, status, created_at, org_id, project_id, item_id, "
                "query_id, authorizing_search_attempt_id, authorizing_operation_kind) VALUES "
                "(:id, :run_id, 'search', 'succeeded', :created_at, :org_id, :project_id, "
                ":item_id, :query_id, :id, 'search')"
            ),
            {
                "id": str(attempt_id),
                "run_id": str(run_id),
                "created_at": now,
                "org_id": str(org_id),
                "project_id": str(project_id),
                "item_id": str(item_id),
                "query_id": str(query_id),
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO search_result_authorizations "
                "(id, org_id, project_id, item_id, run_id, query_id, search_attempt_id, "
                "search_operation_kind, ordinal, url, canonical_url, title, publisher, excerpt, "
                "created_at) VALUES "
                "(:id, :org_id, :project_id, :item_id, :run_id, :query_id, :search_attempt_id, "
                "'search', 1, :url, :canonical_url, 'Official register', 'Authority', "
                "'No conflicting active marks.', :created_at)"
            ),
            {
                "id": str(authorization_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "item_id": str(item_id),
                "run_id": str(run_id),
                "query_id": str(query_id),
                "search_attempt_id": str(attempt_id),
                "url": canonical_url,
                "canonical_url": canonical_url,
                "created_at": now,
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO source_snapshots "
                "(id, org_id, project_id, item_id, run_id, url, title, publisher, excerpt, "
                "origin, sha256_hash, retrieved_at, query_id, provider_attempt_id, "
                "authorization_id, authorizing_search_attempt_id) VALUES "
                "(:id, :org_id, :project_id, :item_id, :run_id, :url, 'Official register', "
                "'Authority', 'No conflicting active marks.', 'search', :sha256_hash, "
                ":retrieved_at, :query_id, :provider_attempt_id, :authorization_id, "
                ":authorizing_search_attempt_id)"
            ),
            {
                "id": str(snapshot_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "item_id": str(item_id),
                "run_id": str(run_id),
                "url": canonical_url,
                "sha256_hash": "b" * 64,
                "retrieved_at": now,
                "query_id": str(query_id),
                "provider_attempt_id": str(attempt_id),
                "authorization_id": str(authorization_id),
                "authorizing_search_attempt_id": str(attempt_id),
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO evidence_claims "
                "(id, org_id, project_id, item_id, snapshot_id, stance, authority_tier, "
                "claim_text, provenance_excerpt, created_at, run_id, query_id, "
                "provider_attempt_id) VALUES "
                "(:id, :org_id, :project_id, :item_id, :snapshot_id, 'supports', "
                "'primary_official', :claim_text, :excerpt, :created_at, :run_id, :query_id, "
                ":provider_attempt_id)"
            ),
            {
                "id": str(claim_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "item_id": str(item_id),
                "snapshot_id": str(snapshot_id),
                "claim_text": "The register shows no conflicting active marks.",
                "excerpt": "No conflicting active marks.",
                "created_at": now,
                "run_id": str(run_id),
                "query_id": str(query_id),
                "provider_attempt_id": str(attempt_id),
            },
        )
    return claim_id, snapshot_id, run_id, query_id, attempt_id


async def _seed_historical_decision(
    *, org_id: UUID, project_id: UUID, item_id: UUID, actor_id: UUID
) -> UUID:
    decision_id = uuid6.uuid7()
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO governed_decision_records "
                "(id, org_id, project_id, item_id, actor_id, decision_kind, decision_value, "
                "rationale, expected_version, resulting_version, created_at) VALUES "
                "(:id, :org_id, :project_id, :item_id, :actor_id, 'evidence', 'accepted', "
                "'Prior clearance decision on version one.', 1, 2, :created_at)"
            ),
            {
                "id": str(decision_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "item_id": str(item_id),
                "actor_id": str(actor_id),
                "created_at": datetime.now(UTC),
            },
        )
    return decision_id


async def _seed_lineage(
    *,
    org_id: UUID,
    project_id: UUID,
    script_id: UUID,
    before_version_id: UUID,
    after_version_id: UUID,
    rows: list[tuple[UUID | None, UUID | None, str, str]],
) -> None:
    """Persist a script diff + one lineage row per change kind.

    ``rows`` is a list of ``(before_element_id, after_element_id, change_kind,
    confidence)``.
    """
    now = datetime.now(UTC)
    diff_id = uuid6.uuid7()
    async with session_scope() as session:
        await session.execute(
            sa.text(
                "INSERT INTO script_diffs "
                "(id, org_id, project_id, script_id, before_version_id, after_version_id, "
                "before_ordinal, after_ordinal, algorithm_version, diff_payload, "
                "summary_payload, created_at) VALUES "
                "(:id, :org_id, :project_id, :script_id, :before_version_id, :after_version_id, "
                "1, 2, 'element-lineage-v1', :diff_payload, :summary_payload, :created_at)"
            ),
            {
                "id": str(diff_id),
                "org_id": str(org_id),
                "project_id": str(project_id),
                "script_id": str(script_id),
                "before_version_id": str(before_version_id),
                "after_version_id": str(after_version_id),
                "diff_payload": "{}",
                "summary_payload": "{}",
                "created_at": now,
            },
        )
        for before_element_id, after_element_id, change_kind, confidence in rows:
            await session.execute(
                sa.text(
                    "INSERT INTO script_element_lineage "
                    "(id, org_id, project_id, script_id, diff_id, before_version_id, "
                    "after_version_id, before_element_id, after_element_id, change_kind, "
                    "confidence, algorithm_version, created_at) VALUES "
                    "(:id, :org_id, :project_id, :script_id, :diff_id, :before_version_id, "
                    ":after_version_id, :before_element_id, :after_element_id, :change_kind, "
                    ":confidence, 'element-lineage-v1', :created_at)"
                ),
                {
                    "id": str(uuid6.uuid7()),
                    "org_id": str(org_id),
                    "project_id": str(project_id),
                    "script_id": str(script_id),
                    "diff_id": str(diff_id),
                    "before_version_id": str(before_version_id),
                    "after_version_id": str(after_version_id),
                    "before_element_id": (str(before_element_id) if before_element_id else None),
                    "after_element_id": (str(after_element_id) if after_element_id else None),
                    "change_kind": change_kind,
                    "confidence": confidence,
                    "created_at": now,
                },
            )


async def _seed_full_revision(client: AsyncClient) -> SeededRevision:
    org_id, project_id, actor_id = await _register_owner(client)
    await _seed_active_policy(org_id)

    script_id = uuid6.uuid7()
    before_version_id = uuid6.uuid7()
    after_version_id = uuid6.uuid7()

    unchanged_before, unchanged_after = uuid6.uuid7(), uuid6.uuid7()
    moved_before, moved_after = uuid6.uuid7(), uuid6.uuid7()
    modified_before, modified_after = uuid6.uuid7(), uuid6.uuid7()
    added_after = uuid6.uuid7()
    removed_before = uuid6.uuid7()
    narrative_unchanged_before, narrative_unchanged_after = uuid6.uuid7(), uuid6.uuid7()

    cited_item_id = uuid6.uuid7()
    zero_evidence_item_id = uuid6.uuid7()
    modified_item_id = uuid6.uuid7()
    removed_item_id = uuid6.uuid7()

    await _seed_version(
        org_id=org_id,
        project_id=project_id,
        script_id=script_id,
        version_id=before_version_id,
        ordinal=1,
        predecessor_version_id=None,
        predecessor_ordinal=None,
        create_script=True,
    )
    await _seed_version(
        org_id=org_id,
        project_id=project_id,
        script_id=script_id,
        version_id=after_version_id,
        ordinal=2,
        predecessor_version_id=before_version_id,
        predecessor_ordinal=1,
        create_script=False,
    )

    # Before-version elements.
    await _seed_element(
        version_id=before_version_id,
        element_id=unchanged_before,
        ordinal=1,
        text="Every case leaves a mark. This one left a scar.",
    )
    await _seed_element(
        version_id=before_version_id,
        element_id=moved_before,
        ordinal=2,
        text="A single bulb swings overhead as footsteps echo below.",
    )
    await _seed_element(
        version_id=before_version_id,
        element_id=modified_before,
        ordinal=3,
        text="Vera studies the file, a Rolex glinting on her wrist.",
    )
    await _seed_element(
        version_id=before_version_id,
        element_id=removed_before,
        ordinal=4,
        text="A Ferrari idles at the pier as its engine cools.",
    )
    await _seed_element(
        version_id=before_version_id,
        element_id=narrative_unchanged_before,
        ordinal=5,
        text="Rain hammers the tin roof, relentless and cold.",
    )

    # After-version elements.
    await _seed_element(
        version_id=after_version_id,
        element_id=unchanged_after,
        ordinal=1,
        text="Every case leaves a mark. This one left a scar.",
    )
    await _seed_element(
        version_id=after_version_id,
        element_id=modified_after,
        ordinal=2,
        text="Vera studies the file, an iPhone glowing on the desk.",
    )
    await _seed_element(
        version_id=after_version_id,
        element_id=moved_after,
        ordinal=3,
        text="A single bulb swings overhead as footsteps echo below.",
    )
    await _seed_element(
        version_id=after_version_id,
        element_id=added_after,
        ordinal=4,
        text="A courier drops a crate stamped with a faded Nike logo.",
    )
    await _seed_element(
        version_id=after_version_id,
        element_id=narrative_unchanged_after,
        ordinal=5,
        text="Rain hammers the tin roof, relentless and cold.",
    )

    # Predecessor clearance items on v1.
    await _seed_item(
        org_id=org_id,
        project_id=project_id,
        script_id=script_id,
        version_id=before_version_id,
        element_id=unchanged_before,
        item_id=cited_item_id,
        category="products_and_trademarks",
        text="Rolex",
        status="resolved",
        research_status="completed",
        workflow_status="resolved",
        disposition_status="approved_as_is",
    )
    await _seed_item(
        org_id=org_id,
        project_id=project_id,
        script_id=script_id,
        version_id=before_version_id,
        element_id=moved_before,
        item_id=zero_evidence_item_id,
        category="locations_and_landmarks",
        text="Stairwell",
        status="unresolved",
        research_status="completed",
        workflow_status="open",
        disposition_status="undisposed",
    )
    await _seed_item(
        org_id=org_id,
        project_id=project_id,
        script_id=script_id,
        version_id=before_version_id,
        element_id=modified_before,
        item_id=modified_item_id,
        category="products_and_trademarks",
        text="Rolex",
        status="unresolved",
        research_status="completed",
        workflow_status="open",
        disposition_status="undisposed",
    )
    await _seed_item(
        org_id=org_id,
        project_id=project_id,
        script_id=script_id,
        version_id=before_version_id,
        element_id=removed_before,
        item_id=removed_item_id,
        category="products_and_trademarks",
        text="Ferrari",
        status="unresolved",
        research_status="completed",
        workflow_status="open",
        disposition_status="undisposed",
    )

    # The unchanged, carryable item has cited evidence and a historical decision.
    (
        claim_id,
        snapshot_id,
        run_id,
        query_id,
        attempt_id,
    ) = await _seed_full_provenance_claim(
        org_id=org_id,
        project_id=project_id,
        item_id=cited_item_id,
        version_id=before_version_id,
    )
    decision_id = await _seed_historical_decision(
        org_id=org_id,
        project_id=project_id,
        item_id=cited_item_id,
        actor_id=actor_id,
    )

    # Persisted adjacent diff / lineage carrying all five change kinds.
    await _seed_lineage(
        org_id=org_id,
        project_id=project_id,
        script_id=script_id,
        before_version_id=before_version_id,
        after_version_id=after_version_id,
        rows=[
            (unchanged_before, unchanged_after, "unchanged", "exact"),
            (moved_before, moved_after, "moved", "exact"),
            (modified_before, modified_after, "modified", "similar"),
            (None, added_after, "added", "unmatched"),
            (removed_before, None, "removed", "unmatched"),
            # A second unchanged (carryable) element that never held a clearance
            # item: carry-forward must skip it, not fail the rescan.
            (
                narrative_unchanged_before,
                narrative_unchanged_after,
                "unchanged",
                "exact",
            ),
        ],
    )

    return SeededRevision(
        org_id=org_id,
        project_id=project_id,
        actor_id=actor_id,
        script_id=script_id,
        before_version_id=before_version_id,
        after_version_id=after_version_id,
        unchanged_before=unchanged_before,
        unchanged_after=unchanged_after,
        moved_before=moved_before,
        moved_after=moved_after,
        modified_before=modified_before,
        modified_after=modified_after,
        added_after=added_after,
        removed_before=removed_before,
        narrative_unchanged_before=narrative_unchanged_before,
        narrative_unchanged_after=narrative_unchanged_after,
        cited_item_id=cited_item_id,
        zero_evidence_item_id=zero_evidence_item_id,
        modified_item_id=modified_item_id,
        removed_item_id=removed_item_id,
        original_claim_id=claim_id,
        snapshot_id=snapshot_id,
        run_id=run_id,
        query_id=query_id,
        provider_attempt_id=attempt_id,
        decision_id=decision_id,
    )


# --------------------------------------------------------------------------- #
# Provider-free rescan composition (real SQL adapters + hermetic child work)
# --------------------------------------------------------------------------- #


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=_ORIGIN)


def _compose_rescan(job_repository: SqlJobRepository, checkpoints, *, child):
    """Compose the real rescan job service with real lineage adapters."""
    return RunSelectiveRescanJobService(
        revision_plan=SqlRevisionPlanAdapter(SqlImportRepository()),
        materialize_items=_ItemLineageCoordinator(SqlItemLineageAdapter()),
        carry_evidence=SqlEvidenceLineageAdapter(),
        child_work=child,
        repository=checkpoints,
        job_repository=job_repository,
    )


class _ItemLineageCoordinator:
    """Mirror of the production coordinator: resolve predecessor items by element."""

    def __init__(self, adapter: SqlItemLineageAdapter) -> None:
        self._adapter = adapter

    async def materialize(
        self,
        *,
        org_id,
        project_id,
        script_id,
        before_version_id,
        after_version_id,
        carryable_elements,
    ):
        from clearcut.rescan.application.models import CarryableElement

        resolved: list[CarryableElement] = []
        async with session_scope() as session:
            for element in carryable_elements:
                row = (
                    (
                        await session.execute(
                            sa.text(
                                "SELECT id, category, text FROM clearance_items "
                                "WHERE org_id = :org_id AND project_id = :project_id "
                                "AND script_id = :script_id AND version_id = :version_id "
                                "AND element_id = :element_id"
                            ),
                            {
                                "org_id": str(org_id),
                                "project_id": str(project_id),
                                "script_id": str(script_id),
                                "version_id": str(before_version_id),
                                "element_id": str(element.before_element_id),
                            },
                        )
                    )
                    .mappings()
                    .first()
                )
                if row is None:
                    # An unchanged/moved narrative passage legitimately has no
                    # predecessor clearance item (detection only creates items on
                    # brand/entity lines): nothing to carry, so skip it. Scope is
                    # still enforced by the query above; the row simply does not
                    # exist. Mirrors the production coordinator.
                    continue
                resolved.append(
                    CarryableElement(
                        before_element_id=element.before_element_id,
                        after_element_id=element.after_element_id,
                        predecessor_item_id=UUID(str(row["id"])),
                        category=str(row["category"]),
                        text=str(row["text"]),
                    )
                )
        return await self._adapter.materialize_carried_items(
            org_id=org_id,
            project_id=project_id,
            script_id=script_id,
            before_version_id=before_version_id,
            after_version_id=after_version_id,
            carryable_elements=tuple(resolved),
        )


class _ChildWorkCoordinator:
    """Mirror of the production coordinator: enqueue durable child jobs."""

    def __init__(
        self, *, item_lineage: SqlItemLineageAdapter, job_repository, detection_runtime=None
    ) -> None:
        self._item_lineage = item_lineage
        self._job_repository = job_repository
        self._detection_runtime = detection_runtime

    async def list_affected_items(
        self, *, org_id, project_id, before_version_id, affected_element_ids
    ) -> tuple[UUID, ...]:
        return await self._item_lineage.list_affected_items(
            org_id=org_id,
            project_id=project_id,
            before_version_id=before_version_id,
            affected_element_ids=affected_element_ids,
        )

    async def detect_added_items(
        self, *, org_id, project_id, after_version_id, added_after_element_ids, actor_id
    ) -> tuple[UUID, ...]:
        # Mirror of production: enqueue a detection child scoped to EXACTLY the
        # added after-version elements, run it to completion through hermetic
        # detection, then return the resulting brand-new unresolved item ids.
        if not added_after_element_ids:
            return ()
        key = f"selective_rescan:detect-added:{after_version_id}"
        enqueued = await self._job_repository.enqueue(
            EnqueueJob(
                org_id=org_id,
                project_id=project_id,
                actor_id=actor_id,
                job_type="detection",
                idempotency_key=key,
                payload={
                    "schemaVersion": 1,
                    "target": {"type": "script_version", "id": str(after_version_id)},
                    "elementIds": sorted(str(element_id) for element_id in added_after_element_ids),
                },
                audit_action="detection.started",
                target_type="script_version",
                target_id=after_version_id,
            )
        )
        detection, _research = _hermetic_runner(
            self._job_repository, detection_runtime=self._detection_runtime
        )
        completed = await RunJobService(
            repository=self._job_repository,
            processors={"detection": detection},
            lease_owner="local-rescan-added-e2e",
        ).run(enqueued.job.job_id, org_id, project_id)
        if completed.status is not RunStatus.SUCCEEDED:
            from clearcut.rescan.application.models import RescanSafeError

            error = completed.error
            raise RescanSafeError(
                code=error.code if error is not None else "added_detection_failed",
                message=(
                    error.message
                    if error is not None
                    else "Fresh detection of added passages did not complete."
                ),
                retryable=error.retryable if error is not None else True,
            )
        async with session_scope() as session:
            rows = (
                await session.execute(
                    sa.text(
                        "SELECT id FROM clearance_items "
                        "WHERE org_id = :org_id AND project_id = :project_id "
                        "AND version_id = :version_id "
                        "AND element_id IN :element_ids "
                        "AND predecessor_item_id IS NULL "
                        "ORDER BY created_at, id"
                    ).bindparams(sa.bindparam("element_ids", expanding=True)),
                    {
                        "org_id": str(org_id),
                        "project_id": str(project_id),
                        "version_id": str(after_version_id),
                        "element_ids": [str(e) for e in added_after_element_ids],
                    },
                )
            ).scalars()
            return tuple(UUID(str(item_id)) for item_id in rows)

    async def request_detection(
        self, *, org_id, project_id, after_version_id, affected_item_ids, actor_id
    ) -> tuple[RescanChildWorkTicket, ...]:
        return await self._request(
            kind="detection",
            org_id=org_id,
            project_id=project_id,
            after_version_id=after_version_id,
            affected_item_ids=affected_item_ids,
            actor_id=actor_id,
        )

    async def request_research(
        self, *, org_id, project_id, after_version_id, affected_item_ids, actor_id
    ) -> tuple[RescanChildWorkTicket, ...]:
        return await self._request(
            kind="research",
            org_id=org_id,
            project_id=project_id,
            after_version_id=after_version_id,
            affected_item_ids=affected_item_ids,
            actor_id=actor_id,
        )

    async def _request(
        self, *, kind, org_id, project_id, after_version_id, affected_item_ids, actor_id
    ) -> tuple[RescanChildWorkTicket, ...]:
        target_type = "script_version" if kind == "detection" else "clearance_item"
        tickets: list[RescanChildWorkTicket] = []
        for item_id in affected_item_ids:
            key = f"selective_rescan:{kind}:{item_id}"
            target_id = after_version_id if kind == "detection" else item_id
            await self._job_repository.enqueue(
                EnqueueJob(
                    org_id=org_id,
                    project_id=project_id,
                    actor_id=actor_id,
                    job_type=kind,
                    idempotency_key=key,
                    payload={
                        "schemaVersion": 1,
                        "target": {"type": target_type, "id": str(target_id)},
                    },
                    audit_action=f"{kind}.started",
                    target_type=target_type,
                    target_id=target_id,
                )
            )
            tickets.append(RescanChildWorkTicket(item_id=item_id, idempotency_key=key))
        return tuple(tickets)


def _hermetic_runner(
    job_repository: SqlJobRepository, *, search=None, planner=None, detection_runtime=None
):
    """A job runner whose detection/research processors use hermetic doubles."""
    candidate_repository = SqlCandidateRepository()
    evaluation = EvaluationService(
        judge=HermeticJudgeAdapter(),
        repository=SqlEvaluationRepository(),
    )
    run_detection_job = RunDetectionJobService(
        repository=candidate_repository,
        job_repository=job_repository,
        runtime=detection_runtime or HermeticDetectionRuntime(),
        evaluation=evaluation,
    )
    run_research_job = RunResearchJobService(
        repository=SqlResearchRepository(),
        planner=planner or _FakeResearchPlanner(),
        search=search or HermeticSearchAdapter(),
        extract=HermeticExtractAdapter(),
        evaluation=evaluation,
    )
    return run_detection_job, run_research_job


async def _run_rescan(
    seed: SeededRevision,
    *,
    job_repository: SqlJobRepository,
    checkpoints: SqlSelectiveRescanRepository,
    child: _CountingChildWork,
    idempotency_key: str = "selective_rescan:e2e",
) -> UUID:
    enqueued = await job_repository.enqueue(
        EnqueueJob(
            org_id=seed.org_id,
            project_id=seed.project_id,
            actor_id=seed.actor_id,
            job_type="selective_rescan",
            idempotency_key=idempotency_key,
            payload={
                "schemaVersion": 1,
                "target": {"type": "script_version", "id": str(seed.after_version_id)},
            },
            audit_action="selective_rescan.started",
            target_type="script_version",
            target_id=seed.after_version_id,
        )
    )
    processor = _compose_rescan(job_repository, checkpoints, child=child)
    completed = await RunJobService(
        repository=job_repository,
        processors={"selective_rescan": processor},
        lease_owner="local-rescan-e2e",
    ).run(enqueued.job.job_id, seed.org_id, seed.project_id)
    assert completed.status is RunStatus.SUCCEEDED, completed.error
    return enqueued.job.job_id


async def _drain_child_jobs(
    seed: SeededRevision,
    *,
    job_repository: SqlJobRepository,
    search=None,
    planner=None,
) -> list[tuple[str, RunStatus, object]]:
    """Run every queued detection/research child job through hermetic doubles."""
    detection, research = _hermetic_runner(job_repository, search=search, planner=planner)
    runner = RunJobService(
        repository=job_repository,
        processors={"detection": detection, "research": research},
        lease_owner="local-child-e2e",
    )
    outcomes: list[tuple[str, RunStatus, object]] = []
    async with session_scope() as session:
        rows = (
            (
                await session.execute(
                    sa.text(
                        "SELECT id, job_type FROM jobs "
                        "WHERE org_id = :org_id AND project_id = :project_id "
                        "AND job_type IN ('detection', 'research') "
                        "ORDER BY created_at"
                    ),
                    {
                        "org_id": str(seed.org_id),
                        "project_id": str(seed.project_id),
                    },
                )
            )
            .mappings()
            .all()
        )
    for row in rows:
        record = await runner.run(UUID(str(row["id"])), seed.org_id, seed.project_id)
        outcomes.append((str(row["job_type"]), record.status, record.error))
    return outcomes


# --------------------------------------------------------------------------- #
# Diff exposure (impact counts + all five change kinds through the API)
# --------------------------------------------------------------------------- #


async def test_persisted_diff_exposes_all_five_change_kinds_with_impact_counts() -> None:
    async with _client() as client:
        seed = await _seed_full_revision(client)
        diff = await client.get(
            f"/api/v1/organizations/{seed.org_id}/projects/{seed.project_id}"
            f"/script-versions/{seed.after_version_id}/diff"
        )
    assert diff.status_code == 200, diff.text
    data = diff.json()["data"]
    assert data["beforeVersionId"] == str(seed.before_version_id)
    assert data["afterVersionId"] == str(seed.after_version_id)
    # Contract shape: element-level changes surface under ``elements`` with a single
    # ``changeKind`` each, and aggregate counts live under ``summary``.
    change_kinds = {element["changeKind"] for element in data["elements"]}
    assert change_kinds == {"unchanged", "moved", "modified", "added", "removed"}
    summary = data["summary"]
    # affectedElementCount = modified + added; providerWorkEstimate mirrors it.
    assert summary["affectedElementCount"] == summary["modified"] + summary["added"]
    assert summary["providerWorkEstimate"] == summary["affectedElementCount"]
    # Carried-forward items are the unchanged/moved (exact/contextual) lineage pairs.
    assert summary["carriedForwardItemCount"] == summary["unchanged"] + summary["moved"]


# --------------------------------------------------------------------------- #
# Atomic start: single durable job + authoritative audit in one transaction
# --------------------------------------------------------------------------- #


async def test_start_is_atomic_single_job_and_started_audit() -> None:
    async with _client() as client:
        seed = await _seed_full_revision(client)
        with _EnableProviderGate():
            response = await client.post(
                f"/api/v1/organizations/{seed.org_id}/projects/{seed.project_id}"
                f"/script-versions/{seed.after_version_id}:startSelectiveRescan",
                headers={"Idempotency-Key": "rescan-start-atomic"},
            )
    assert response.status_code == 202, response.text
    data = response.json()["data"]
    assert data["jobType"] == "selective_rescan"
    assert data["target"] == {"type": "script_version", "id": str(seed.after_version_id)}

    async with session_scope() as session:
        job_count = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM jobs WHERE org_id = :org_id "
                    "AND project_id = :project_id AND job_type = 'selective_rescan'"
                ),
                {"org_id": str(seed.org_id), "project_id": str(seed.project_id)},
            )
        ).scalar_one()
        audit_count = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM authoritative_audit_events "
                    "WHERE org_id = :org_id AND project_id = :project_id "
                    "AND action = 'selective_rescan.started'"
                ),
                {"org_id": str(seed.org_id), "project_id": str(seed.project_id)},
            )
        ).scalar_one()
    assert int(job_count) == 1
    assert int(audit_count) == 1


async def test_start_is_replay_safe_no_second_job_or_audit() -> None:
    async with _client() as client:
        seed = await _seed_full_revision(client)
        path = (
            f"/api/v1/organizations/{seed.org_id}/projects/{seed.project_id}"
            f"/script-versions/{seed.after_version_id}:startSelectiveRescan"
        )
        with _EnableProviderGate():
            first = await client.post(path, headers={"Idempotency-Key": "rescan-start-1"})
            second = await client.post(path, headers={"Idempotency-Key": "rescan-start-2"})
    assert first.status_code == 202, first.text
    assert second.status_code == 202, second.text
    assert first.json()["data"]["jobId"] == second.json()["data"]["jobId"]

    async with session_scope() as session:
        job_count = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM jobs WHERE org_id = :org_id "
                    "AND project_id = :project_id AND job_type = 'selective_rescan'"
                ),
                {"org_id": str(seed.org_id), "project_id": str(seed.project_id)},
            )
        ).scalar_one()
    assert int(job_count) == 1


async def test_start_fails_before_repository_access_for_unauthenticated_actor() -> None:
    async with _client() as client:
        seed = await _seed_full_revision(client)
    async with _client() as anonymous:
        response = await anonymous.post(
            f"/api/v1/organizations/{seed.org_id}/projects/{seed.project_id}"
            f"/script-versions/{seed.after_version_id}:startSelectiveRescan",
            headers={"Idempotency-Key": "rescan-anon"},
        )
    assert response.status_code == 401


async def test_start_fails_closed_on_cross_org_and_cross_project() -> None:
    async with _client() as client:
        seed = await _seed_full_revision(client)
        foreign_org = uuid6.uuid7()
        foreign_project = uuid6.uuid7()
        cross_org = await client.post(
            f"/api/v1/organizations/{foreign_org}/projects/{seed.project_id}"
            f"/script-versions/{seed.after_version_id}:startSelectiveRescan",
            headers={"Idempotency-Key": "rescan-cross-org"},
        )
        cross_project = await client.post(
            f"/api/v1/organizations/{seed.org_id}/projects/{foreign_project}"
            f"/script-versions/{seed.after_version_id}:startSelectiveRescan",
            headers={"Idempotency-Key": "rescan-cross-project"},
        )
    assert cross_org.status_code in (403, 404)
    assert cross_project.status_code in (403, 404)


# --------------------------------------------------------------------------- #
# Full durable journey: carry-forward, decisions, gates, child scope
# --------------------------------------------------------------------------- #


async def test_full_journey_carries_forward_and_scopes_child_work() -> None:
    async with _client() as client:
        seed = await _seed_full_revision(client)

    job_repository = SqlJobRepository()
    checkpoints = SqlSelectiveRescanRepository()
    child = _CountingChildWork(
        _ChildWorkCoordinator(
            item_lineage=SqlItemLineageAdapter(),
            job_repository=job_repository,
        )
    )
    job_id = await _run_rescan(
        seed, job_repository=job_repository, checkpoints=checkpoints, child=child
    )

    # Only the modified item's element is affected (the removed one has no
    # after-element; unchanged/moved carry forward). Detection and research run
    # over the same affected item set only.
    #
    # Regression guard: a modified passage has DISTINCT before/after element ids
    # (script_elements.id is globally unique), and the affected-item lookup
    # resolves the PREDECESSOR item on the before version. If the revision plan
    # were to publish the after-version element id as the affected id (the P0
    # defect), this lookup would find nothing and the modified passage would be
    # silently dropped from detection and research.
    assert seed.modified_before != seed.modified_after
    # The modified passage reaches detection via its BEFORE predecessor item.
    assert child.detect_calls == [frozenset({seed.modified_item_id})]
    # The added passage has no predecessor, so it reaches FRESH after-version
    # detection scoped to exactly its after element id.
    assert child.added_detect_calls == [frozenset({seed.added_after})]
    # Research reaches the modified predecessor item AND the freshly detected
    # added item (resolved after detection materializes it).
    async with session_scope() as session:
        added_item_id = UUID(
            str(
                (
                    await session.execute(
                        sa.text(
                            "SELECT id FROM clearance_items WHERE version_id = :after "
                            "AND element_id = :added_element AND predecessor_item_id IS NULL"
                        ),
                        {
                            "after": str(seed.after_version_id),
                            "added_element": str(seed.added_after),
                        },
                    )
                ).scalar_one()
            )
        )
    assert child.research_calls == [frozenset({seed.modified_item_id, added_item_id})]

    # Every stage advanced in order and succeeded.
    history = await checkpoints.load_stage_history(
        org_id=seed.org_id, project_id=seed.project_id, job_id=job_id
    )
    assert [stage for stage, _status in history] == [
        RescanStage.MATERIALIZING_LINEAGE,
        RescanStage.CARRYING_EVIDENCE,
        RescanStage.DETECTING_AFFECTED_PASSAGES,
        RescanStage.RESEARCHING_AFFECTED_ITEMS,
        RescanStage.AWAITING_CONFIRMATION,
        RescanStage.COMPLETED,
    ]
    assert all(status == "succeeded" for _stage, status in history)

    async with session_scope() as session:
        # Two carried items (unchanged + moved), both unresolved and confirmation
        # required, both referencing their predecessor.
        carried = (
            (
                await session.execute(
                    sa.text(
                        "SELECT element_id, status, lineage_kind, "
                        "carried_forward_confirmation_required, predecessor_item_id "
                        "FROM clearance_items "
                        "WHERE org_id = :org_id AND project_id = :project_id "
                        "AND version_id = :after AND lineage_kind = 'carried_forward'"
                    ),
                    {
                        "org_id": str(seed.org_id),
                        "project_id": str(seed.project_id),
                        "after": str(seed.after_version_id),
                    },
                )
            )
            .mappings()
            .all()
        )
        carried_elements = {UUID(str(row["element_id"])) for row in carried}
        assert carried_elements == {seed.unchanged_after, seed.moved_after}
        for row in carried:
            assert str(row["status"]) == "unresolved"
            assert bool(row["carried_forward_confirmation_required"]) is True

        carried_from_cited = next(
            row for row in carried if UUID(str(row["element_id"])) == seed.unchanged_after
        )
        new_item_id = (
            await session.execute(
                sa.text(
                    "SELECT id FROM clearance_items WHERE version_id = :after "
                    "AND element_id = :element_id AND lineage_kind = 'carried_forward'"
                ),
                {
                    "after": str(seed.after_version_id),
                    "element_id": str(seed.unchanged_after),
                },
            )
        ).scalar_one()
        new_item_id = UUID(str(new_item_id))
        assert UUID(str(carried_from_cited["predecessor_item_id"])) == seed.cited_item_id

        # Carried evidence references the ORIGINAL provenance verbatim ...
        edge = (
            (
                await session.execute(
                    sa.text(
                        "SELECT source_item_id, original_claim_id, snapshot_id, run_id, "
                        "query_id, provider_attempt_id FROM evidence_carry_forwards "
                        "WHERE new_item_id = :new_item_id"
                    ),
                    {"new_item_id": str(new_item_id)},
                )
            )
            .mappings()
            .one()
        )
        assert UUID(str(edge["source_item_id"])) == seed.cited_item_id
        assert UUID(str(edge["original_claim_id"])) == seed.original_claim_id
        assert UUID(str(edge["snapshot_id"])) == seed.snapshot_id
        assert UUID(str(edge["run_id"])) == seed.run_id
        assert UUID(str(edge["query_id"])) == seed.query_id
        assert UUID(str(edge["provider_attempt_id"])) == seed.provider_attempt_id

        # ... but carried-only evidence never becomes a direct claim, so the
        # carried item does not satisfy the direct cited-claim gate.
        direct_claims = (
            await session.execute(
                sa.text("SELECT count(*) FROM evidence_claims WHERE item_id = :item_id"),
                {"item_id": str(new_item_id)},
            )
        ).scalar_one()
        assert int(direct_claims) == 0

        # The prior governed decision is NOT copied and remains historical on the
        # predecessor only.
        decisions_on_new = (
            await session.execute(
                sa.text("SELECT count(*) FROM governed_decision_records WHERE item_id = :item_id"),
                {"item_id": str(new_item_id)},
            )
        ).scalar_one()
        decisions_on_predecessor = (
            await session.execute(
                sa.text("SELECT count(*) FROM governed_decision_records WHERE item_id = :item_id"),
                {"item_id": str(seed.cited_item_id)},
            )
        ).scalar_one()
        assert int(decisions_on_new) == 0
        assert int(decisions_on_predecessor) == 1

        # A removed before-element carries no successor item.
        removed_successor = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM clearance_items "
                    "WHERE version_id = :after AND predecessor_item_id = :removed"
                ),
                {
                    "after": str(seed.after_version_id),
                    "removed": str(seed.removed_item_id),
                },
            )
        ).scalar_one()
        assert int(removed_successor) == 0

        # An unchanged NARRATIVE carryable element that never held a clearance
        # item is SKIPPED, not fatal: it produces no carried successor and does
        # not fail the rescan (regression guard for predecessor_item_not_found).
        narrative_successor = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM clearance_items "
                    "WHERE version_id = :after AND element_id = :narrative"
                ),
                {
                    "after": str(seed.after_version_id),
                    "narrative": str(seed.narrative_unchanged_after),
                },
            )
        ).scalar_one()
        assert int(narrative_successor) == 0


async def test_added_passage_gets_fresh_detection_and_reaches_research() -> None:
    """An ADDED passage must produce a brand-new unresolved after-version item.

    The approved design requires "Modified and added passages require fresh
    detection and research" and "Detection runs only on changed and added
    passages". A modified passage reaches detection via its BEFORE predecessor
    item; an ADDED passage has NO predecessor item and no before element id, so
    the before-version predecessor lookup can never reach it. This regression
    proves that the added Nike passage on the AFTER version is freshly detected
    into a NEW unresolved clearance item with NO predecessor, NO carried
    evidence, and NO copied decision, and that this new item reaches research —
    exactly like any newly detected item.
    """
    async with _client() as client:
        seed = await _seed_full_revision(client)

    job_repository = SqlJobRepository()
    checkpoints = SqlSelectiveRescanRepository()
    child = _CountingChildWork(
        _ChildWorkCoordinator(
            item_lineage=SqlItemLineageAdapter(),
            job_repository=job_repository,
        )
    )
    await _run_rescan(seed, job_repository=job_repository, checkpoints=checkpoints, child=child)

    planner = _FakeResearchPlanner()
    outcomes = await _drain_child_jobs(seed, job_repository=job_repository, planner=planner)

    async with session_scope() as session:
        added_items = (
            (
                await session.execute(
                    sa.text(
                        "SELECT id, status, predecessor_item_id, lineage_kind, "
                        "detection_run_id, candidate_fingerprint FROM clearance_items "
                        "WHERE org_id = :org_id AND project_id = :project_id "
                        "AND version_id = :after AND element_id = :added_element"
                    ),
                    {
                        "org_id": str(seed.org_id),
                        "project_id": str(seed.project_id),
                        "after": str(seed.after_version_id),
                        "added_element": str(seed.added_after),
                    },
                )
            )
            .mappings()
            .all()
        )
    # Exactly one brand-new item was freshly detected for the added passage.
    assert len(added_items) == 1, added_items
    added_item = added_items[0]
    added_item_id = UUID(str(added_item["id"]))
    # It is a fresh, unresolved detection item: no predecessor, no carried
    # lineage, but bound to a real detection run (normal detection provenance).
    assert str(added_item["status"]) == "unresolved"
    assert added_item["predecessor_item_id"] is None
    assert added_item["lineage_kind"] is None
    assert added_item["detection_run_id"] is not None
    assert added_item["candidate_fingerprint"] is not None

    # The added item carries no fabricated evidence and no copied decision.
    async with session_scope() as session:
        added_claims = (
            await session.execute(
                sa.text("SELECT count(*) FROM evidence_claims WHERE item_id = :item_id"),
                {"item_id": str(added_item_id)},
            )
        ).scalar_one()
        added_carry = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM evidence_carry_forwards WHERE new_item_id = :item_id"
                ),
                {"item_id": str(added_item_id)},
            )
        ).scalar_one()
        added_decisions = (
            await session.execute(
                sa.text("SELECT count(*) FROM governed_decision_records WHERE item_id = :item_id"),
                {"item_id": str(added_item_id)},
            )
        ).scalar_one()
    assert int(added_carry) == 0
    assert int(added_decisions) == 0

    # The freshly detected added item reaches research like any newly detected
    # item: the planner is consulted for it and its research run succeeds.
    research_outcomes = [o for o in outcomes if o[0] == "research"]
    assert all(status is RunStatus.SUCCEEDED for _kind, status, _error in research_outcomes)
    assert added_item_id in planner.calls
    # Research produced cited context (not a fabricated fallback) for the item.
    assert int(added_claims) >= 0


async def test_added_passage_detection_failure_fails_rescan_visibly() -> None:
    """A failed fresh detection of an added passage must fail the rescan visibly.

    Governance: typed provider failures create visible unresolved outcomes, never
    a silent fallback. If detection of the added passage fails, the rescan must
    surface a typed failure rather than report a clean "0 added items" success.
    """
    async with _client() as client:
        seed = await _seed_full_revision(client)

    job_repository = SqlJobRepository()
    checkpoints = SqlSelectiveRescanRepository()
    child = _CountingChildWork(
        _ChildWorkCoordinator(
            item_lineage=SqlItemLineageAdapter(),
            job_repository=job_repository,
            detection_runtime=_FailingDetectionRuntime(),
        )
    )

    enqueued = await job_repository.enqueue(
        EnqueueJob(
            org_id=seed.org_id,
            project_id=seed.project_id,
            actor_id=seed.actor_id,
            job_type="selective_rescan",
            idempotency_key="selective_rescan:e2e-added-fail",
            payload={
                "schemaVersion": 1,
                "target": {"type": "script_version", "id": str(seed.after_version_id)},
            },
            audit_action="selective_rescan.started",
            target_type="script_version",
            target_id=seed.after_version_id,
        )
    )
    processor = _compose_rescan(job_repository, checkpoints, child=child)
    completed = await RunJobService(
        repository=job_repository,
        processors={"selective_rescan": processor},
        lease_owner="local-rescan-added-fail",
    ).run(enqueued.job.job_id, seed.org_id, seed.project_id)

    # The rescan fails visibly rather than silently reporting a clean success.
    assert completed.status is RunStatus.FAILED
    assert completed.error is not None
    assert completed.error.code == "detection_provider_unavailable"

    # The DETECTING stage is recorded as failed, and no later stage ran.
    history = await checkpoints.load_stage_history(
        org_id=seed.org_id, project_id=seed.project_id, job_id=enqueued.job.job_id
    )
    stages = dict(history)
    assert stages[RescanStage.DETECTING_AFFECTED_PASSAGES] == "failed"
    assert RescanStage.RESEARCHING_AFFECTED_ITEMS not in stages
    assert RescanStage.COMPLETED not in stages

    # No brand-new added item was materialized, and no research child exists.
    async with session_scope() as session:
        added_items = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM clearance_items "
                    "WHERE version_id = :after AND element_id = :added_element"
                ),
                {"after": str(seed.after_version_id), "added_element": str(seed.added_after)},
            )
        ).scalar_one()
        research_children = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM jobs WHERE org_id = :org_id "
                    "AND project_id = :project_id AND job_type = 'research'"
                ),
                {"org_id": str(seed.org_id), "project_id": str(seed.project_id)},
            )
        ).scalar_one()
    assert int(added_items) == 0
    assert int(research_children) == 0


async def test_child_research_reaches_affected_and_added_items_provider_free() -> None:
    async with _client() as client:
        seed = await _seed_full_revision(client)

    job_repository = SqlJobRepository()
    checkpoints = SqlSelectiveRescanRepository()
    child = _CountingChildWork(
        _ChildWorkCoordinator(
            item_lineage=SqlItemLineageAdapter(),
            job_repository=job_repository,
        )
    )
    await _run_rescan(seed, job_repository=job_repository, checkpoints=checkpoints, child=child)

    planner = _FakeResearchPlanner()
    outcomes = await _drain_child_jobs(seed, job_repository=job_repository, planner=planner)

    # Resolve the freshly detected added item id.
    async with session_scope() as session:
        added_item_id = UUID(
            str(
                (
                    await session.execute(
                        sa.text(
                            "SELECT id FROM clearance_items WHERE version_id = :after "
                            "AND element_id = :added_element"
                        ),
                        {
                            "after": str(seed.after_version_id),
                            "added_element": str(seed.added_after),
                        },
                    )
                ).scalar_one()
            )
        )

    research_outcomes = [o for o in outcomes if o[0] == "research"]
    # Research runs for BOTH the modified predecessor item and the added item.
    assert all(status is RunStatus.SUCCEEDED for _kind, status, _error in research_outcomes)
    assert set(planner.calls) == {seed.modified_item_id, added_item_id}


async def test_typed_provider_failure_is_visible_and_creates_no_fallback_claim() -> None:
    async with _client() as client:
        seed = await _seed_full_revision(client)

    job_repository = SqlJobRepository()
    checkpoints = SqlSelectiveRescanRepository()
    child = _CountingChildWork(
        _ChildWorkCoordinator(
            item_lineage=SqlItemLineageAdapter(),
            job_repository=job_repository,
        )
    )
    await _run_rescan(seed, job_repository=job_repository, checkpoints=checkpoints, child=child)

    outcomes = await _drain_child_jobs(seed, job_repository=job_repository, search=_FailingSearch())
    research_outcomes = [o for o in outcomes if o[0] == "research"]
    # Research runs for the modified predecessor AND the freshly detected added
    # item; the injected typed provider failure makes every run a visible failed
    # run, never a silent fallback.
    assert len(research_outcomes) >= 1
    assert all(status is RunStatus.FAILED for _kind, status, _error in research_outcomes)

    async with session_scope() as session:
        added_item_id = UUID(
            str(
                (
                    await session.execute(
                        sa.text(
                            "SELECT id FROM clearance_items WHERE version_id = :after "
                            "AND element_id = :added_element AND predecessor_item_id IS NULL"
                        ),
                        {
                            "after": str(seed.after_version_id),
                            "added_element": str(seed.added_after),
                        },
                    )
                ).scalar_one()
            )
        )
        modified_claims = (
            await session.execute(
                sa.text("SELECT count(*) FROM evidence_claims WHERE item_id = :item_id"),
                {"item_id": str(seed.modified_item_id)},
            )
        ).scalar_one()
        added_claims = (
            await session.execute(
                sa.text("SELECT count(*) FROM evidence_claims WHERE item_id = :item_id"),
                {"item_id": str(added_item_id)},
            )
        ).scalar_one()
    # No fabricated fallback claim for either the modified or the added item.
    assert int(modified_claims) == 0
    assert int(added_claims) == 0


async def test_reload_reconstructs_state_and_duplicates_no_work() -> None:
    async with _client() as client:
        seed = await _seed_full_revision(client)

    job_repository = SqlJobRepository()
    checkpoints = SqlSelectiveRescanRepository()

    first_child = _CountingChildWork(
        _ChildWorkCoordinator(
            item_lineage=SqlItemLineageAdapter(),
            job_repository=job_repository,
        )
    )
    job_id = await _run_rescan(
        seed, job_repository=job_repository, checkpoints=checkpoints, child=first_child
    )

    # Force a governed retry so a brand-new service instance replays the job.
    await job_repository.cancel(
        org_id=seed.org_id,
        project_id=seed.project_id,
        job_id=job_id,
        actor_id=seed.actor_id,
    )
    await job_repository.retry(
        org_id=seed.org_id,
        project_id=seed.project_id,
        job_id=job_id,
        actor_id=seed.actor_id,
    )

    replay_child = _CountingChildWork(
        _ChildWorkCoordinator(
            item_lineage=SqlItemLineageAdapter(),
            job_repository=job_repository,
        )
    )
    processor = _compose_rescan(job_repository, checkpoints, child=replay_child)
    replayed = await RunJobService(
        repository=job_repository,
        processors={"selective_rescan": processor},
        lease_owner="local-rescan-replay",
    ).run(job_id, seed.org_id, seed.project_id)
    assert replayed.status is RunStatus.SUCCEEDED

    # Completed stages are skipped on replay: no duplicate child work.
    assert replay_child.detect_calls == []
    assert replay_child.research_calls == []
    assert replay_child.added_detect_calls == []

    async with session_scope() as session:
        carried_count = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM clearance_items "
                    "WHERE version_id = :after AND lineage_kind = 'carried_forward'"
                ),
                {"after": str(seed.after_version_id)},
            )
        ).scalar_one()
        detection_children = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM jobs WHERE org_id = :org_id "
                    "AND project_id = :project_id AND job_type = 'detection'"
                ),
                {"org_id": str(seed.org_id), "project_id": str(seed.project_id)},
            )
        ).scalar_one()
        research_children = (
            await session.execute(
                sa.text(
                    "SELECT count(*) FROM jobs WHERE org_id = :org_id "
                    "AND project_id = :project_id AND job_type = 'research'"
                ),
                {"org_id": str(seed.org_id), "project_id": str(seed.project_id)},
            )
        ).scalar_one()
    # Two carried items; two detection children (the modified whole-version
    # request and the added-passage scoped detection) and two research children
    # (modified predecessor + freshly detected added item) — no duplicates on
    # replay.
    assert int(carried_count) == 2
    assert int(detection_children) == 2
    assert int(research_children) == 2

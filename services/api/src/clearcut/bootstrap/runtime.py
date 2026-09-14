"""Decoupled runtime composition root for web and standalone worker processes.

Constructs the complete domain processor graph, repositories, and provider gates
without importing the FastAPI web shell or triggering HTTP routing/lifespan side-effects.
"""
from __future__ import annotations

import asyncio
import logging
import os
import socket
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from clearcut.bootstrap.paid_providers import (
    PaidProviderGate,
    build_paid_provider_gate,
)
from clearcut.bootstrap.secrets import (
    SecretResolver,
    build_secret_resolver,
)
from clearcut.bootstrap.settings import (
    ClearcutSettings,
    DispatchAdapter,
    ModelBackend,
)
from clearcut.bootstrap.storage import (
    ObjectStoragePort,
    build_object_storage,
)
from clearcut.database import session_scope
from clearcut.detection.adapters.sql_candidate_repository import SqlCandidateRepository
from clearcut.detection.adapters.sql_rescan_lineage import SqlItemLineageAdapter
from clearcut.detection.application.run_detection_job import RunDetectionJobService
from clearcut.detection.ports.model_runtime import DetectionResult, ModelRuntimePort
from clearcut.detection.runtime_provider import get_detection_runtime
from clearcut.evaluation.adapters.sql_evaluation_repository import SqlEvaluationRepository
from clearcut.evaluation.application.evaluate import EvaluationService
from clearcut.evaluation.ports.judge import JudgePort, JudgeRequest, JudgeResult
from clearcut.evaluation.runtime_provider import get_judge_runtime
from clearcut.identity.adapters.local_identity import Argon2idIdentityProvider
from clearcut.identity.adapters.sql_repository import DatabaseIdentityRepository
from clearcut.identity.application.session_service import SessionService
from clearcut.operations.adapters.cloud_tasks import (
    CloudTasksClient,
    CloudTasksConfiguration,
    CloudTasksJobDispatcher,
    GoogleAccessToken,
)
from clearcut.operations.adapters.sql_job_repository import SqlJobRepository
from clearcut.operations.application.local_dispatcher import (
    LocalDispatchConfigurationError,
    LocalJobDispatcher,
)
from clearcut.operations.application.reconcile_jobs import (
    ReconcileJobsService,
    SqlDispatchOutbox,
)
from clearcut.operations.application.run_job import RunJobService
from clearcut.operations.domain.jobs import RunStatus
from clearcut.operations.ports.job_dispatcher import JobDispatcherPort
from clearcut.operations.ports.job_repository import EnqueueJob, JobRepositoryPort
from clearcut.organizations.adapters.sql_repository import DatabaseOrganizationRepository
from clearcut.organizations.application.bootstrap import OrganizationBootstrapService
from clearcut.projects.adapters.sql_repository import DatabaseProjectRepository
from clearcut.projects.application.project_service import ProjectService
from clearcut.rescan.adapters.sql_repository import SqlSelectiveRescanRepository
from clearcut.rescan.application.models import (
    CarriedItemMapping,
    CarryableElement,
    RescanSafeError,
)
from clearcut.rescan.application.run_rescan_job import RunSelectiveRescanJobService
from clearcut.rescan.application.start_rescan import StartSelectiveRescanService
from clearcut.rescan.ports.repository import RescanChildWorkTicket
from clearcut.research.adapters.sql_evidence_lineage import SqlEvidenceLineageAdapter
from clearcut.research.adapters.sql_research_repository import SqlResearchRepository
from clearcut.research.adapters.sql_step_receipt_repository import SqlStepReceiptRepository
from clearcut.research.adapters.strands_workflow import StrandsResearchWorkflow
from clearcut.research.application.run_research_job import RunResearchJobService
from clearcut.research.domain.extraction import ExtractRequest
from clearcut.research.domain.queries import SearchRequest
from clearcut.research.domain.snapshots import ProviderResult
from clearcut.research.ports.claim_synthesizer import (
    ClaimSynthesisRequest,
    ClaimSynthesisResult,
    ClaimSynthesizerPort,
)
from clearcut.research.ports.planner import (
    ResearchPlannerPort,
    ResearchPlanningRequest,
    ResearchPlanningResult,
)
from clearcut.research.ports.url_extract import ExtractResult, UrlExtractPort
from clearcut.research.ports.web_search import WebSearchPort
from clearcut.research.runtime_provider import (
    ResearchRuntime,
    get_claim_synthesizer,
    get_research_planner,
    resolve_research_runtime,
)
from clearcut.scripts.adapters.sql_import_repository import SqlImportRepository
from clearcut.scripts.adapters.sql_revision_plan import SqlRevisionPlanAdapter
from clearcut.scripts.application.import_script import ImportScriptService
from clearcut.scripts.domain.elements import ScriptElement
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


def _configured_api_worker_count() -> int:
    configured_workers: dict[str, int] = {}
    for variable in ("CLEARCUT_API_WORKERS", "WEB_CONCURRENCY"):
        value = os.getenv(variable)
        if value is None or not value.strip():
            continue
        try:
            configured_workers[variable] = int(value)
        except ValueError as error:
            raise LocalDispatchConfigurationError(f"{variable} must be an integer.") from error
    if len(set(configured_workers.values())) > 1:
        raise LocalDispatchConfigurationError(
            "CLEARCUT_API_WORKERS and WEB_CONCURRENCY must match when both are set."
        )
    return next(iter(configured_workers.values()), 1)


class _ConfiguredDetectionRuntime(ModelRuntimePort):
    """Resolve and gate the configured live runtime only when a job executes."""

    def __init__(self, gate: PaidProviderGate, model_provider: str = "gemini") -> None:
        self._gate = gate
        self._model_provider = model_provider
        self._runtime: ModelRuntimePort | None = None

    @property
    def requested_model(self) -> str:
        return self._resolve().requested_model

    async def detect_element(self, element: ScriptElement) -> DetectionResult:
        async with self._gate.acquire(self._model_provider):
            return await self._resolve().detect_element(element)

    def _resolve(self) -> ModelRuntimePort:
        if self._runtime is None:
            self._runtime = get_detection_runtime()
        return self._runtime


class _ConfiguredJudgeRuntime(JudgePort):
    """Resolve and gate the configured live Pro judge only when invoked."""

    def __init__(self, gate: PaidProviderGate, model_provider: str = "gemini") -> None:
        self._gate = gate
        self._model_provider = model_provider
        self._runtime: JudgePort | None = None

    @property
    def requested_model(self) -> str:
        return self._resolve().requested_model

    async def evaluate(self, request: JudgeRequest) -> JudgeResult:
        async with self._gate.acquire(self._model_provider):
            return await self._resolve().evaluate(request)

    def _resolve(self) -> JudgePort:
        if self._runtime is None:
            self._runtime = get_judge_runtime()
        return self._runtime


class _ConfiguredResearchPlanner(ResearchPlannerPort):
    """Resolve and gate the configured Flash-Lite or Bedrock planner only when research executes."""

    def __init__(self, gate: PaidProviderGate, model_provider: str = "gemini") -> None:
        self._gate = gate
        self._model_provider = model_provider
        self._runtime: ResearchPlannerPort | None = None

    @property
    def requested_model(self) -> str:
        return self._resolve().requested_model

    async def plan_research(
        self,
        request: ResearchPlanningRequest,
    ) -> ResearchPlanningResult:
        async with self._gate.acquire(self._model_provider):
            return await self._resolve().plan_research(request)

    def _resolve(self) -> ResearchPlannerPort:
        if self._runtime is None:
            self._runtime = get_research_planner()
        return self._runtime


class _ConfiguredClaimSynthesizer(ClaimSynthesizerPort):
    """Resolve and gate the configured claim synthesizer only when research executes."""

    def __init__(self, gate: PaidProviderGate, model_provider: str = "gemini") -> None:
        self._gate = gate
        self._model_provider = model_provider
        self._runtime: ClaimSynthesizerPort | None = None

    @property
    def requested_model(self) -> str:
        return self._resolve().requested_model

    async def synthesize_claim(
        self,
        request: ClaimSynthesisRequest,
    ) -> ClaimSynthesisResult:
        async with self._gate.acquire(self._model_provider):
            return await self._resolve().synthesize_claim(request)

    def _resolve(self) -> ClaimSynthesizerPort:
        if self._runtime is None:
            self._runtime = get_claim_synthesizer()
        return self._runtime


class _ConfiguredResearchRuntime(WebSearchPort, UrlExtractPort):
    """Resolve and gate configured Parallel Search/Extract on first call."""

    def __init__(
        self,
        gate: PaidProviderGate,
        secret_resolver: SecretResolver | None = None,
    ) -> None:
        self._gate = gate
        self._secret_resolver = secret_resolver
        self._runtime: ResearchRuntime | None = None

    def search(self, request: SearchRequest) -> ProviderResult:
        with self._gate.acquire("parallel"):
            return self._resolve().search.search(request)

    def extract(self, request: ExtractRequest) -> ExtractResult:
        with self._gate.acquire("parallel"):
            return self._resolve().extract.extract(request)

    def _resolve(self) -> ResearchRuntime:
        if self._runtime is None:
            self._runtime = resolve_research_runtime(secret_resolver=self._secret_resolver)
        return self._runtime


class _SqlActivePolicyGate:
    """Composition-root active-policy check for the rescan start service.

    Persistence stays out of the rescan application layer: the service reads an
    organization's active governing policy through this structural gate.
    """

    async def is_active(self, org_id: UUID) -> bool:
        async with session_scope() as session:
            row = (
                await session.execute(
                    sa.text(
                        "SELECT 1 FROM protected_configurations "
                        "WHERE org_id = :org_id AND lifecycle = 'active' LIMIT 1"
                    ),
                    {"org_id": str(org_id)},
                )
            ).first()
        return row is not None


class _SelectiveRescanItemLineageCoordinator:
    """Resolves every carryable element's predecessor items, then materializes.

    The scripts diff yields element-only carryable pairs; the orchestration passes
    the ``before_element_id`` as the join key. This coordinator resolves ALL real
    predecessor clearance items bound to that before element/version within scope
    — a single passage can hold several items — then delegates to the
    detection-owned :class:`SqlItemLineageAdapter`, which creates exactly one
    successor per predecessor. A
    carryable-by-lineage element with no predecessor item in scope is an
    unchanged/moved narrative passage that never held a clearance item (detection
    only creates items on brand/entity lines): there is nothing to carry, so it is
    skipped — never a synthesized item and never a fatal failure. Only
    item-bearing carryable elements are passed to ``materialize_carried_items``.
    """

    def __init__(self, adapter: SqlItemLineageAdapter) -> None:
        self._adapter = adapter

    async def materialize(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        script_id: UUID,
        before_version_id: UUID,
        after_version_id: UUID,
        carryable_elements: tuple[CarryableElement, ...],
    ) -> tuple[CarriedItemMapping, ...]:
        if not carryable_elements:
            return ()
        resolved: list[CarryableElement] = []
        async with session_scope() as session:
            for element in carryable_elements:
                rows = (
                    (
                        await session.execute(
                            sa.text(
                                "SELECT id, category, text FROM clearance_items "
                                "WHERE org_id = :org_id AND project_id = :project_id "
                                "AND script_id = :script_id AND version_id = :version_id "
                                "AND element_id = :element_id "
                                "ORDER BY created_at, id"
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
                    .all()
                )
                if not rows:
                    continue
                resolved.extend(
                    CarryableElement(
                        before_element_id=element.before_element_id,
                        after_element_id=element.after_element_id,
                        predecessor_item_id=UUID(str(row["id"])),
                        category=str(row["category"]),
                        text=str(row["text"]),
                    )
                    for row in rows
                )
        if not resolved:
            return ()
        return await self._adapter.materialize_carried_items(
            org_id=org_id,
            project_id=project_id,
            script_id=script_id,
            before_version_id=before_version_id,
            after_version_id=after_version_id,
            carryable_elements=tuple(resolved),
        )


class _SelectiveRescanChildWorkCoordinator:
    """Lists affected items and requests durable child rescan work.

    Child detection/research is enqueued through the shared job repository with
    stable idempotency keys so a reload or retry never duplicates a child job.
    The single local worker is never blocked on child completion: child jobs are
    durable queued requests dispatched independently.
    """

    def __init__(
        self,
        *,
        item_lineage: SqlItemLineageAdapter,
        job_repository: SqlJobRepository,
        detection_processor: RunDetectionJobService,
    ) -> None:
        self._item_lineage = item_lineage
        self._job_repository = job_repository
        self._detection_processor = detection_processor

    async def list_affected_items(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        before_version_id: UUID,
        affected_element_ids: tuple[UUID, ...],
    ) -> tuple[UUID, ...]:
        return await self._item_lineage.list_affected_items(
            org_id=org_id,
            project_id=project_id,
            before_version_id=before_version_id,
            affected_element_ids=affected_element_ids,
        )

    async def detect_added_items(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        after_version_id: UUID,
        added_after_element_ids: tuple[UUID, ...],
        actor_id: UUID,
    ) -> tuple[UUID, ...]:
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
        completed = await RunJobService(
            repository=self._job_repository,
            processors={"detection": self._detection_processor},
            lease_owner=f"local-rescan-added:{socket.gethostname()}:{os.getpid()}",
        ).run(enqueued.job.job_id, org_id, project_id)
        if completed.status is not RunStatus.SUCCEEDED:
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
        return await self._added_item_ids(
            org_id=org_id,
            project_id=project_id,
            after_version_id=after_version_id,
            added_after_element_ids=added_after_element_ids,
        )

    @staticmethod
    async def _added_item_ids(
        *,
        org_id: UUID,
        project_id: UUID,
        after_version_id: UUID,
        added_after_element_ids: tuple[UUID, ...],
    ) -> tuple[UUID, ...]:
        return await _SelectiveRescanChildWorkCoordinator._scoped_detected_item_ids(
            org_id=org_id,
            project_id=project_id,
            after_version_id=after_version_id,
            element_ids=added_after_element_ids,
        )

    @staticmethod
    async def _scoped_detected_item_ids(
        *,
        org_id: UUID,
        project_id: UUID,
        after_version_id: UUID,
        element_ids: tuple[UUID, ...],
    ) -> tuple[UUID, ...]:
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
                        "element_ids": [str(element_id) for element_id in element_ids],
                    },
                )
            ).scalars()
            return tuple(UUID(str(item_id)) for item_id in rows)

    async def detect_modified_items(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        after_version_id: UUID,
        modified_after_element_ids: tuple[UUID, ...],
        actor_id: UUID,
    ) -> tuple[UUID, ...]:
        if not modified_after_element_ids:
            return ()
        key = f"selective_rescan:detect-modified:{after_version_id}"
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
                    "elementIds": sorted(
                        str(element_id) for element_id in modified_after_element_ids
                    ),
                },
                audit_action="detection.started",
                target_type="script_version",
                target_id=after_version_id,
            )
        )
        completed = await RunJobService(
            repository=self._job_repository,
            processors={"detection": self._detection_processor},
            lease_owner=f"local-rescan-modified:{socket.gethostname()}:{os.getpid()}",
        ).run(enqueued.job.job_id, org_id, project_id)
        if completed.status is not RunStatus.SUCCEEDED:
            error = completed.error
            raise RescanSafeError(
                code=error.code if error is not None else "modified_detection_failed",
                message=(
                    error.message
                    if error is not None
                    else "Fresh detection of modified passages did not complete."
                ),
                retryable=error.retryable if error is not None else True,
            )
        return await self._scoped_detected_item_ids(
            org_id=org_id,
            project_id=project_id,
            after_version_id=after_version_id,
            element_ids=modified_after_element_ids,
        )

    async def request_research(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        after_version_id: UUID,
        affected_item_ids: tuple[UUID, ...],
        actor_id: UUID,
    ) -> tuple[RescanChildWorkTicket, ...]:
        tickets: list[RescanChildWorkTicket] = []
        for item_id in affected_item_ids:
            key = f"selective_rescan:research:{item_id}"
            await self._job_repository.enqueue(
                EnqueueJob(
                    org_id=org_id,
                    project_id=project_id,
                    actor_id=actor_id,
                    job_type="research",
                    idempotency_key=key,
                    payload={
                        "schemaVersion": 1,
                        "target": {"type": "clearance_item", "id": str(item_id)},
                    },
                    audit_action="research.started",
                    target_type="clearance_item",
                    target_id=item_id,
                )
            )
            tickets.append(RescanChildWorkTicket(item_id=item_id, idempotency_key=key))
        return tuple(tickets)


_LOCAL_JOB_DRAIN_BATCH_SIZE = 8


async def _drain_due_local_jobs(
    repository: SqlJobRepository, runner: RunJobService
) -> None:
    """Execute every due queued/awaiting-retry job through the local runner."""
    try:
        due = await repository.dequeue_due_local_jobs(_LOCAL_JOB_DRAIN_BATCH_SIZE)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Local job queue drain listing failed.")
        return
    for job in due:
        try:
            await runner.run(job.job_id, job.org_id, job.project_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Local job drain execution failed: job_id=%s job_type=%s",
                job.job_id,
                job.job_type,
            )


async def _local_job_maintenance_loop(
    repository: SqlJobRepository,
    runner: RunJobService,
    *,
    interval_seconds: float,
) -> None:
    """Recover expired local leases and drain due queued work until shutdown."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await repository.recover_interrupted_local_jobs()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Periodic local job lease recovery failed.")
        await _drain_due_local_jobs(repository, runner)


@dataclass(frozen=True)
class RuntimeComposition:
    """Shared, immutable graph of domain processors, repositories, and gates."""

    # 1. Canonical Seam Required by PROJECT.md
    settings: ClearcutSettings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    job_repository: JobRepositoryPort
    storage_adapter: ObjectStoragePort
    secret_resolver: SecretResolver
    provider_gate: PaidProviderGate
    detection_runtime: ModelRuntimePort
    research_planner: ResearchPlannerPort
    claim_synthesizer: ClaimSynthesizerPort
    judge_runtime: JudgePort

    # 2. Shared Domain Processors & Services
    candidate_repository: SqlCandidateRepository
    evaluation_repository: SqlEvaluationRepository
    evaluation_service: EvaluationService
    run_detection_job: RunDetectionJobService
    research_repository: SqlResearchRepository
    research_runtime: Any
    run_research_job: RunResearchJobService
    rescan_repository: SqlSelectiveRescanRepository
    revision_plan_adapter: SqlRevisionPlanAdapter
    item_lineage_adapter: SqlItemLineageAdapter
    rescan_item_lineage: _SelectiveRescanItemLineageCoordinator
    rescan_evidence_lineage: SqlEvidenceLineageAdapter
    rescan_child_work: _SelectiveRescanChildWorkCoordinator
    active_policy_gate: _SqlActivePolicyGate
    run_rescan_job: RunSelectiveRescanJobService
    start_selective_rescan_service: StartSelectiveRescanService
    job_runner: RunJobService
    dispatch_outbox: SqlDispatchOutbox
    job_dispatcher: JobDispatcherPort
    reconcile_jobs_service: ReconcileJobsService
    identity_repo: DatabaseIdentityRepository
    identity_provider: Argon2idIdentityProvider
    session_service: SessionService
    org_repo: DatabaseOrganizationRepository
    org_service: OrganizationBootstrapService
    project_repo: DatabaseProjectRepository
    project_service: ProjectService
    import_repository: SqlImportRepository
    import_script_service: ImportScriptService

    # 3. Optional Cloud Configuration & Tunables
    cloud_tasks_config: CloudTasksConfiguration | None = None
    task_client: CloudTasksClient | None = None
    local_job_recovery_interval_seconds: float = 30.0

    @property
    def storage(self) -> ObjectStoragePort:
        """Alias for backwards compatibility with app.state.storage."""
        return self.storage_adapter

    @property
    def paid_provider_gate(self) -> PaidProviderGate:
        """Alias for backwards compatibility with app.state.paid_provider_gate."""
        return self.provider_gate


def build_runtime_composition(
    settings: ClearcutSettings,
    *,
    engine: AsyncEngine | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    storage: ObjectStoragePort | None = None,
    storage_adapter: ObjectStoragePort | None = None,
    secret_resolver: SecretResolver | None = None,
    job_dispatcher: JobDispatcherPort | None = None,
) -> RuntimeComposition:
    """Construct the complete domain dependency graph without starting FastAPI."""
    if engine is None or session_factory is None:
        from clearcut.database import DATABASE_URL as CONFIGURED_DATABASE_URL
        from clearcut.database import AsyncSessionLocal as default_session_factory  # noqa: N813
        from clearcut.database import engine as default_engine

        if engine is None:
            if settings.database.url != SecretStr(CONFIGURED_DATABASE_URL):
                raise RuntimeError(
                    "Configured database URL does not match the process database engine."
                )
            engine = default_engine
        if session_factory is None:
            session_factory = default_session_factory

    resolved_storage = storage if storage is not None else storage_adapter
    if resolved_storage is None:
        resolved_storage = build_object_storage(settings.storage)
    storage = resolved_storage
    if secret_resolver is None:
        secret_resolver = build_secret_resolver(
            settings.secrets,
            project_id=getattr(settings.storage, "project_id", None)
            or getattr(settings.dispatch, "project_id", None),
            aws_region=getattr(settings, "aws_region", None),
        )
    paid_provider_gate = build_paid_provider_gate(settings)

    identity_repo = DatabaseIdentityRepository()
    identity_provider = Argon2idIdentityProvider()
    session_service = SessionService(
        repository=identity_repo,
        identity_provider=identity_provider,
    )
    org_repo = DatabaseOrganizationRepository()
    org_service = OrganizationBootstrapService(repository=org_repo)
    project_repo = DatabaseProjectRepository()
    project_service = ProjectService(repository=project_repo)
    import_repository = SqlImportRepository()
    import_script_service = ImportScriptService(
        repository=import_repository,
        storage=storage,
    )

    job_repository = SqlJobRepository()
    candidate_repository = SqlCandidateRepository()
    evaluation_repository = SqlEvaluationRepository()
    model_provider = settings.model_backend.value
    detection_runtime = _ConfiguredDetectionRuntime(paid_provider_gate, model_provider=model_provider)
    judge_runtime = _ConfiguredJudgeRuntime(paid_provider_gate, model_provider=model_provider)
    evaluation_service = EvaluationService(
        judge=judge_runtime,
        repository=evaluation_repository,
    )
    run_detection_job = RunDetectionJobService(
        repository=candidate_repository,
        job_repository=job_repository,
        runtime=detection_runtime,
        evaluation=evaluation_service,
    )

    research_repository = SqlResearchRepository()
    research_planner = _ConfiguredResearchPlanner(paid_provider_gate, model_provider=model_provider)
    research_synthesizer = _ConfiguredClaimSynthesizer(paid_provider_gate, model_provider=model_provider)
    research_runtime = _ConfiguredResearchRuntime(
        paid_provider_gate, secret_resolver=secret_resolver
    )
    active_orchestrator_provider = os.getenv("CLEARCUT_RESEARCH_ORCHESTRATOR_PROVIDER") or (
        "bedrock" if settings.model_backend == ModelBackend.BEDROCK else "gemini"
    )
    step_receipt_repo = SqlStepReceiptRepository()
    strands_workflow = StrandsResearchWorkflow(
        repository=research_repository,
        step_receipt_repo=step_receipt_repo,
        search=research_runtime,
        extract=research_runtime,
        gate=paid_provider_gate,
        planner=research_planner,
        synthesizer=research_synthesizer,
        evaluation=evaluation_service,
        provider_name=active_orchestrator_provider,
    )
    run_research_job = RunResearchJobService(
        repository=research_repository,
        planner=research_planner,
        synthesizer=research_synthesizer,
        search=research_runtime,
        extract=research_runtime,
        evaluation=evaluation_service,
        workflow=strands_workflow,
    )

    rescan_repository = SqlSelectiveRescanRepository()
    revision_plan_adapter = SqlRevisionPlanAdapter(import_repository)
    item_lineage_adapter = SqlItemLineageAdapter()
    rescan_item_lineage = _SelectiveRescanItemLineageCoordinator(item_lineage_adapter)
    rescan_evidence_lineage = SqlEvidenceLineageAdapter()
    rescan_child_work = _SelectiveRescanChildWorkCoordinator(
        item_lineage=item_lineage_adapter,
        job_repository=job_repository,
        detection_processor=run_detection_job,
    )
    run_rescan_job = RunSelectiveRescanJobService(
        revision_plan=revision_plan_adapter,
        materialize_items=rescan_item_lineage,
        carry_evidence=rescan_evidence_lineage,
        child_work=rescan_child_work,
        repository=rescan_repository,
        job_repository=job_repository,
    )
    active_policy_gate = _SqlActivePolicyGate()
    start_selective_rescan_service = StartSelectiveRescanService(
        revision_plan=revision_plan_adapter,
        provider_gate=paid_provider_gate,
        active_policy=active_policy_gate,
        job_repository=job_repository,
    )

    job_runner = RunJobService(
        repository=job_repository,
        processors={
            "detection": run_detection_job,
            "research": run_research_job,
            "selective_rescan": run_rescan_job,
        },
        lease_owner=f"local:{socket.gethostname()}:{os.getpid()}",
    )
    dispatch_outbox = SqlDispatchOutbox(repository=job_repository)

    cloud_tasks_config: CloudTasksConfiguration | None = None
    task_client: CloudTasksClient | None = None

    if job_dispatcher is not None:
        reconcile_jobs_service = ReconcileJobsService(
            outbox=dispatch_outbox,
            client=None,  # type: ignore[arg-type]
            repository=job_repository,
        )
    elif settings.dispatch.adapter is DispatchAdapter.LOCAL:
        job_dispatcher = LocalJobDispatcher(
            runner=job_runner,
            mode="local" if settings.dispatch.enabled else "disabled",
            worker_count=_configured_api_worker_count(),
        )
        reconcile_jobs_service = ReconcileJobsService(
            outbox=dispatch_outbox,
            client=None,  # type: ignore[arg-type]
            repository=job_repository,
        )
    elif settings.dispatch.adapter is DispatchAdapter.CLOUD_TASKS:
        cloud_tasks_config = CloudTasksConfiguration(
            project_id=settings.dispatch.project_id or "",
            location=settings.dispatch.location or "",
            queue=settings.dispatch.queue or "",
            target_url=settings.dispatch.target_url or "",
            audience=settings.dispatch.audience or "",
            service_account_email=settings.dispatch.service_account_email or "",
        )
        task_client = CloudTasksClient(
            configuration=cloud_tasks_config,
            credentials=GoogleAccessToken(),
        )
        job_dispatcher = CloudTasksJobDispatcher(
            client=task_client,
            outbox=dispatch_outbox,
        )
        reconcile_jobs_service = ReconcileJobsService(
            outbox=dispatch_outbox,
            client=task_client,
            repository=job_repository,
        )
    else:
        raise RuntimeError(
            f"Dispatch adapter {settings.dispatch.adapter.value!r} is not implemented yet."
        )

    local_job_recovery_interval_seconds = float(
        os.getenv("CLEARCUT_LOCAL_JOB_RECOVERY_INTERVAL_SECONDS", "30")
    )

    return RuntimeComposition(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        job_repository=job_repository,
        storage_adapter=storage,
        secret_resolver=secret_resolver,
        provider_gate=paid_provider_gate,
        detection_runtime=detection_runtime,
        research_planner=research_planner,
        claim_synthesizer=research_synthesizer,
        judge_runtime=judge_runtime,
        candidate_repository=candidate_repository,
        evaluation_repository=evaluation_repository,
        evaluation_service=evaluation_service,
        run_detection_job=run_detection_job,
        research_repository=research_repository,
        research_runtime=research_runtime,
        run_research_job=run_research_job,
        rescan_repository=rescan_repository,
        revision_plan_adapter=revision_plan_adapter,
        item_lineage_adapter=item_lineage_adapter,
        rescan_item_lineage=rescan_item_lineage,
        rescan_evidence_lineage=rescan_evidence_lineage,
        rescan_child_work=rescan_child_work,
        active_policy_gate=active_policy_gate,
        run_rescan_job=run_rescan_job,
        start_selective_rescan_service=start_selective_rescan_service,
        job_runner=job_runner,
        dispatch_outbox=dispatch_outbox,
        job_dispatcher=job_dispatcher,
        reconcile_jobs_service=reconcile_jobs_service,
        identity_repo=identity_repo,
        identity_provider=identity_provider,
        session_service=session_service,
        org_repo=org_repo,
        org_service=org_service,
        project_repo=project_repo,
        project_service=project_service,
        import_repository=import_repository,
        import_script_service=import_script_service,
        cloud_tasks_config=cloud_tasks_config,
        task_client=task_client,
        local_job_recovery_interval_seconds=local_job_recovery_interval_seconds,
    )


@asynccontextmanager
async def web_lifespan(app: Any):
    """Recover expired local work at startup and while this web process remains alive."""
    recovery_task: asyncio.Task[None] | None = None
    dispatcher = getattr(app.state, "job_dispatcher", None)
    if dispatcher is not None and getattr(dispatcher, "mode", None) == "local":
        repository = app.state.job_repository
        runner = app.state.job_runner
        interval_seconds = getattr(
            app.state, "local_job_recovery_interval_seconds", 30.0
        )
        if interval_seconds <= 0:
            raise RuntimeError("Local job recovery interval must be positive.")
        await repository.recover_interrupted_local_jobs()
        await _drain_due_local_jobs(repository, runner)
        recovery_task = asyncio.create_task(
            _local_job_maintenance_loop(
                repository,
                runner,
                interval_seconds=interval_seconds,
            ),
            name="local-job-lease-recovery",
        )
    try:
        yield
    finally:
        if recovery_task is not None:
            recovery_task.cancel()
            with suppress(asyncio.CancelledError):
                await recovery_task


@asynccontextmanager
async def worker_lifespan(
    composition: RuntimeComposition,
    *,
    interval_seconds: float | None = None,
):
    """Manage standalone background worker lifecycle without FastAPI dependencies."""
    recovery_task: asyncio.Task[None] | None = None
    interval = (
        interval_seconds
        if interval_seconds is not None
        else composition.local_job_recovery_interval_seconds
    )
    if interval <= 0:
        raise RuntimeError("Worker recovery interval must be positive.")

    if getattr(composition.job_dispatcher, "mode", None) == "local":
        await composition.job_repository.recover_interrupted_local_jobs()
        await _drain_due_local_jobs(composition.job_repository, composition.job_runner)
        recovery_task = asyncio.create_task(
            _local_job_maintenance_loop(
                composition.job_repository,
                composition.job_runner,
                interval_seconds=interval,
            ),
            name="worker-local-job-lease-recovery",
        )
    try:
        yield
    finally:
        if recovery_task is not None:
            recovery_task.cancel()
            with suppress(asyncio.CancelledError):
                await recovery_task

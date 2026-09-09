"""FastAPI application shell entry point."""

import asyncio
import logging
import os
import socket
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import SecretStr
from starlette.exceptions import HTTPException as StarletteHTTPException

from clearcut.bootstrap.container import build_application
from clearcut.bootstrap.paid_providers import PaidProviderGate, build_paid_provider_gate
from clearcut.bootstrap.secrets import build_secret_resolver
from clearcut.bootstrap.settings import (
    ClearcutSettings,
    DispatchAdapter,
)
from clearcut.bootstrap.storage import build_object_storage
from clearcut.collaboration.delivery.http import router as collaboration_router
from clearcut.collaboration.delivery.notifications_http import router as notifications_router
from clearcut.database import DATABASE_URL as CONFIGURED_DATABASE_URL
from clearcut.database import session_scope
from clearcut.decisions.delivery.http import router as decisions_router
from clearcut.delivery_errors import error_response
from clearcut.detection.adapters.sql_candidate_repository import SqlCandidateRepository
from clearcut.detection.adapters.sql_rescan_lineage import SqlItemLineageAdapter
from clearcut.detection.application.run_detection_job import RunDetectionJobService
from clearcut.detection.delivery.http import router as detection_router
from clearcut.detection.ports.model_runtime import DetectionResult, ModelRuntimePort
from clearcut.detection.runtime_provider import get_detection_runtime
from clearcut.evaluation.adapters.sql_evaluation_repository import SqlEvaluationRepository
from clearcut.evaluation.application.evaluate import EvaluationService
from clearcut.evaluation.delivery.configuration_http import router as configuration_router
from clearcut.evaluation.delivery.http import router as evaluation_router
from clearcut.evaluation.delivery.learning_http import router as learning_router
from clearcut.evaluation.ports.judge import JudgePort, JudgeRequest, JudgeResult
from clearcut.evaluation.runtime_provider import get_judge_runtime
from clearcut.export.delivery.http import router as export_router
from clearcut.identity.adapters.local_identity import Argon2idIdentityProvider
from clearcut.identity.adapters.sql_repository import DatabaseIdentityRepository
from clearcut.identity.application.session_service import SessionService
from clearcut.identity.delivery.http import router as identity_router
from clearcut.items.delivery.http import router as items_router
from clearcut.monitoring.delivery.http import router as monitoring_router
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
from clearcut.operations.delivery.http import router as operations_router
from clearcut.operations.delivery.tasks_http import router as tasks_router
from clearcut.operations.domain.jobs import RunStatus
from clearcut.operations.ports.job_repository import EnqueueJob
from clearcut.organizations.adapters.sql_repository import DatabaseOrganizationRepository
from clearcut.organizations.application.bootstrap import OrganizationBootstrapService
from clearcut.organizations.delivery.http import router as organization_router
from clearcut.organizations.delivery.settings_http import router as organization_settings_router
from clearcut.projects.adapters.sql_repository import DatabaseProjectRepository
from clearcut.projects.application.project_service import ProjectService
from clearcut.records.delivery.http import router as records_router
from clearcut.rescan.adapters.sql_repository import SqlSelectiveRescanRepository
from clearcut.rescan.application.models import (
    CarriedItemMapping,
    CarryableElement,
    RescanSafeError,
)
from clearcut.rescan.application.run_rescan_job import RunSelectiveRescanJobService
from clearcut.rescan.application.start_rescan import StartSelectiveRescanService
from clearcut.rescan.delivery.http import router as rescan_router
from clearcut.rescan.ports.repository import RescanChildWorkTicket
from clearcut.research.adapters.sql_evidence_lineage import SqlEvidenceLineageAdapter
from clearcut.research.adapters.sql_research_repository import SqlResearchRepository
from clearcut.research.application.run_research_job import RunResearchJobService
from clearcut.research.delivery.http import router as research_router
from clearcut.research.domain.extraction import ExtractRequest
from clearcut.research.domain.queries import SearchRequest
from clearcut.research.domain.snapshots import ProviderResult
from clearcut.research.ports.planner import (
    ResearchPlannerPort,
    ResearchPlanningRequest,
    ResearchPlanningResult,
)
from clearcut.research.ports.url_extract import ExtractResult, UrlExtractPort
from clearcut.research.ports.web_search import WebSearchPort
from clearcut.research.runtime_provider import (
    ResearchRuntime,
    get_research_planner,
    get_research_runtime,
)
from clearcut.scripts.adapters.sql_import_repository import SqlImportRepository
from clearcut.scripts.adapters.sql_revision_plan import SqlRevisionPlanAdapter
from clearcut.scripts.application.import_script import ImportScriptService
from clearcut.scripts.delivery.http import router as scripts_router
from clearcut.scripts.domain.elements import ScriptElement
from clearcut.static_delivery import install_same_origin_routes

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

    def __init__(self, gate: PaidProviderGate) -> None:
        self._gate = gate
        self._runtime: ModelRuntimePort | None = None

    @property
    def requested_model(self) -> str:
        with self._gate.acquire("gemini"):
            return self._resolve().requested_model

    async def detect_element(self, element: ScriptElement) -> DetectionResult:
        async with self._gate.acquire("gemini"):
            return await self._resolve().detect_element(element)

    def _resolve(self) -> ModelRuntimePort:
        if self._runtime is None:
            self._runtime = get_detection_runtime()
        return self._runtime


class _ConfiguredJudgeRuntime(JudgePort):
    """Resolve and gate the configured live Pro judge only when invoked."""

    def __init__(self, gate: PaidProviderGate) -> None:
        self._gate = gate
        self._runtime: JudgePort | None = None

    @property
    def requested_model(self) -> str:
        with self._gate.acquire("gemini"):
            return self._resolve().requested_model

    async def evaluate(self, request: JudgeRequest) -> JudgeResult:
        async with self._gate.acquire("gemini"):
            return await self._resolve().evaluate(request)

    def _resolve(self) -> JudgePort:
        if self._runtime is None:
            self._runtime = get_judge_runtime()
        return self._runtime


class _ConfiguredResearchPlanner(ResearchPlannerPort):
    """Resolve and gate the configured Flash-Lite planner only when research executes."""

    def __init__(self, gate: PaidProviderGate) -> None:
        self._gate = gate
        self._runtime: ResearchPlannerPort | None = None

    @property
    def requested_model(self) -> str:
        with self._gate.acquire("gemini"):
            return self._resolve().requested_model

    async def plan_research(
        self,
        request: ResearchPlanningRequest,
    ) -> ResearchPlanningResult:
        async with self._gate.acquire("gemini"):
            return await self._resolve().plan_research(request)

    def _resolve(self) -> ResearchPlannerPort:
        if self._runtime is None:
            self._runtime = get_research_planner()
        return self._runtime


class _ConfiguredResearchRuntime(WebSearchPort, UrlExtractPort):
    """Resolve and gate configured Parallel Search/Extract on first call."""

    def __init__(self, gate: PaidProviderGate) -> None:
        self._gate = gate
        self._runtime: ResearchRuntime | None = None

    def search(self, request: SearchRequest) -> ProviderResult:
        with self._gate.acquire("parallel"):
            return self._resolve().search.search(request)

    def extract(self, request: ExtractRequest) -> ExtractResult:
        with self._gate.acquire("parallel"):
            return self._resolve().extract.extract(request)

    def _resolve(self) -> ResearchRuntime:
        if self._runtime is None:
            self._runtime = get_research_runtime()
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
    """Resolves each carryable element's predecessor item, then materializes.

    The scripts diff yields element-only carryable pairs; the orchestration passes
    the ``before_element_id`` as the join key. This coordinator resolves the real
    predecessor clearance item bound to that before element/version within scope,
    then delegates to the detection-owned :class:`SqlItemLineageAdapter`. A
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
                    # A carryable-by-lineage element is an exact/contextual
                    # unchanged or moved passage. Detection only creates clearance
                    # items on brand/entity lines, so an unchanged NARRATIVE line
                    # legitimately has no predecessor item in the correct scope:
                    # there is simply nothing to carry, so skip it. This is NOT a
                    # scope violation (the org/project/script/before-version scope
                    # is enforced in the query above); the row just does not exist.
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
        if not resolved:
            # No carryable element carried a predecessor item: nothing to
            # materialize. Return an empty mapping rather than calling the adapter
            # with an empty set.
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
        # Enqueue a detection child scoped to EXACTLY the added after-version
        # elements (never the whole version) with a stable idempotency key, then
        # run it to completion so the resulting brand-new unresolved items exist
        # before research is requested. Replays reuse the same durable job and the
        # detection fingerprint unique constraint, so no duplicate item is
        # created and the same item ids are returned.
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
        # A failed scoped detection must surface as a visible, typed rescan
        # failure — never a silent "0 added items" that advances the rescan to
        # completion and drops the added passages from clearance and research.
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
                        "element_ids": [str(element_id) for element_id in added_after_element_ids],
                    },
                )
            ).scalars()
            return tuple(UUID(str(item_id)) for item_id in rows)

    async def request_detection(
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        after_version_id: UUID,
        affected_item_ids: tuple[UUID, ...],
        actor_id: UUID,
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
        self,
        *,
        org_id: UUID,
        project_id: UUID,
        after_version_id: UUID,
        affected_item_ids: tuple[UUID, ...],
        actor_id: UUID,
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
        self,
        *,
        kind: str,
        org_id: UUID,
        project_id: UUID,
        after_version_id: UUID,
        affected_item_ids: tuple[UUID, ...],
        actor_id: UUID,
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


async def _recover_expired_local_jobs_periodically(
    repository: SqlJobRepository,
    *,
    interval_seconds: float,
) -> None:
    """Recover bounded batches of expired local leases until lifespan cancellation."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await repository.recover_interrupted_local_jobs()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Periodic local job lease recovery failed.")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Recover expired local work at startup and while this process remains alive."""
    recovery_task: asyncio.Task[None] | None = None
    if _app.state.job_dispatcher.mode == "local":
        await _app.state.job_repository.recover_interrupted_local_jobs()
        interval_seconds = _app.state.local_job_recovery_interval_seconds
        if interval_seconds <= 0:
            raise RuntimeError("Local job recovery interval must be positive.")
        recovery_task = asyncio.create_task(
            _recover_expired_local_jobs_periodically(
                _app.state.job_repository,
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


async def handle_http_exception(
    _request: Request,
    error: StarletteHTTPException,
) -> JSONResponse:
    """Normalize framework and dependency failures to the public error contract."""
    code_by_status = {
        status.HTTP_400_BAD_REQUEST: "validation_failed",
        status.HTTP_401_UNAUTHORIZED: "authentication_required",
        status.HTTP_403_FORBIDDEN: "permission_denied",
        status.HTTP_404_NOT_FOUND: "not_found",
        status.HTTP_405_METHOD_NOT_ALLOWED: "validation_failed",
        status.HTTP_409_CONFLICT: "conflict",
        status.HTTP_429_TOO_MANY_REQUESTS: "rate_limited",
        status.HTTP_503_SERVICE_UNAVAILABLE: "capability_unavailable",
    }
    message = error.detail if isinstance(error.detail, str) else "Request failed."
    return error_response(
        status_code=error.status_code,
        code=code_by_status.get(error.status_code, "internal_error"),
        message=message,
        retryable=error.status_code
        in {
            status.HTTP_429_TOO_MANY_REQUESTS,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        },
        headers=error.headers,
    )


async def handle_request_validation_error(
    _request: Request,
    _error: RequestValidationError,
) -> JSONResponse:
    """Normalize framework validation failures to the public error contract."""
    return error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code="validation_failed",
        message="Request validation failed.",
    )


async def handle_unexpected_exception(
    request: Request,
    error: Exception,
) -> JSONResponse:
    """Redact unexpected failures while retaining server-side trace correlation."""
    response = error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="internal_error",
        message="An internal error prevented the request from completing.",
        retryable=True,
    )
    logger.error(
        "Unhandled API error request_id=%s method=%s path=%s",
        response.headers["x-request-id"],
        request.method,
        request.url.path,
        exc_info=(type(error), error, error.__traceback__),
    )
    return response


def create_app(settings: ClearcutSettings) -> FastAPI:
    """Compose a FastAPI application from validated deployment settings."""
    application_container = build_application(settings)
    if settings.database.url != SecretStr(CONFIGURED_DATABASE_URL):
        raise RuntimeError("Configured database URL does not match the process database engine.")
    if settings.dispatch.adapter not in {DispatchAdapter.LOCAL, DispatchAdapter.CLOUD_TASKS}:
        raise RuntimeError(
            f"Dispatch adapter {settings.dispatch.adapter.value!r} is not implemented yet."
        )

    app = FastAPI(
        title="ClearCut API",
        version="0.1.0",
        description="Screenplay pre-clearance research desk and evidence workspace API",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url="/api/redoc",
        lifespan=lifespan,
    )
    app.add_exception_handler(
        StarletteHTTPException,
        handle_http_exception,  # pyright: ignore[reportArgumentType]
    )
    app.add_exception_handler(
        RequestValidationError,
        handle_request_validation_error,  # pyright: ignore[reportArgumentType]
    )
    app.add_exception_handler(Exception, handle_unexpected_exception)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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
    storage = build_object_storage(settings.storage)
    secret_resolver = build_secret_resolver(
        settings.secrets,
        project_id=getattr(settings.storage, "project_id", None)
        or getattr(settings.dispatch, "project_id", None),
    )
    paid_provider_gate = build_paid_provider_gate(settings)
    import_repository = SqlImportRepository()
    import_script_service = ImportScriptService(
        repository=import_repository,
        storage=storage,
    )

    job_repository = SqlJobRepository()
    candidate_repository = SqlCandidateRepository()
    evaluation_repository = SqlEvaluationRepository()
    detection_runtime = _ConfiguredDetectionRuntime(paid_provider_gate)
    judge_runtime = _ConfiguredJudgeRuntime(paid_provider_gate)
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
    research_planner = _ConfiguredResearchPlanner(paid_provider_gate)
    research_runtime = _ConfiguredResearchRuntime(paid_provider_gate)
    run_research_job = RunResearchJobService(
        repository=research_repository,
        planner=research_planner,
        search=research_runtime,
        extract=research_runtime,
        evaluation=evaluation_service,
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
    start_selective_rescan_service = StartSelectiveRescanService(
        revision_plan=revision_plan_adapter,
        provider_gate=paid_provider_gate,
        active_policy=_SqlActivePolicyGate(),
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
    if settings.dispatch.adapter is DispatchAdapter.LOCAL:
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
        app.state.cloud_tasks_config = cloud_tasks_config
        app.state.task_client = task_client

    app.state.settings = settings
    app.state.deployment_summary = application_container.summary
    app.state.application_container = application_container
    app.state.identity_repo = identity_repo
    app.state.identity_provider = identity_provider
    app.state.session_service = session_service
    app.state.org_repo = org_repo
    app.state.org_service = org_service
    app.state.project_repo = project_repo
    app.state.project_service = project_service
    app.state.storage = storage
    app.state.secret_resolver = secret_resolver
    app.state.paid_provider_gate = paid_provider_gate
    app.state.import_repository = import_repository
    app.state.import_script_service = import_script_service
    app.state.job_repository = job_repository
    app.state.candidate_repository = candidate_repository
    app.state.evaluation_repository = evaluation_repository
    app.state.run_detection_job = run_detection_job
    app.state.research_repository = research_repository
    app.state.research_planner = research_planner
    app.state.research_runtime = research_runtime
    app.state.run_research_job = run_research_job
    app.state.rescan_repository = rescan_repository
    app.state.run_rescan_job = run_rescan_job
    app.state.start_selective_rescan_service = start_selective_rescan_service
    app.state.job_runner = job_runner
    app.state.job_dispatcher = job_dispatcher
    app.state.dispatch_outbox = dispatch_outbox
    app.state.reconcile_jobs_service = reconcile_jobs_service
    app.state.local_job_recovery_interval_seconds = float(
        os.getenv("CLEARCUT_LOCAL_JOB_RECOVERY_INTERVAL_SECONDS", "30")
    )

    app.include_router(identity_router)
    app.include_router(organization_router)
    app.include_router(scripts_router)
    app.include_router(items_router)
    app.include_router(decisions_router)
    app.include_router(collaboration_router)
    app.include_router(detection_router)
    app.include_router(research_router)
    app.include_router(rescan_router)
    app.include_router(operations_router)
    app.include_router(tasks_router)
    app.include_router(monitoring_router)
    app.include_router(records_router)
    app.include_router(evaluation_router)
    app.include_router(configuration_router)
    app.include_router(learning_router)
    app.include_router(notifications_router)
    app.include_router(organization_settings_router)
    app.include_router(export_router)

    async def healthz() -> JSONResponse:
        return JSONResponse(
            content={
                "status": "ok",
                "timestamp": datetime.now(UTC).isoformat(),
                "version": "0.1.0",
                "deployment": {
                    "profile": app.state.deployment_summary.profile,
                    "databaseConfigured": app.state.deployment_summary.database_configured,
                    "storageAdapter": app.state.deployment_summary.storage_adapter,
                    "dispatchAdapter": app.state.deployment_summary.dispatch_adapter,
                    "dispatchEnabled": app.state.deployment_summary.dispatch_enabled,
                    "authenticationAdapter": (app.state.deployment_summary.authentication_adapter),
                    "secretBackend": app.state.deployment_summary.secret_backend,
                    "paidProvidersEnabled": list(
                        app.state.deployment_summary.paid_providers_enabled
                    ),
                },
                "jobDispatch": {
                    "mode": app.state.job_dispatcher.mode,
                    "durable": app.state.job_dispatcher.durable,
                },
            }
        )

    app.add_api_route("/healthz", healthz, methods=["GET"])
    app.add_api_route("/api/v1/healthz", healthz, methods=["GET"])

    static_delivery = settings.static_delivery
    configured_static_paths = (
        static_delivery.site_dist is not None or static_delivery.workspace_dist is not None
    )
    if not static_delivery.enabled and configured_static_paths:
        raise RuntimeError(
            "Static delivery paths cannot be configured while static delivery is disabled."
        )
    if static_delivery.enabled:
        if static_delivery.site_dist is None or static_delivery.workspace_dist is None:
            raise RuntimeError(
                "Enabled static delivery requires both site and workspace distribution paths."
            )
        install_same_origin_routes(
            app,
            site_dist=static_delivery.site_dist,
            workspace_dist=static_delivery.workspace_dist,
        )

    return app


app = create_app(ClearcutSettings.from_environment())

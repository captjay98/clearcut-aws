"""FastAPI application shell entry point."""

import asyncio
import logging
import os
import socket
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import SecretStr
from starlette.exceptions import HTTPException as StarletteHTTPException

from clearcut.bootstrap.container import build_application
from clearcut.bootstrap.settings import ClearcutSettings, StorageAdapter
from clearcut.collaboration.delivery.http import router as collaboration_router
from clearcut.database import DATABASE_URL as CONFIGURED_DATABASE_URL
from clearcut.decisions.delivery.http import router as decisions_router
from clearcut.delivery_errors import error_response
from clearcut.detection.adapters.sql_candidate_repository import SqlCandidateRepository
from clearcut.detection.application.run_detection_job import RunDetectionJobService
from clearcut.detection.delivery.http import router as detection_router
from clearcut.detection.ports.model_runtime import DetectionResult, ModelRuntimePort
from clearcut.detection.runtime_provider import get_detection_runtime
from clearcut.evaluation.adapters.sql_evaluation_repository import SqlEvaluationRepository
from clearcut.evaluation.application.evaluate import EvaluationService
from clearcut.evaluation.delivery.http import router as evaluation_router
from clearcut.evaluation.ports.judge import JudgePort, JudgeRequest, JudgeResult
from clearcut.evaluation.runtime_provider import get_judge_runtime
from clearcut.export.delivery.http import router as export_router
from clearcut.identity.adapters.local_identity import Argon2idIdentityProvider
from clearcut.identity.adapters.sql_repository import DatabaseIdentityRepository
from clearcut.identity.application.session_service import SessionService
from clearcut.identity.delivery.http import router as identity_router
from clearcut.items.delivery.http import router as items_router
from clearcut.monitoring.delivery.http import router as monitoring_router
from clearcut.operations.adapters.sql_job_repository import SqlJobRepository
from clearcut.operations.application.local_dispatcher import (
    LocalDispatchConfigurationError,
    LocalJobDispatcher,
)
from clearcut.operations.application.run_job import RunJobService
from clearcut.operations.delivery.http import router as operations_router
from clearcut.organizations.adapters.sql_repository import DatabaseOrganizationRepository
from clearcut.organizations.application.bootstrap import OrganizationBootstrapService
from clearcut.organizations.delivery.http import router as organization_router
from clearcut.projects.adapters.sql_repository import DatabaseProjectRepository
from clearcut.projects.application.project_service import ProjectService
from clearcut.records.delivery.http import router as records_router
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
from clearcut.scripts.adapters.filesystem_storage import FilesystemObjectStorage
from clearcut.scripts.adapters.sql_import_repository import SqlImportRepository
from clearcut.scripts.application.import_script import ImportScriptService
from clearcut.scripts.delivery.http import router as scripts_router
from clearcut.scripts.domain.elements import ScriptElement

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
            raise LocalDispatchConfigurationError(
                f"{variable} must be an integer."
            ) from error
    if len(set(configured_workers.values())) > 1:
        raise LocalDispatchConfigurationError(
            "CLEARCUT_API_WORKERS and WEB_CONCURRENCY must match when both are set."
        )
    return next(iter(configured_workers.values()), 1)


class _ConfiguredDetectionRuntime(ModelRuntimePort):
    """Resolve and cache the configured live runtime only when a job executes."""

    def __init__(self) -> None:
        self._runtime: ModelRuntimePort | None = None

    @property
    def requested_model(self) -> str:
        return self._resolve().requested_model

    async def detect_element(self, element: ScriptElement) -> DetectionResult:
        return await self._resolve().detect_element(element)

    def _resolve(self) -> ModelRuntimePort:
        if self._runtime is None:
            self._runtime = get_detection_runtime()
        return self._runtime


class _ConfiguredJudgeRuntime(JudgePort):
    """Resolve and cache the configured live Pro judge only when invoked."""

    def __init__(self) -> None:
        self._runtime: JudgePort | None = None

    @property
    def requested_model(self) -> str:
        return self._resolve().requested_model

    async def evaluate(self, request: JudgeRequest) -> JudgeResult:
        return await self._resolve().evaluate(request)

    def _resolve(self) -> JudgePort:
        if self._runtime is None:
            self._runtime = get_judge_runtime()
        return self._runtime


class _ConfiguredResearchPlanner(ResearchPlannerPort):
    """Resolve the configured Flash-Lite planner only when research executes."""

    def __init__(self) -> None:
        self._runtime: ResearchPlannerPort | None = None

    @property
    def requested_model(self) -> str:
        return self._resolve().requested_model

    async def plan_research(
        self,
        request: ResearchPlanningRequest,
    ) -> ResearchPlanningResult:
        return await self._resolve().plan_research(request)

    def _resolve(self) -> ResearchPlannerPort:
        if self._runtime is None:
            self._runtime = get_research_planner()
        return self._runtime


class _ConfiguredResearchRuntime(WebSearchPort, UrlExtractPort):
    """Resolve and cache configured Parallel Search/Extract on first call."""

    def __init__(self) -> None:
        self._runtime: ResearchRuntime | None = None

    def search(self, request: SearchRequest) -> ProviderResult:
        return self._resolve().search.search(request)

    def extract(self, request: ExtractRequest) -> ExtractResult:
        return self._resolve().extract.extract(request)

    def _resolve(self) -> ResearchRuntime:
        if self._runtime is None:
            self._runtime = get_research_runtime()
        return self._runtime


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
        raise RuntimeError(
            "Configured database URL does not match the process database engine."
        )
    if settings.storage.adapter is not StorageAdapter.FILESYSTEM:
        raise RuntimeError(
            f"Storage adapter {settings.storage.adapter.value!r} is not implemented yet."
        )
    if settings.storage.path is None:
        raise RuntimeError("Filesystem storage requires a configured path.")

    app = FastAPI(
        title="ClearCut API",
        version="0.1.0",
        description="Screenplay pre-clearance research desk and evidence workspace API",
        lifespan=lifespan,
    )
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(RequestValidationError, handle_request_validation_error)
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
    storage = FilesystemObjectStorage(settings.storage.path)
    import_repository = SqlImportRepository()
    import_script_service = ImportScriptService(
        repository=import_repository,
        storage=storage,
    )

    job_repository = SqlJobRepository()
    candidate_repository = SqlCandidateRepository()
    evaluation_repository = SqlEvaluationRepository()
    detection_runtime = _ConfiguredDetectionRuntime()
    judge_runtime = _ConfiguredJudgeRuntime()
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
    research_planner = _ConfiguredResearchPlanner()
    research_runtime = _ConfiguredResearchRuntime()
    run_research_job = RunResearchJobService(
        repository=research_repository,
        planner=research_planner,
        search=research_runtime,
        extract=research_runtime,
        evaluation=evaluation_service,
    )
    job_runner = RunJobService(
        repository=job_repository,
        processors={
            "detection": run_detection_job,
            "research": run_research_job,
        },
        lease_owner=f"local:{socket.gethostname()}:{os.getpid()}",
    )
    job_dispatcher = LocalJobDispatcher(
        runner=job_runner,
        mode="local" if settings.dispatch.enabled else "disabled",
        worker_count=_configured_api_worker_count(),
    )

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
    app.state.job_runner = job_runner
    app.state.job_dispatcher = job_dispatcher
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
    app.include_router(operations_router)
    app.include_router(monitoring_router)
    app.include_router(records_router)
    app.include_router(evaluation_router)
    app.include_router(export_router)

    async def healthz() -> JSONResponse:
        return JSONResponse(
            content={
                "status": "ok",
                "timestamp": datetime.now(UTC).isoformat(),
                "version": "0.1.0",
                "jobDispatch": {
                    "mode": app.state.job_dispatcher.mode,
                    "durable": app.state.job_dispatcher.durable,
                },
            }
        )

    app.add_api_route("/healthz", healthz, methods=["GET"])
    app.add_api_route("/api/v1/healthz", healthz, methods=["GET"])

    web_dist_env = os.getenv("WEB_DIST_PATH")
    if web_dist_env and Path(web_dist_env).is_dir():
        web_dist_dir = Path(web_dist_env)
        assets_dir = web_dist_dir / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        async def serve_spa(full_path: str):
            if (
                full_path.startswith("api/")
                or full_path.startswith("docs")
                or full_path.startswith("openapi.json")
                or full_path.startswith("healthz")
                or full_path == "healthz"
            ):
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            target = web_dist_dir / full_path
            if target.is_file():
                return FileResponse(target)
            index_path = web_dist_dir / "index.html"
            if index_path.is_file():
                return FileResponse(index_path)
            return JSONResponse(
                {"detail": "SPA index.html not found"},
                status_code=404,
            )

        app.add_api_route("/{full_path:path}", serve_spa, methods=["GET"])

    return app


app = create_app(ClearcutSettings.from_environment())

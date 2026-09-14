"""FastAPI application shell entry point."""

import logging
from datetime import UTC, datetime

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from clearcut.bootstrap.container import build_application
from clearcut.bootstrap.runtime import (
    RuntimeComposition,
    _configured_api_worker_count,
    _ConfiguredClaimSynthesizer,
    _ConfiguredDetectionRuntime,
    _ConfiguredJudgeRuntime,
    _ConfiguredResearchPlanner,
    _ConfiguredResearchRuntime,
    _drain_due_local_jobs,
    _local_job_maintenance_loop,
    _SelectiveRescanChildWorkCoordinator,
    _SelectiveRescanItemLineageCoordinator,
    _SqlActivePolicyGate,
    build_runtime_composition,
    web_lifespan,
    worker_lifespan,
)
from clearcut.bootstrap.settings import (
    ClearcutSettings,
)
from clearcut.collaboration.delivery.http import router as collaboration_router
from clearcut.collaboration.delivery.notifications_http import router as notifications_router
from clearcut.decisions.delivery.http import rewrites_router
from clearcut.decisions.delivery.http import router as decisions_router
from clearcut.delivery_errors import error_response
from clearcut.detection.delivery.http import router as detection_router
from clearcut.detection.runtime_provider import (
    DetectionRuntimeNotConfiguredError,
    ProviderConfigurationError,
    ProviderUnavailableError,
    get_detection_runtime,
)
from clearcut.evaluation.delivery.configuration_http import router as configuration_router
from clearcut.evaluation.delivery.http import router as evaluation_router
from clearcut.evaluation.delivery.learning_http import router as learning_router
from clearcut.evaluation.runtime_provider import (
    JudgeRuntimeNotConfiguredError,
    get_judge_runtime,
)
from clearcut.export.delivery.http import router as export_router
from clearcut.identity.delivery.http import router as identity_router
from clearcut.items.delivery.http import router as items_router
from clearcut.monitoring.delivery.http import reviews_router as monitoring_reviews_router
from clearcut.monitoring.delivery.http import router as monitoring_router
from clearcut.operations.delivery.http import router as operations_router
from clearcut.operations.delivery.tasks_http import router as tasks_router
from clearcut.organizations.delivery.http import router as organization_router
from clearcut.organizations.delivery.settings_http import router as organization_settings_router
from clearcut.records.delivery.http import router as records_router
from clearcut.rescan.delivery.http import router as rescan_router
from clearcut.research.delivery.http import router as research_router
from clearcut.research.runtime_provider import (
    ResearchRuntimeNotConfiguredError,
    get_claim_synthesizer,
    get_research_planner,
    get_research_runtime,
)
from clearcut.scripts.delivery.http import router as scripts_router
from clearcut.static_delivery import install_same_origin_routes

__all__ = [
    "DetectionRuntimeNotConfiguredError",
    "JudgeRuntimeNotConfiguredError",
    "ProviderConfigurationError",
    "ProviderUnavailableError",
    "ResearchRuntimeNotConfiguredError",
    "RuntimeComposition",
    "_ConfiguredClaimSynthesizer",
    "_ConfiguredDetectionRuntime",
    "_ConfiguredJudgeRuntime",
    "_ConfiguredResearchPlanner",
    "_ConfiguredResearchRuntime",
    "_SelectiveRescanChildWorkCoordinator",
    "_SelectiveRescanItemLineageCoordinator",
    "_SqlActivePolicyGate",
    "_configured_api_worker_count",
    "_drain_due_local_jobs",
    "_local_job_maintenance_loop",
    "app",
    "build_runtime_composition",
    "create_app",
    "get_claim_synthesizer",
    "get_detection_runtime",
    "get_judge_runtime",
    "get_research_planner",
    "get_research_runtime",
    "handle_provider_unavailable_error",
    "lifespan",
    "web_lifespan",
    "worker_lifespan",
]

logger = logging.getLogger(__name__)

lifespan = web_lifespan


async def handle_provider_unavailable_error(
    _request: Request,
    error: ProviderUnavailableError,
) -> JSONResponse:
    """Normalize domain provider unavailable errors to public HTTP 503 error contract."""
    return error_response(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code="capability_unavailable",
        message=str(error),
        retryable=True,
    )



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
    composition = build_runtime_composition(settings)

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
    app.add_exception_handler(
        ProviderUnavailableError,
        handle_provider_unavailable_error,  # pyright: ignore[reportArgumentType]
    )
    app.add_exception_handler(Exception, handle_unexpected_exception)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.runtime_composition = composition
    app.state.composition = composition
    app.state.settings = composition.settings
    app.state.deployment_summary = application_container.summary
    app.state.application_container = application_container
    app.state.identity_repo = composition.identity_repo
    app.state.identity_provider = composition.identity_provider
    app.state.session_service = composition.session_service
    app.state.org_repo = composition.org_repo
    app.state.org_service = composition.org_service
    app.state.project_repo = composition.project_repo
    app.state.project_service = composition.project_service
    app.state.storage = composition.storage_adapter
    app.state.secret_resolver = composition.secret_resolver
    app.state.paid_provider_gate = composition.provider_gate
    app.state.active_policy_gate = composition.active_policy_gate
    app.state.import_repository = composition.import_repository
    app.state.import_script_service = composition.import_script_service
    app.state.job_repository = composition.job_repository
    app.state.candidate_repository = composition.candidate_repository
    app.state.evaluation_repository = composition.evaluation_repository
    app.state.run_detection_job = composition.run_detection_job
    app.state.research_repository = composition.research_repository
    app.state.research_planner = composition.research_planner
    app.state.research_runtime = composition.research_runtime
    app.state.run_research_job = composition.run_research_job
    app.state.rescan_repository = composition.rescan_repository
    app.state.run_rescan_job = composition.run_rescan_job
    app.state.start_selective_rescan_service = composition.start_selective_rescan_service
    app.state.job_runner = composition.job_runner
    app.state.job_dispatcher = composition.job_dispatcher
    app.state.dispatch_outbox = composition.dispatch_outbox
    app.state.reconcile_jobs_service = composition.reconcile_jobs_service
    app.state.cloud_tasks_config = composition.cloud_tasks_config
    app.state.task_client = composition.task_client
    app.state.local_job_recovery_interval_seconds = composition.local_job_recovery_interval_seconds


    app.include_router(identity_router)
    app.include_router(organization_router)
    app.include_router(scripts_router)
    app.include_router(items_router)
    app.include_router(decisions_router)
    app.include_router(rewrites_router)
    app.include_router(collaboration_router)
    app.include_router(detection_router)
    app.include_router(research_router)
    app.include_router(rescan_router)
    app.include_router(operations_router)
    app.include_router(tasks_router)
    app.include_router(monitoring_router)
    app.include_router(monitoring_reviews_router)
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

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

import sqlalchemy as sa
import uuid6
from clearcut.commanding.errors import (
    CommandForbiddenError,
    CommandNotFoundError,
    CommandValidationError,
)
from clearcut.database import session_scope
from clearcut.delivery_errors import error_response
from clearcut.identity.delivery.scope import get_request_scope
from clearcut.monitoring.adapters.sql_review_repository import SqlMonitoringReviewRepository
from clearcut.monitoring.application.review_change import MonitoringReviewService
from clearcut.monitoring.domain.materiality import MonitoringReviewAction
from clearcut.monitoring.ports.review_repository import PendingChangeSignal
from clearcut.organizations.delivery.http import verify_csrf_origin
from fastapi import APIRouter, Path, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(prefix="/api/v1/organizations/{org_id}/projects/{project_id}", tags=["monitoring"])

# The canonical monitoring read/review operations declare their path parameters
# as ``orgId``/``projectId``/``reviewId`` (camelCase) in the contract, so they are
# mounted on a dedicated router with those exact path segments and operation ids
# rather than the snake_case prefix above, keeping mounted parity with the spec.
reviews_router = APIRouter(tags=["monitoring"])

OrgIdParam = Annotated[str, Path(alias="orgId")]
ProjectIdParam = Annotated[str, Path(alias="projectId")]
ReviewIdParam = Annotated[str, Path(alias="reviewId")]

_MONITORED_SOURCES_PATH = (
    "/api/v1/organizations/{orgId}/projects/{projectId}/monitored-sources"
)
_MONITORING_CHANGES_PATH = (
    "/api/v1/organizations/{orgId}/projects/{projectId}/monitoring-changes"
)
_REVIEW_CHANGE_PATH = (
    "/api/v1/organizations/{orgId}/projects/{projectId}"
    "/monitoring-reviews/{reviewId}:recordDecision"
)

_review_repository = SqlMonitoringReviewRepository()
_review_service = MonitoringReviewService(repository=_review_repository)

# The contract exposes a neutral review vocabulary (accepted/rejected/escalated);
# the domain records the operational triage action. This is the single mapping
# boundary between the two, kept explicit so neither side silently drifts.
_DECISION_TO_ACTION: dict[str, MonitoringReviewAction] = {
    "accepted": MonitoringReviewAction.KEEP_WITH_FOLLOW_UP,
    "rejected": MonitoringReviewAction.REOPEN,
    "escalated": MonitoringReviewAction.REFER,
}

_LIST_MONITORED_SOURCES = sa.text(
    """
    SELECT id, item_id, cadence, watch_kind, target_url, query_text, created_at
    FROM monitoring_watches
    WHERE org_id = :org_id AND project_id = :project_id
    ORDER BY created_at DESC
    """
)


class SetCadenceBody(BaseModel):
    cadence: str = "weekly"


class ReviewMonitoringChangeBody(BaseModel):
    """Contract-aligned request body for ``reviewMonitoringChange``."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["accepted", "rejected", "escalated"]
    rationale: Annotated[str, Field(min_length=1)] = "Monitoring change reviewed."


@router.get("/monitoring-cadence")
@router.get("/watch")
async def get_watch_config(org_id: str, project_id: str, request: Request) -> dict:
    await get_request_scope(request, org_id=org_id, project_id=project_id)
    now = datetime.now(UTC)
    next_run = now + timedelta(days=7)
    return {
        "data": {
            "cadence": "weekly",
            "lastRunAt": (now - timedelta(days=1)).isoformat(),
            "nextRunAt": next_run.isoformat(),
            "status": "active",
            "monitoredSourcesCount": 38,
        }
    }


@router.post("/monitoring-cadence")
@router.post("/watch")
async def update_watch_config(
    org_id: str, project_id: str, body: SetCadenceBody, request: Request
) -> dict:
    verify_csrf_origin(request)
    await get_request_scope(request, org_id=org_id, project_id=project_id)
    now = datetime.now(UTC)
    return {
        "data": {
            "cadence": body.cadence,
            "status": "active",
            "updatedAt": now.isoformat(),
        }
    }


@router.post("/monitoring:runCheck", status_code=status.HTTP_201_CREATED)
async def run_monitoring_check(
    org_id: str, project_id: str, request: Request
) -> dict:
    verify_csrf_origin(request)
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)
    job_id = uuid6.uuid7()
    now = datetime.now(UTC)

    return {
        "data": {
            "jobId": str(job_id),
            "orgId": str(scope.org_id),
            "projectId": str(scope.project_id),
            "status": "completed",
            "signalsDetected": 0,
            "checkedAt": now.isoformat(),
        },
        "meta": {"requestId": "req_monitor_check"},
    }


@reviews_router.get(_MONITORED_SOURCES_PATH, operation_id="listMonitoredSources")
async def list_monitored_sources(
    org_id: OrgIdParam, project_id: ProjectIdParam, request: Request
) -> dict:
    """List the monitored sources (watches) for a project.

    Reads real ``monitoring_watches`` rows scoped to the authenticated
    organization-and-project, replacing the previously hardcoded count with the
    persisted watch inventory.
    """
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)
    async with session_scope() as session:
        rows = (
            (
                await session.execute(
                    _LIST_MONITORED_SOURCES,
                    {"org_id": str(scope.org_id), "project_id": str(scope.project_id)},
                )
            )
            .mappings()
            .all()
        )
    sources = [
        {
            "watchId": str(row["id"]),
            "itemId": str(row["item_id"]),
            "cadence": str(row["cadence"]),
            "watchKind": str(row["watch_kind"]),
            "targetUrl": row["target_url"],
            "queryText": row["query_text"],
            "createdAt": row["created_at"].isoformat()
            if hasattr(row["created_at"], "isoformat")
            else str(row["created_at"]),
        }
        for row in rows
    ]
    return {
        "data": sources,
        "meta": {"requestId": f"req_{uuid6.uuid7()}", "totalCount": len(sources)},
    }


@reviews_router.get(_MONITORING_CHANGES_PATH, operation_id="listMonitoringChanges")
async def list_monitoring_changes(
    org_id: OrgIdParam, project_id: ProjectIdParam, request: Request
) -> dict:
    """List the pending, persisted change signals for a project.

    Each entry carries its ``reviewId`` (the delta's own id, the value a client
    posts back to ``reviewMonitoringChange``) plus the change detail, so a
    reviewer can triage a durable signal rather than a fabricated placeholder.
    """
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)
    assert scope.org_id is not None
    assert scope.project_id is not None
    async with session_scope() as session:
        pending = await _review_repository.list_pending(
            session,
            org_id=scope.org_id,
            project_id=scope.project_id,
        )
    changes = [_change_payload(signal) for signal in pending]
    return {
        "data": changes,
        "meta": {"requestId": f"req_{uuid6.uuid7()}", "totalCount": len(changes)},
    }


@reviews_router.post(_REVIEW_CHANGE_PATH, operation_id="reviewMonitoringChange")
async def review_monitoring_change(
    org_id: OrgIdParam,
    project_id: ProjectIdParam,
    review_id: ReviewIdParam,
    body: ReviewMonitoringChangeBody,
    request: Request,
) -> JSONResponse:
    """Record a governed decision on a pending monitoring change signal.

    The decision and its authoritative audit event commit in one transaction via
    the persistent review service; there is no in-memory dict. ``reviewId`` is
    the pending delta's id surfaced by ``listMonitoringChanges``.
    """
    verify_csrf_origin(request)
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)
    assert scope.org_id is not None
    assert scope.project_id is not None

    parsed_delta_id = _parse_uuid(review_id)
    if parsed_delta_id is None:
        # An unparseable review id is a resource that cannot exist in scope:
        # neutral not-found parity, never a distinguishing validation error.
        return _envelope_for(CommandNotFoundError())

    action = _DECISION_TO_ACTION[body.decision]

    try:
        async with session_scope() as session:
            # The pending delta records its own item scope; load it so the
            # decision and audit reference the exact item the signal belongs to.
            pending = await _review_repository.list_pending(
                session,
                org_id=scope.org_id,
                project_id=scope.project_id,
            )
            target = next(
                (signal for signal in pending if signal.delta_id == parsed_delta_id),
                None,
            )
            if target is None:
                raise CommandNotFoundError()
            decision = await _review_service.review_monitoring_delta(
                session,
                org_id=scope.org_id,
                project_id=scope.project_id,
                item_id=target.item_id,
                delta_id=parsed_delta_id,
                actor_id=scope.user_id,
                actor_role=scope.role or "",
                action=action,
                rationale=body.rationale,
            )
    except (
        CommandForbiddenError,
        CommandNotFoundError,
        CommandValidationError,
    ) as error:
        return _envelope_for(error)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "data": {
                "reviewId": str(decision.review_id),
                "decision": body.decision,
            },
            "meta": {"requestId": f"req_{decision.review_id}"},
        },
    )


def _change_payload(signal: PendingChangeSignal) -> dict[str, object]:
    """Project a pending change signal onto the ``MonitoringChange`` response."""
    data: dict[str, object] = {
        "reviewId": str(signal.delta_id),
        "deltaId": str(signal.delta_id),
        "itemId": str(signal.item_id),
        "signalType": signal.signal_type.value,
        "changeKind": signal.change_kind,
        "changeSummary": signal.change_summary,
        "detectedAt": signal.detected_at.isoformat()
        if hasattr(signal.detected_at, "isoformat")
        else str(signal.detected_at),
    }
    if signal.watch_id is not None:
        data["watchId"] = str(signal.watch_id)
    if signal.prior_excerpt is not None:
        data["priorExcerpt"] = signal.prior_excerpt
    if signal.current_excerpt is not None:
        data["currentExcerpt"] = signal.current_excerpt
    return data


def _parse_uuid(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


def _envelope_for(error: Exception) -> JSONResponse:
    if isinstance(error, CommandForbiddenError):
        return error_response(
            status_code=status.HTTP_403_FORBIDDEN,
            code="permission_denied",
            message=error.message,
        )
    if isinstance(error, CommandNotFoundError):
        return error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="not_found",
            message=error.message,
        )
    message = getattr(error, "message", "The review inputs were invalid.")
    return error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code="validation_failed",
        message=message,
    )

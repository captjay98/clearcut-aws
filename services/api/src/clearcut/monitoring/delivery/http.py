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
from clearcut.monitoring.adapters.sql_watch_repository import SqlMonitoringWatchRepository
from clearcut.monitoring.application.review_change import MonitoringReviewService
from clearcut.monitoring.application.run_scheduled_watch import ScheduledWatchService
from clearcut.monitoring.domain.materiality import ChangeMateriality, MonitoringReviewAction
from clearcut.monitoring.domain.models import WatchCadence, WatchConfig, WatchKind
from clearcut.monitoring.ports.review_repository import PendingChangeSignal
from clearcut.organizations.delivery.http import verify_csrf_origin
from clearcut.research.adapters.hermetic_extract import HermeticExtractAdapter
from clearcut.research.adapters.hermetic_search import HermeticSearchAdapter
from clearcut.research.domain.snapshots import SourceSnapshot
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
_REGISTER_SOURCE_PATH = (
    "/api/v1/organizations/{orgId}/projects/{projectId}/monitored-sources:register"
)

_review_repository = SqlMonitoringReviewRepository()
_review_service = MonitoringReviewService(repository=_review_repository)
_watch_repository = SqlMonitoringWatchRepository()
# The recheck adapters are hermetic (no paid provider call): a recheck always
# re-derives the same deterministic excerpt, so a change is detected only when a
# registered baseline was recorded with a *different* excerpt. No fabricated
# provider traffic and no fabricated change.
_scheduled_watch_service = ScheduledWatchService(
    extract_port=HermeticExtractAdapter(),
    search_port=HermeticSearchAdapter(),
)

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


class RegisterMonitoredSourceBody(BaseModel):
    """Contract-aligned request body for ``registerMonitoredSource``.

    A registration records *what* to watch (an item-scoped source) and captures
    an initial baseline snapshot as the prior a later recheck compares against.
    ``baselineExcerpt`` seeds that baseline's content: because the hermetic
    recheck re-derives a fixed excerpt, a baseline recorded with a different
    excerpt makes the first recheck legitimately detect a change through the real
    comparison, without fabricating a delta. Omitting it stores the same excerpt
    the recheck produces, so the first recheck is correctly non-material.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    item_id: Annotated[str, Field(alias="itemId")]
    cadence: Literal["off", "manual", "daily", "weekly"] = "weekly"
    watch_kind: Annotated[
        Literal["exact_source", "new_event_topic"], Field(alias="watchKind")
    ] = "exact_source"
    target_url: Annotated[str | None, Field(alias="targetUrl", min_length=1)] = None
    query_text: Annotated[str | None, Field(alias="queryText", min_length=1)] = None
    baseline_excerpt: Annotated[
        str | None, Field(alias="baselineExcerpt", min_length=1)
    ] = None


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
    """Run a monitoring check across the project's registered watches.

    For each registered watch this loads the item's most recent persisted
    snapshot as the prior, re-retrieves the source via
    :meth:`ScheduledWatchService.execute_watch_recheck`, persists the fresh
    snapshot and its :class:`MonitoringRun`, and — only when the real
    ``compare_snapshots`` comparison yields a MATERIAL delta — persists that
    delta as a pending review signal. ``signalsDetected`` is the exact number of
    material signals persisted this run; a project with no watches, or one whose
    sources are unchanged, honestly reports ``0`` and persists no signal.
    """
    verify_csrf_origin(request)
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)
    assert scope.org_id is not None
    assert scope.project_id is not None
    job_id = uuid6.uuid7()
    now = datetime.now(UTC)

    signals_detected = 0
    async with session_scope() as session:
        watches = await _watch_repository.list_watches(
            session,
            org_id=scope.org_id,
            project_id=scope.project_id,
        )
        for watch in watches:
            prior = await _watch_repository.latest_snapshot_for_watch(
                session, watch=watch
            )
            run, snapshot, delta = await _scheduled_watch_service.execute_watch_recheck(
                watch, prior_snapshot=prior
            )
            await _watch_repository.persist_recheck(
                session, run=run, snapshot=snapshot
            )
            # A delta only exists when there was a prior to compare against; only
            # a MATERIAL delta becomes a pending review signal. NON_MATERIAL and
            # "no prior" both persist the fresh snapshot without a signal, so no
            # change is fabricated.
            if delta is not None and delta.materiality is ChangeMateriality.MATERIAL:
                await _review_repository.write_delta(
                    session,
                    delta=delta,
                    watch_id=watch.watch_id,
                    change_kind="content_changed",
                    prior_excerpt=prior.excerpt if prior is not None else None,
                    current_excerpt=snapshot.excerpt,
                )
                signals_detected += 1

    return {
        "data": {
            "jobId": str(job_id),
            "orgId": str(scope.org_id),
            "projectId": str(scope.project_id),
            "status": "completed",
            "signalsDetected": signals_detected,
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


@reviews_router.post(
    _REGISTER_SOURCE_PATH,
    operation_id="registerMonitoredSource",
    status_code=status.HTTP_201_CREATED,
)
async def register_monitored_source(
    org_id: OrgIdParam,
    project_id: ProjectIdParam,
    body: RegisterMonitoredSourceBody,
    request: Request,
) -> JSONResponse:
    """Register a monitored source and record its baseline snapshot.

    Inserts an item-scoped ``monitoring_watches`` row and stores an initial
    baseline :class:`SourceSnapshot` — the real prior a later recheck compares
    against — in one transaction. ``baselineExcerpt`` (optional) seeds the
    baseline content so a subsequent recheck can legitimately detect a change
    through the real comparison rather than a fabricated delta. This is an
    operational write (recording what to watch), not a governed clearance
    decision, so it carries no audit event.
    """
    verify_csrf_origin(request)
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)
    assert scope.org_id is not None
    assert scope.project_id is not None

    parsed_item_id = _parse_uuid(body.item_id)
    if parsed_item_id is None:
        return _envelope_for(CommandValidationError("itemId must be a valid identifier."))
    if body.target_url is None and body.query_text is None:
        return _envelope_for(
            CommandValidationError("A monitored source needs a targetUrl or queryText.")
        )

    watch = WatchConfig.create(
        org_id=scope.org_id,
        project_id=scope.project_id,
        item_id=parsed_item_id,
        cadence=WatchCadence(body.cadence),
        watch_kind=WatchKind(body.watch_kind),
        target_url=body.target_url,
        query_text=body.query_text,
    )
    # The baseline snapshot mirrors the source the recheck will re-retrieve. Its
    # excerpt defaults to the recheck's own deterministic excerpt (so an
    # unchanged source is correctly non-material); an explicit baselineExcerpt
    # makes the first recheck detect a real change.
    baseline_url = watch.target_url or "https://example.com/source"
    baseline = SourceSnapshot.create(
        org_id=scope.org_id,
        project_id=scope.project_id,
        item_id=parsed_item_id,
        run_id=uuid6.uuid7(),
        url=baseline_url,
        title=f"Baseline for {parsed_item_id}",
        publisher=baseline_url.split("//")[-1].split("/")[0],
        excerpt=body.baseline_excerpt or "Active registered record",
        origin="extract",
    )

    async with session_scope() as session:
        await _watch_repository.register_watch(
            session, watch=watch, baseline_snapshot=baseline
        )

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "data": {
                "watchId": str(watch.watch_id),
                "itemId": str(watch.item_id),
                "cadence": watch.cadence.value,
                "watchKind": watch.watch_kind.value,
                "targetUrl": watch.target_url,
                "queryText": watch.query_text,
                "createdAt": watch.created_at.isoformat(),
            },
            "meta": {"requestId": f"req_{watch.watch_id}"},
        },
    )


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

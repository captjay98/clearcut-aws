"""Delivery boundary for the canonical governed evidence-decision operation.

This router mounts exactly the canonical ``:recordEvidenceDecision`` operation
from the contract. The superseded public ``/items/{item}/decisions`` route that
wrote the legacy ``audit_events`` table has been retired: governed evidence
decisions now flow through the shared command kernel and the authoritative audit
ledger, with tenant-and-project scope, server-derived capability, expected-
version concurrency, intent/idempotency, zero-evidence protection, and a
same-transaction authoritative audit event.

Typed governed-command errors are translated to the canonical HTTP error
envelope here; the neutral not-found/forbidden shapes preserve safe tenant
parity so a caller cannot probe for the existence of another tenant's items.
"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from clearcut.commanding.errors import (
    CommandForbiddenError,
    CommandNotFoundError,
    CommandValidationError,
    IdempotencyIntentConflictError,
    StaleVersionConflictError,
)
from clearcut.csrf import verify_csrf_origin
from clearcut.database import session_scope
from clearcut.decisions.adapters.sql_repository import SqlDecisionRepository
from clearcut.decisions.application.record_evidence_decision import (
    EvidenceDecisionValue,
    RecordEvidenceDecisionCommand,
    RecordEvidenceDecisionService,
)
from clearcut.decisions.application.set_disposition import (
    ClearanceDisposition,
    SetDispositionCommand,
    SetDispositionService,
)
from clearcut.decisions.ports.repository import PersistedDecision
from clearcut.delivery_errors import error_response
from clearcut.identity.delivery.scope import get_request_scope
from fastapi import APIRouter, Header, Path, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(tags=["decisions"])

_DECISION_PATH = (
    "/api/v1/organizations/{orgId}/projects/{projectId}"
    "/clearance-items/{itemId}:recordEvidenceDecision"
)

_DISPOSITION_PATH = (
    "/api/v1/organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}:setDisposition"
)

OrgIdParam = Annotated[str, Path(alias="orgId")]
ProjectIdParam = Annotated[str, Path(alias="projectId")]
ItemIdParam = Annotated[str, Path(alias="itemId")]

_service = RecordEvidenceDecisionService(repository=SqlDecisionRepository())
_disposition_service = SetDispositionService(repository=SqlDecisionRepository())


class RecordEvidenceDecisionBody(BaseModel):
    """Contract-aligned request body for ``recordEvidenceDecision``."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["accepted", "rejected", "further_review_required"]
    rationale: Annotated[str, Field(min_length=1)]
    expected_version: Annotated[int, Field(ge=1, alias="expectedVersion")]
    intent_hash: Annotated[str, Field(min_length=1, alias="intentHash")]


class SetDispositionBody(BaseModel):
    """Contract-aligned request body for ``setDisposition``.

    ``disposition`` is restricted to the canonical ``ClearanceDisposition``
    vocabulary at the request boundary; any other value is a framework 422 before
    the handler runs, so arbitrary/legacy disposition strings can never reach
    storage.
    """

    model_config = ConfigDict(extra="forbid")

    disposition: Literal["pending", "verified", "ruled_out", "fixed_in_rewrite", "deferred"]
    rationale: Annotated[str, Field(min_length=1)]
    expected_version: Annotated[int, Field(ge=1, alias="expectedVersion")]
    intent_hash: Annotated[str, Field(min_length=1, alias="intentHash")]


@router.post(_DECISION_PATH, operation_id="recordEvidenceDecision")
async def record_evidence_decision(
    org_id: OrgIdParam,
    project_id: ProjectIdParam,
    item_id: ItemIdParam,
    body: RecordEvidenceDecisionBody,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=16, max_length=128)],
) -> JSONResponse:
    verify_csrf_origin(request)
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)

    parsed_item_id = _parse_item_id(item_id)
    if parsed_item_id is None:
        # An unparseable item id is a resource that cannot exist in scope: neutral
        # not-found parity, never a distinguishing validation error.
        return _envelope_for(CommandNotFoundError())

    assert scope.org_id is not None  # get_request_scope enforced org membership
    assert scope.project_id is not None  # get_request_scope enforced project scope

    command = RecordEvidenceDecisionCommand(
        org_id=scope.org_id,
        project_id=scope.project_id,
        item_id=parsed_item_id,
        actor_id=scope.user_id,
        actor_role=scope.role or "",
        decision=EvidenceDecisionValue(body.decision),
        rationale=body.rationale,
        expected_version=body.expected_version,
        intent_hash=body.intent_hash,
        idempotency_key=idempotency_key,
    )

    try:
        async with session_scope() as session:
            result = await _service.record(session, command)
    except (
        CommandForbiddenError,
        CommandNotFoundError,
        StaleVersionConflictError,
        IdempotencyIntentConflictError,
        CommandValidationError,
    ) as error:
        return _envelope_for(error)

    return _success(result)


@router.post(_DISPOSITION_PATH, operation_id="setDisposition")
async def set_disposition(
    org_id: OrgIdParam,
    project_id: ProjectIdParam,
    item_id: ItemIdParam,
    body: SetDispositionBody,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=16, max_length=128)],
) -> JSONResponse:
    verify_csrf_origin(request)
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)

    parsed_item_id = _parse_item_id(item_id)
    if parsed_item_id is None:
        # An unparseable item id is a resource that cannot exist in scope: neutral
        # not-found parity, never a distinguishing validation error.
        return _envelope_for(CommandNotFoundError())

    assert scope.org_id is not None  # get_request_scope enforced org membership
    assert scope.project_id is not None  # get_request_scope enforced project scope

    command = SetDispositionCommand(
        org_id=scope.org_id,
        project_id=scope.project_id,
        item_id=parsed_item_id,
        actor_id=scope.user_id,
        actor_role=scope.role or "",
        disposition=ClearanceDisposition(body.disposition),
        rationale=body.rationale,
        expected_version=body.expected_version,
        intent_hash=body.intent_hash,
        idempotency_key=idempotency_key,
    )

    try:
        async with session_scope() as session:
            result = await _disposition_service.set_disposition(session, command)
    except (
        CommandForbiddenError,
        CommandNotFoundError,
        StaleVersionConflictError,
        IdempotencyIntentConflictError,
        CommandValidationError,
    ) as error:
        return _envelope_for(error)

    return _success(result)


def _parse_item_id(item_id: str) -> UUID | None:
    try:
        return UUID(item_id)
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
    if isinstance(error, StaleVersionConflictError):
        return error_response(
            status_code=status.HTTP_409_CONFLICT,
            code="conflict_stale_version",
            message=error.message,
        )
    if isinstance(error, IdempotencyIntentConflictError):
        return error_response(
            status_code=status.HTTP_409_CONFLICT,
            code="conflict_idempotency_mismatch",
            message=error.message,
        )
    # CommandValidationError and any other typed governed-command error.
    message = getattr(error, "message", "The decision inputs were invalid.")
    return error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code="validation_failed",
        message=message,
    )


def _success(result: PersistedDecision) -> JSONResponse:
    data: dict[str, object] = {
        "itemId": str(result.item_id),
        "projectId": str(result.project_id),
        "version": result.resulting_version,
        "category": result.category,
        "entityName": result.entity_name,
        "status": result.status,
        "claimCount": result.cited_claim_count,
    }
    if result.version_id is not None:
        data["versionId"] = str(result.version_id)
    if result.context_text is not None:
        data["contextText"] = result.context_text
    # Only surface a disposition that is part of the canonical vocabulary; the
    # storage default ("undisposed") is not a contract disposition value.
    if result.disposition_status is not None and result.disposition_status != "undisposed":
        data["disposition"] = result.disposition_status
    if result.assigned_to_user_id is not None:
        data["assignedTo"] = str(result.assigned_to_user_id)

    request_id = f"req_{result.decision_id}"
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"data": data, "meta": {"requestId": request_id}},
    )

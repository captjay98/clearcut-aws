"""Delivery boundary for the canonical governed evidence-decision operation.

This router mounts exactly the canonical ``:recordEvidenceDecision`` operation
from the contract. The superseded public ``/items/{item}/decisions`` route that
wrote the legacy ``audit_events`` table has been retired: governed evidence
decisions now flow through the shared command kernel and the authoritative audit
ledger, with tenant-and-project scope, server-derived capability, expected-
version concurrency, intent/idempotency, zero-evidence protection, and a
same-transaction authoritative audit event.

``rewrites_router`` mounts the four contract-declared rewrite operations plus the
scoped proposal list. Those four operations were declared in the contract and
called by the shipped UI while no route existed to serve them; they now run
through the same governed-command kernel as evidence decisions.

Typed governed-command errors are translated to the canonical HTTP error
envelope here; the neutral not-found/forbidden shapes preserve safe tenant
parity so a caller cannot probe for the existence of another tenant's items.
"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

import uuid6
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
from clearcut.decisions.adapters.sql_rewrite_repository import SqlRewriteRepository
from clearcut.decisions.application.record_evidence_decision import (
    EvidenceDecisionValue,
    RecordEvidenceDecisionCommand,
    RecordEvidenceDecisionService,
)
from clearcut.decisions.application.rewrite_commands import (
    ProposeRewriteCommand,
    RewriteCommandService,
    RewriteTransitionCommand,
)
from clearcut.decisions.application.set_disposition import (
    ClearanceDisposition,
    SetDispositionCommand,
    SetDispositionService,
)
from clearcut.decisions.domain.rewrites import RewriteAction, RewriteTransitionError
from clearcut.decisions.ports.repository import PersistedDecision
from clearcut.decisions.ports.rewrite_repository import ScopedRewriteProposal
from clearcut.delivery_errors import error_response
from clearcut.identity.delivery.scope import get_request_scope
from fastapi import APIRouter, Header, Path, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(tags=["decisions"])
rewrites_router = APIRouter(tags=["rewrites"])

_DECISION_PATH = (
    "/api/v1/organizations/{orgId}/projects/{projectId}"
    "/clearance-items/{itemId}:recordEvidenceDecision"
)

_DISPOSITION_PATH = (
    "/api/v1/organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}:setDisposition"
)

_PROPOSE_REWRITE_PATH = (
    "/api/v1/organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}:proposeRewrite"
)

_LIST_REWRITES_PATH = (
    "/api/v1/organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}/rewrite-proposals"
)

_REWRITE_PROPOSAL_PATH = (
    "/api/v1/organizations/{orgId}/projects/{projectId}/rewrite-proposals/{proposalId}"
)

OrgIdParam = Annotated[str, Path(alias="orgId")]
ProjectIdParam = Annotated[str, Path(alias="projectId")]
ItemIdParam = Annotated[str, Path(alias="itemId")]
ProposalIdParam = Annotated[str, Path(alias="proposalId")]

# The canonical rewrite operations declare no Idempotency-Key parameter, so the
# header is accepted but not required. A client that sends one gets replay
# protection; a client that does not gets a fresh key per request, and the
# lifecycle state machine is what stops a second approval from committing twice.
OptionalIdempotencyKey = Annotated[
    str | None, Header(alias="Idempotency-Key", min_length=16, max_length=128)
]

_service = RecordEvidenceDecisionService(repository=SqlDecisionRepository())
_disposition_service = SetDispositionService(repository=SqlDecisionRepository())
_rewrite_service = RewriteCommandService(repository=SqlRewriteRepository())

# Every typed failure the rewrite lifecycle can raise. Listing them explicitly
# keeps an unexpected exception a 500 rather than silently becoming a 422.
_REWRITE_ERRORS = (
    RewriteTransitionError,
    CommandForbiddenError,
    CommandNotFoundError,
    StaleVersionConflictError,
    IdempotencyIntentConflictError,
    CommandValidationError,
)


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


class ProposeRewriteBody(BaseModel):
    """Contract-aligned request body for ``proposeRewrite``.

    Deliberately absent: ``originalText``, ``elementId``, ``sourceVersionId``, and
    any ownership field. The server reads all of those from the authorized item,
    so a client can neither claim what passage it is replacing nor which version
    it belongs to.
    """

    model_config = ConfigDict(extra="forbid")

    proposed_text: Annotated[str, Field(min_length=1, alias="proposedText")]
    rationale: str = ""


class RewriteTransitionBody(BaseModel):
    """Optional body for ``approveRewrite``/``rejectRewrite``/``withdrawRewrite``.

    The canonical operations declare no request body, so this is optional. A
    supplied ``rationale`` is recorded as the rejection reason on a rejection; it
    is never invented when absent, so an unexplained rejection stays unexplained
    rather than carrying fabricated text.
    """

    model_config = ConfigDict(extra="forbid")

    rationale: str | None = None


@rewrites_router.post(
    _PROPOSE_REWRITE_PATH,
    operation_id="proposeRewrite",
    status_code=status.HTTP_201_CREATED,
)
async def propose_rewrite(
    org_id: OrgIdParam,
    project_id: ProjectIdParam,
    item_id: ItemIdParam,
    body: ProposeRewriteBody,
    request: Request,
    idempotency_key: OptionalIdempotencyKey = None,
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

    command = ProposeRewriteCommand(
        org_id=scope.org_id,
        project_id=scope.project_id,
        item_id=parsed_item_id,
        actor_id=scope.user_id,
        actor_role=scope.role or "",
        actor_email=scope.email,
        proposed_text=body.proposed_text,
        rationale=body.rationale,
        idempotency_key=idempotency_key or _derived_idempotency_key(),
    )

    try:
        async with session_scope() as session:
            result = await _rewrite_service.propose(session, command)
    except _REWRITE_ERRORS as error:
        return _envelope_for(error)

    return _rewrite_success(result, status_code=status.HTTP_201_CREATED)


@rewrites_router.post(f"{_REWRITE_PROPOSAL_PATH}:approve", operation_id="approveRewrite")
async def approve_rewrite(
    org_id: OrgIdParam,
    project_id: ProjectIdParam,
    proposal_id: ProposalIdParam,
    request: Request,
    body: RewriteTransitionBody | None = None,
    idempotency_key: OptionalIdempotencyKey = None,
) -> JSONResponse:
    return await _transition(
        request,
        org_id=org_id,
        project_id=project_id,
        proposal_id=proposal_id,
        action=RewriteAction.APPROVE,
        body=body,
        idempotency_key=idempotency_key,
    )


@rewrites_router.post(f"{_REWRITE_PROPOSAL_PATH}:reject", operation_id="rejectRewrite")
async def reject_rewrite(
    org_id: OrgIdParam,
    project_id: ProjectIdParam,
    proposal_id: ProposalIdParam,
    request: Request,
    body: RewriteTransitionBody | None = None,
    idempotency_key: OptionalIdempotencyKey = None,
) -> JSONResponse:
    return await _transition(
        request,
        org_id=org_id,
        project_id=project_id,
        proposal_id=proposal_id,
        action=RewriteAction.REJECT,
        body=body,
        idempotency_key=idempotency_key,
    )


@rewrites_router.post(f"{_REWRITE_PROPOSAL_PATH}:withdraw", operation_id="withdrawRewrite")
async def withdraw_rewrite(
    org_id: OrgIdParam,
    project_id: ProjectIdParam,
    proposal_id: ProposalIdParam,
    request: Request,
    body: RewriteTransitionBody | None = None,
    idempotency_key: OptionalIdempotencyKey = None,
) -> JSONResponse:
    return await _transition(
        request,
        org_id=org_id,
        project_id=project_id,
        proposal_id=proposal_id,
        action=RewriteAction.WITHDRAW,
        body=body,
        idempotency_key=idempotency_key,
    )


@rewrites_router.get(_LIST_REWRITES_PATH, operation_id="listRewriteProposals")
async def list_rewrite_proposals(
    org_id: OrgIdParam,
    project_id: ProjectIdParam,
    item_id: ItemIdParam,
    request: Request,
) -> JSONResponse:
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)

    parsed_item_id = _parse_item_id(item_id)
    if parsed_item_id is None:
        return _envelope_for(CommandNotFoundError())

    assert scope.org_id is not None  # get_request_scope enforced org membership
    assert scope.project_id is not None  # get_request_scope enforced project scope

    try:
        async with session_scope() as session:
            proposals = await _rewrite_service.list_proposals(
                session,
                org_id=scope.org_id,
                project_id=scope.project_id,
                item_id=parsed_item_id,
                actor_role=scope.role or "",
            )
    except _REWRITE_ERRORS as error:
        return _envelope_for(error)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "data": [_rewrite_payload(proposal) for proposal in proposals],
            "meta": {"requestId": f"req_{uuid6.uuid7()}", "totalCount": len(proposals)},
        },
    )


async def _transition(
    request: Request,
    *,
    org_id: str,
    project_id: str,
    proposal_id: str,
    action: RewriteAction,
    body: RewriteTransitionBody | None,
    idempotency_key: str | None,
) -> JSONResponse:
    """Run one governed rewrite lifecycle move.

    The three transition operations differ only in the action they carry, so they
    share this handler rather than triplicating the scope, parse, and error
    translation steps.
    """
    verify_csrf_origin(request)
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)

    parsed_proposal_id = _parse_item_id(proposal_id)
    if parsed_proposal_id is None:
        return _envelope_for(CommandNotFoundError())

    assert scope.org_id is not None  # get_request_scope enforced org membership
    assert scope.project_id is not None  # get_request_scope enforced project scope

    command = RewriteTransitionCommand(
        org_id=scope.org_id,
        project_id=scope.project_id,
        proposal_id=parsed_proposal_id,
        actor_id=scope.user_id,
        actor_role=scope.role or "",
        action=action,
        rationale=body.rationale if body is not None else None,
        idempotency_key=idempotency_key or _derived_idempotency_key(),
    )

    try:
        async with session_scope() as session:
            result = await _rewrite_service.transition(session, command)
    except _REWRITE_ERRORS as error:
        return _envelope_for(error)

    return _rewrite_success(result, status_code=status.HTTP_200_OK)


def _derived_idempotency_key() -> str:
    """Mint a per-request idempotency key when the client supplied none.

    A fresh key means the request is classified as a new command, so the
    lifecycle state machine -- not a silent replay -- decides whether it is legal.
    """
    return f"srv-{uuid6.uuid7().hex}"


def _rewrite_payload(proposal: ScopedRewriteProposal) -> dict[str, object]:
    """Project a proposal onto the canonical ``RewriteProposal`` response shape.

    Personal data is limited to the proposer's id and email, which is exactly
    what the existing collaboration surface already exposes for a comment author.
    """
    data: dict[str, object] = {
        "proposalId": str(proposal.proposal_id),
        "itemId": str(proposal.item_id),
        "projectId": str(proposal.project_id),
        "sourceVersionId": str(proposal.source_version_id),
        "elementId": str(proposal.element_id),
        "proposerId": str(proposal.proposer_id),
        "status": proposal.status.value,
        "originalText": proposal.original_text,
        "proposedText": proposal.proposed_text,
        "itemVersion": proposal.item_version,
        "createdAt": proposal.created_at.isoformat(),
        "updatedAt": proposal.updated_at.isoformat(),
    }
    if proposal.proposer_email:
        data["proposerEmail"] = proposal.proposer_email
    if proposal.rationale:
        data["rationale"] = proposal.rationale
    if proposal.approver_id is not None:
        data["approverId"] = str(proposal.approver_id)
    if proposal.rejection_reason:
        data["rejectionReason"] = proposal.rejection_reason
    # Present only when a separate materialization step has bound the proposal to
    # the successor version it produced; approval alone never creates one.
    if proposal.resulting_version_id is not None:
        data["resultingVersionId"] = str(proposal.resulting_version_id)
    return data


def _rewrite_success(proposal: ScopedRewriteProposal, *, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "data": _rewrite_payload(proposal),
            "meta": {"requestId": f"req_{proposal.proposal_id}"},
        },
    )


def _envelope_for(error: Exception) -> JSONResponse:
    if isinstance(error, RewriteTransitionError):
        # An illegal lifecycle move is a visible conflict: the caller asked for a
        # transition the proposal's current state does not allow.
        return error_response(
            status_code=status.HTTP_409_CONFLICT,
            code="conflict",
            message=error.message,
        )
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

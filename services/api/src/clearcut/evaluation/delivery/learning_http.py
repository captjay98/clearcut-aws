"""Delivery boundary for the bounded learning-candidate lifecycle.

Three contract operations are mounted here:

* ``listLearningCandidates`` -- readable by any active member of the organization,
  newest first.
* ``promoteLearningCandidate`` and ``rollbackLearningCandidate`` -- governed
  mutations, Owner-only, each running through the shared command kernel so the
  stage change and its immutable authoritative audit event commit together.

Handler order is the same for every mutation: verify the request origin, resolve
the authenticated scope (which enforces active membership and yields the
server-derived role), treat an unparseable candidate id as a neutral not-found,
build the typed command with the organization id taken from the *scope* rather
than the path and the role taken from the scope, run one ``session_scope()``
transaction, translate typed governed-command errors into the canonical error
envelope, and return the typed result.

The contract defines no request body for promote and rollback. Both accept an
optional one so a caller can supply ``expectedVersion`` for optimistic
concurrency and a rollback ``reason``; omitting the body is fully supported and
the version-guarded compare-and-swap still rejects concurrent interleaving. Both
bodies forbid unknown fields.

Error envelopes use the canonical code vocabulary: a protected-scope or
capability refusal is ``permission_denied`` (403), an absent or foreign candidate
is ``not_found`` (404), a concurrent version change is ``conflict_stale_version``
(409), and a failed gate or illegal stage move is ``validation_failed`` (422).
Not-found is presented with the same neutral shape whether the candidate is
absent or belongs to another organization.
"""

from __future__ import annotations

from typing import Annotated
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
from clearcut.delivery_errors import error_response
from clearcut.evaluation.adapters.sql_learning_repository import SqlLearningRepository
from clearcut.evaluation.application.learning_pipeline import (
    LearningPipelineService,
    LearningStageChange,
    PromoteLearningCandidateCommand,
    RollbackLearningCandidateCommand,
)
from clearcut.evaluation.domain.learning import LearningCandidate
from clearcut.identity.delivery.scope import get_request_scope
from fastapi import APIRouter, Header, Path, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(tags=["learning"])

_LIST_PATH = "/api/v1/organizations/{orgId}/learning-candidates"
_PROMOTE_PATH = "/api/v1/organizations/{orgId}/learning-candidates/{candidateId}:promote"
_ROLLBACK_PATH = "/api/v1/organizations/{orgId}/learning-candidates/{candidateId}:rollback"

OrgIdParam = Annotated[str, Path(alias="orgId")]
CandidateIdParam = Annotated[str, Path(alias="candidateId")]
IdempotencyKeyHeader = Annotated[str | None, Header(alias="Idempotency-Key", max_length=128)]

_service = LearningPipelineService(repository=SqlLearningRepository())
_repository = SqlLearningRepository()

_GOVERNED_ERRORS = (
    CommandForbiddenError,
    CommandNotFoundError,
    StaleVersionConflictError,
    IdempotencyIntentConflictError,
    CommandValidationError,
)


class PromoteLearningCandidateBody(BaseModel):
    """Optional contract extension carrying the optimistic-concurrency guard."""

    model_config = ConfigDict(extra="forbid")

    expected_version: Annotated[int | None, Field(default=None, ge=1, alias="expectedVersion")]


class RollbackLearningCandidateBody(BaseModel):
    """Optional contract extension carrying the guard and a rollback reason."""

    model_config = ConfigDict(extra="forbid")

    expected_version: Annotated[int | None, Field(default=None, ge=1, alias="expectedVersion")]
    reason: Annotated[str | None, Field(default=None, min_length=1, max_length=2000)]


@router.get(_LIST_PATH, operation_id="listLearningCandidates")
async def list_learning_candidates(
    org_id: OrgIdParam,
    request: Request,
) -> JSONResponse:
    scope = await get_request_scope(request, org_id=org_id)
    assert scope.org_id is not None  # get_request_scope enforced active membership

    try:
        async with session_scope() as session:
            candidates = await _repository.list_candidates(session, org_id=scope.org_id)
    except _GOVERNED_ERRORS as error:
        return _envelope_for(error)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "data": [_candidate_payload(candidate) for candidate in candidates],
            "meta": {
                "requestId": f"req_{uuid6.uuid7()}",
                "totalCount": len(candidates),
            },
        },
    )


@router.post(_PROMOTE_PATH, operation_id="promoteLearningCandidate")
async def promote_learning_candidate(
    org_id: OrgIdParam,
    candidate_id: CandidateIdParam,
    request: Request,
    idempotency_key: IdempotencyKeyHeader = None,
    body: PromoteLearningCandidateBody | None = None,
) -> JSONResponse:
    verify_csrf_origin(request)
    scope = await get_request_scope(request, org_id=org_id)

    parsed_candidate_id = _parse_uuid(candidate_id)
    if parsed_candidate_id is None:
        # An unparseable id is a resource that cannot exist in scope: neutral
        # not-found parity, never a distinguishing validation error.
        return _envelope_for(CommandNotFoundError())

    assert scope.org_id is not None  # get_request_scope enforced active membership

    command = PromoteLearningCandidateCommand(
        org_id=scope.org_id,
        candidate_id=parsed_candidate_id,
        actor_id=scope.user_id,
        actor_role=scope.role or "",
        expected_version=body.expected_version if body is not None else None,
        idempotency_key=_clean_key(idempotency_key),
    )

    try:
        async with session_scope() as session:
            result = await _service.promote(session, command)
    except _GOVERNED_ERRORS as error:
        return _envelope_for(error)

    return _stage_response(result)


@router.post(_ROLLBACK_PATH, operation_id="rollbackLearningCandidate")
async def rollback_learning_candidate(
    org_id: OrgIdParam,
    candidate_id: CandidateIdParam,
    request: Request,
    idempotency_key: IdempotencyKeyHeader = None,
    body: RollbackLearningCandidateBody | None = None,
) -> JSONResponse:
    verify_csrf_origin(request)
    scope = await get_request_scope(request, org_id=org_id)

    parsed_candidate_id = _parse_uuid(candidate_id)
    if parsed_candidate_id is None:
        return _envelope_for(CommandNotFoundError())

    assert scope.org_id is not None  # get_request_scope enforced active membership

    command = RollbackLearningCandidateCommand(
        org_id=scope.org_id,
        candidate_id=parsed_candidate_id,
        actor_id=scope.user_id,
        actor_role=scope.role or "",
        reason=body.reason if body is not None else None,
        expected_version=body.expected_version if body is not None else None,
        idempotency_key=_clean_key(idempotency_key),
    )

    try:
        async with session_scope() as session:
            result = await _service.rollback(session, command)
    except _GOVERNED_ERRORS as error:
        return _envelope_for(error)

    return _stage_response(result)


def _parse_uuid(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


def _clean_key(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _candidate_payload(candidate: LearningCandidate) -> dict[str, object]:
    """Project one candidate onto the contract's ``LearningCandidate`` shape."""
    payload: dict[str, object] = {
        "candidateId": str(candidate.candidate_id),
        "orgId": str(candidate.org_id),
        "scope": candidate.scope.value,
        "stage": candidate.stage.value,
        "canaryPassRate": candidate.canary_pass_rate,
        "regressionCasesPassed": candidate.regression_cases_passed,
        "regressionCasesTotal": candidate.regression_cases_total,
        "version": candidate.version,
        "createdAt": candidate.created_at.isoformat(),
    }
    if candidate.title is not None:
        payload["title"] = candidate.title
    if candidate.summary is not None:
        payload["summary"] = candidate.summary
    if candidate.promoted_at is not None:
        payload["promotedAt"] = candidate.promoted_at.isoformat()
    if candidate.rolled_back_at is not None:
        payload["rolledBackAt"] = candidate.rolled_back_at.isoformat()
    if candidate.rollback_reason is not None:
        payload["rollbackReason"] = candidate.rollback_reason
    return payload


def _stage_response(result: LearningStageChange) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "data": {
                "candidateId": str(result.candidate_id),
                "stage": result.stage.value,
            },
            "meta": {"requestId": f"req_{uuid6.uuid7()}"},
        },
    )


def _envelope_for(error: Exception) -> JSONResponse:
    if isinstance(error, CommandForbiddenError):
        # Covers the protected-scope violation and the unbounded-scope refusal,
        # which subclass the kernel's forbidden error.
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
    # CommandValidationError and its learning subclasses: a failed regression or
    # canary gate, and an illegal stage transition.
    message = getattr(error, "message", "The learning-candidate request was invalid.")
    return error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code="validation_failed",
        message=message,
    )


__all__ = ["router"]

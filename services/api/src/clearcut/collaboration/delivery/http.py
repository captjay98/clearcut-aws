"""Delivery boundary for canonical governed collaboration operations.

The router mounts the generated referral and comment commands with exact
organization/project/item paths. Every command derives actor and tenant scope
from the authenticated request, accepts canonical version/intent/idempotency
inputs, and translates typed command failures to safe 403/404/409/422 envelopes.
Accepted commands commit their domain write, receipt, audit event, and deduplicated
outbox event in one transaction.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from clearcut.collaboration.adapters.sql_repository import SqlCollaborationRepository
from clearcut.collaboration.application.comments import (
    AddCommentCommand,
    CommentService,
    PersistedComment,
    ReplyToCommentCommand,
    ReviseCommentCommand,
)
from clearcut.collaboration.application.referrals import (
    AcknowledgeReferralCommand,
    PersistedReferral,
    ReferralService,
    SubmitReferralCommand,
)
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
from clearcut.identity.delivery.scope import get_request_scope
from fastapi import APIRouter, Header, Path, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.json_schema import SkipJsonSchema

router = APIRouter(tags=["collaboration"])

_REFER_PATH = "/api/v1/organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}:refer"

_ACKNOWLEDGE_PATH = (
    "/api/v1/organizations/{orgId}/projects/{projectId}"
    "/clearance-items/{itemId}/referrals/{referralId}:acknowledge"
)

_ADD_COMMENT_PATH = (
    "/api/v1/organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}/comments"
)

_REPLY_COMMENT_PATH = (
    "/api/v1/organizations/{orgId}/projects/{projectId}"
    "/clearance-items/{itemId}/comments/{commentId}:reply"
)

_REVISE_COMMENT_PATH = (
    "/api/v1/organizations/{orgId}/projects/{projectId}"
    "/clearance-items/{itemId}/comments/{commentId}:revise"
)

OrgIdParam = Annotated[str, Path(alias="orgId")]
ProjectIdParam = Annotated[str, Path(alias="projectId")]
ItemIdParam = Annotated[str, Path(alias="itemId")]
ReferralIdParam = Annotated[str, Path(alias="referralId")]
CommentIdParam = Annotated[str, Path(alias="commentId")]

_service = ReferralService(repository=SqlCollaborationRepository())
_comment_service = CommentService(repository=SqlCollaborationRepository())


class ReferClearanceItemBody(BaseModel):
    """Contract-aligned request body for ``referClearanceItem``."""

    model_config = ConfigDict(extra="forbid")

    target_role: Annotated[str, Field(min_length=1, alias="targetRole")]
    question: Annotated[str, Field(min_length=1)]
    rationale: Annotated[str, Field(min_length=1)]
    expected_version: Annotated[int, Field(ge=0, alias="expectedVersion")]
    intent_hash: Annotated[str, Field(min_length=1, alias="intentHash")]


class AcknowledgeReferralBody(BaseModel):
    """Contract-aligned request body for ``acknowledgeReferral``."""

    model_config = ConfigDict(extra="forbid")

    response: Annotated[str, Field(min_length=1)]
    rationale: Annotated[str, Field(min_length=1)]
    expected_version: Annotated[int, Field(ge=0, alias="expectedVersion")]
    intent_hash: Annotated[str, Field(min_length=1, alias="intentHash")]


_INTENT_HASH_PATTERN = r"^[0-9a-f]{64}$"
_UUIDV7_PATTERN = (
    r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
UUIDv7Value = Annotated[str, Field(pattern=_UUIDV7_PATTERN)]


class _CommentCommandBody(BaseModel):
    """Shared canonical body for comment, reply, and revision commands."""

    model_config = ConfigDict(extra="forbid")

    body: Annotated[str, Field(min_length=1)]
    mentions: list[UUIDv7Value] = Field(
        default_factory=list,
        json_schema_extra={"uniqueItems": True},
    )
    expected_version: Annotated[int, Field(ge=1, alias="expectedVersion")]
    intent_hash: Annotated[
        str,
        Field(pattern=_INTENT_HASH_PATTERN, alias="intentHash"),
    ]

    @field_validator("mentions")
    @classmethod
    def require_unique_mentions(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("Mention recipient IDs must be unique.")
        return values


class AddCommentBody(_CommentCommandBody):
    """Canonical request body for ``addComment``."""


class ReplyToCommentBody(_CommentCommandBody):
    """Canonical request body for ``replyToComment``."""


class ReviseCommentBody(_CommentCommandBody):
    """Canonical request body for ``reviseComment``."""


class CommentData(BaseModel):
    """Canonical persisted comment response projection."""

    model_config = ConfigDict(populate_by_name=True)

    comment_id: UUIDv7Value = Field(alias="commentId")
    item_id: UUIDv7Value = Field(alias="itemId")
    item_version: Annotated[int, Field(ge=0, alias="itemVersion")]
    author_id: UUIDv7Value = Field(alias="authorId")
    author_email: str | SkipJsonSchema[None] = Field(
        default=None,
        alias="authorEmail",
    )
    body: str
    parent_id: UUIDv7Value | SkipJsonSchema[None] = Field(
        default=None,
        alias="parentId",
    )
    created_at: datetime = Field(alias="createdAt")


class CommentResponseMeta(BaseModel):
    """Canonical response metadata for comment commands."""

    model_config = ConfigDict(populate_by_name=True)

    request_id: str = Field(alias="requestId")


class CommentEnvelope(BaseModel):
    """Typed canonical success envelope for comment commands."""

    data: CommentData
    meta: CommentResponseMeta


@router.post(_REFER_PATH, operation_id="referClearanceItem")
async def refer_clearance_item(
    org_id: OrgIdParam,
    project_id: ProjectIdParam,
    item_id: ItemIdParam,
    body: ReferClearanceItemBody,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=16, max_length=128)],
) -> JSONResponse:
    verify_csrf_origin(request)
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)

    parsed_item_id = _parse_uuid(item_id)
    if parsed_item_id is None:
        # An unparseable item id is a resource that cannot exist in scope: neutral
        # not-found parity, never a distinguishing validation error.
        return _envelope_for(CommandNotFoundError())

    assert scope.org_id is not None  # get_request_scope enforced org membership
    assert scope.project_id is not None  # get_request_scope enforced project scope

    command = SubmitReferralCommand(
        org_id=scope.org_id,
        project_id=scope.project_id,
        item_id=parsed_item_id,
        actor_id=scope.user_id,
        actor_role=scope.role or "",
        target_role=body.target_role,
        question=body.question,
        rationale=body.rationale,
        expected_version=body.expected_version,
        intent_hash=body.intent_hash,
        idempotency_key=idempotency_key,
    )

    try:
        async with session_scope() as session:
            result = await _service.submit(session, command)
    except (
        CommandForbiddenError,
        CommandNotFoundError,
        StaleVersionConflictError,
        IdempotencyIntentConflictError,
        CommandValidationError,
    ) as error:
        return _envelope_for(error)

    return _success(result, status_code=status.HTTP_201_CREATED)


@router.post(_ACKNOWLEDGE_PATH, operation_id="acknowledgeReferral")
async def acknowledge_referral(
    org_id: OrgIdParam,
    project_id: ProjectIdParam,
    item_id: ItemIdParam,
    referral_id: ReferralIdParam,
    body: AcknowledgeReferralBody,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=16, max_length=128)],
) -> JSONResponse:
    verify_csrf_origin(request)
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)

    parsed_item_id = _parse_uuid(item_id)
    parsed_referral_id = _parse_uuid(referral_id)
    if parsed_item_id is None or parsed_referral_id is None:
        return _envelope_for(CommandNotFoundError())

    assert scope.org_id is not None  # get_request_scope enforced org membership
    assert scope.project_id is not None  # get_request_scope enforced project scope

    command = AcknowledgeReferralCommand(
        org_id=scope.org_id,
        project_id=scope.project_id,
        item_id=parsed_item_id,
        referral_id=parsed_referral_id,
        actor_id=scope.user_id,
        actor_role=scope.role or "",
        response=body.response,
        rationale=body.rationale,
        expected_version=body.expected_version,
        intent_hash=body.intent_hash,
        idempotency_key=idempotency_key,
    )

    try:
        async with session_scope() as session:
            result = await _service.acknowledge(session, command)
    except (
        CommandForbiddenError,
        CommandNotFoundError,
        StaleVersionConflictError,
        IdempotencyIntentConflictError,
        CommandValidationError,
    ) as error:
        return _envelope_for(error)

    return _success(result, status_code=status.HTTP_200_OK)


@router.post(
    _ADD_COMMENT_PATH,
    operation_id="addComment",
    status_code=status.HTTP_201_CREATED,
    response_model=CommentEnvelope,
    response_model_exclude_none=True,
)
async def add_comment(
    org_id: OrgIdParam,
    project_id: ProjectIdParam,
    item_id: ItemIdParam,
    body: AddCommentBody,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=16, max_length=128)],
) -> CommentEnvelope | JSONResponse:
    verify_csrf_origin(request)
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)

    parsed_item_id = _parse_uuid(item_id)
    if parsed_item_id is None:
        return _envelope_for(CommandNotFoundError())

    assert scope.org_id is not None  # get_request_scope enforced org membership
    assert scope.project_id is not None  # get_request_scope enforced project scope

    command = AddCommentCommand(
        org_id=scope.org_id,
        project_id=scope.project_id,
        item_id=parsed_item_id,
        actor_id=scope.user_id,
        actor_role=scope.role or "",
        content=body.body,
        mention_user_ids=tuple(UUID(value) for value in body.mentions),
        expected_version=body.expected_version,
        intent_hash=body.intent_hash,
        idempotency_key=idempotency_key,
    )

    try:
        async with session_scope() as session:
            result = await _comment_service.add(session, command)
    except (
        CommandForbiddenError,
        CommandNotFoundError,
        StaleVersionConflictError,
        IdempotencyIntentConflictError,
        CommandValidationError,
    ) as error:
        return _envelope_for(error)

    return _comment_success(result)


@router.post(
    _REPLY_COMMENT_PATH,
    operation_id="replyToComment",
    status_code=status.HTTP_201_CREATED,
    response_model=CommentEnvelope,
    response_model_exclude_none=True,
)
async def reply_to_comment(
    org_id: OrgIdParam,
    project_id: ProjectIdParam,
    item_id: ItemIdParam,
    comment_id: CommentIdParam,
    body: ReplyToCommentBody,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=16, max_length=128)],
) -> CommentEnvelope | JSONResponse:
    verify_csrf_origin(request)
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)

    parsed_item_id = _parse_uuid(item_id)
    parsed_comment_id = _parse_uuid(comment_id)
    if parsed_item_id is None or parsed_comment_id is None:
        return _envelope_for(CommandNotFoundError())

    assert scope.org_id is not None  # get_request_scope enforced org membership
    assert scope.project_id is not None  # get_request_scope enforced project scope

    command = ReplyToCommentCommand(
        org_id=scope.org_id,
        project_id=scope.project_id,
        item_id=parsed_item_id,
        parent_comment_id=parsed_comment_id,
        actor_id=scope.user_id,
        actor_role=scope.role or "",
        content=body.body,
        mention_user_ids=tuple(UUID(value) for value in body.mentions),
        expected_version=body.expected_version,
        intent_hash=body.intent_hash,
        idempotency_key=idempotency_key,
    )

    try:
        async with session_scope() as session:
            result = await _comment_service.reply(session, command)
    except (
        CommandForbiddenError,
        CommandNotFoundError,
        StaleVersionConflictError,
        IdempotencyIntentConflictError,
        CommandValidationError,
    ) as error:
        return _envelope_for(error)

    return _comment_success(result)


@router.post(
    _REVISE_COMMENT_PATH,
    operation_id="reviseComment",
    response_model=CommentEnvelope,
    response_model_exclude_none=True,
)
async def revise_comment(
    org_id: OrgIdParam,
    project_id: ProjectIdParam,
    item_id: ItemIdParam,
    comment_id: CommentIdParam,
    body: ReviseCommentBody,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=16, max_length=128)],
) -> CommentEnvelope | JSONResponse:
    verify_csrf_origin(request)
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)

    parsed_item_id = _parse_uuid(item_id)
    parsed_comment_id = _parse_uuid(comment_id)
    if parsed_item_id is None or parsed_comment_id is None:
        return _envelope_for(CommandNotFoundError())

    assert scope.org_id is not None  # get_request_scope enforced org membership
    assert scope.project_id is not None  # get_request_scope enforced project scope

    command = ReviseCommentCommand(
        org_id=scope.org_id,
        project_id=scope.project_id,
        item_id=parsed_item_id,
        comment_id=parsed_comment_id,
        actor_id=scope.user_id,
        actor_role=scope.role or "",
        content=body.body,
        mention_user_ids=tuple(UUID(value) for value in body.mentions),
        expected_version=body.expected_version,
        intent_hash=body.intent_hash,
        idempotency_key=idempotency_key,
    )

    try:
        async with session_scope() as session:
            result = await _comment_service.revise(session, command)
    except (
        CommandForbiddenError,
        CommandNotFoundError,
        StaleVersionConflictError,
        IdempotencyIntentConflictError,
        CommandValidationError,
    ) as error:
        return _envelope_for(error)

    return _comment_success(result)


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
    message = getattr(error, "message", "The referral inputs were invalid.")
    return error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code="validation_failed",
        message=message,
    )


def _success(result: PersistedReferral, *, status_code: int) -> JSONResponse:
    data: dict[str, object] = {
        "referralId": str(result.referral_id),
        "itemId": str(result.item_id),
        "itemVersion": result.resulting_item_version,
        "targetRole": result.target_role,
        "question": result.question,
        "status": result.status,
    }
    if result.response is not None:
        data["response"] = result.response

    request_id = f"req_{result.referral_id}"
    return JSONResponse(
        status_code=status_code,
        content={"data": data, "meta": {"requestId": request_id}},
    )



def _comment_success(result: PersistedComment) -> CommentEnvelope:
    data = CommentData(
        commentId=str(result.comment_id),
        itemId=str(result.item_id),
        item_version=result.resulting_item_version,
        authorId=str(result.author_id),
        body=result.body,
        parentId=(
            str(result.parent_comment_id) if result.parent_comment_id is not None else None
        ),
        createdAt=result.created_at,
    )
    return CommentEnvelope(
        data=data,
        meta=CommentResponseMeta(requestId=f"req_{result.comment_id}"),
    )

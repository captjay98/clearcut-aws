"""Delivery boundary for the organization's protected configuration bindings.

This router mounts exactly the four contract operations
``listProtectedConfigurations``, ``draftProtectedConfiguration``,
``validateProtectedConfiguration``, and ``activateProtectedConfiguration``. All
four are organization-scoped: the authenticated ``org_id`` from the request scope
is the whole tenant key, and it — not the path parameter — is what reaches the
command.

The list requires only active membership, which
:func:`~clearcut.identity.delivery.scope.get_request_scope` proves. The other
three are governed mutations: each verifies the request origin, resolves the
scope, builds a typed command whose actor role is server-derived, runs inside one
transaction, and translates typed governed-command errors into the canonical error
envelope. An unparseable configuration id is a resource that cannot exist in
scope, so it returns the neutral not-found envelope rather than a distinguishing
validation error — the same shape a foreign organization's binding produces, so a
caller cannot probe another tenant.

Authorization for drafting, validating, and activating is Owner-only, enforced in
the application layer against the server-resolved membership role. This boundary
never reads a role, capability, or organization id from the request body.

Mounting
--------
``clearcut.evaluation.delivery.http`` carries an unschematized
``/protected-configurations`` placeholder that answers 503. FastAPI resolves
routes in registration order, so this router must be included *before* that one
for the contract operation to be reachable, or that placeholder must be removed.
"""

from __future__ import annotations

from typing import Annotated
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
from clearcut.delivery_errors import error_response
from clearcut.evaluation.adapters.sql_configuration_repository import (
    SqlProtectedConfigurationRepository,
)
from clearcut.evaluation.application.protected_configuration import (
    ActivateConfigurationCommand,
    ConfigurationActivationResult,
    ConfigurationValidationResult,
    DraftConfigurationCommand,
    ProtectedConfigurationService,
    ValidateConfigurationCommand,
)
from clearcut.evaluation.domain.configuration import (
    LABEL_MAX_LENGTH,
    POLICY_VERSION_MAX_LENGTH,
    PROMPT_VERSION_MAX_LENGTH,
    ConfigurationCandidate,
    ProtectedConfiguration,
)
from clearcut.identity.delivery.scope import get_request_scope
from fastapi import APIRouter, Header, Path, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(tags=["governance"])

_COLLECTION_PATH = "/api/v1/organizations/{orgId}/protected-configurations"
_VALIDATE_PATH = (
    "/api/v1/organizations/{orgId}/protected-configurations/{configurationId}:validate"
)
_ACTIVATE_PATH = (
    "/api/v1/organizations/{orgId}/protected-configurations/{configurationId}:activate"
)

OrgIdParam = Annotated[str, Path(alias="orgId")]
ConfigurationIdParam = Annotated[str, Path(alias="configurationId")]

_service = ProtectedConfigurationService(repository=SqlProtectedConfigurationRepository())


class DraftProtectedConfigurationBody(BaseModel):
    """Contract-aligned request body for ``draftProtectedConfiguration``.

    ``extra="forbid"`` rejects any field the contract does not define, so a client
    cannot smuggle a lifecycle, an ``activatedBy``, or an organization id past this
    boundary — every one of those is server-derived or governed by a separate,
    accountable command. Lengths mirror the storage limits, so an over-long value
    is a framework 422 before the handler runs.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    policy_version: Annotated[
        str,
        Field(min_length=1, max_length=POLICY_VERSION_MAX_LENGTH, alias="policyVersion"),
    ]
    prompt_version: Annotated[
        str,
        Field(min_length=1, max_length=PROMPT_VERSION_MAX_LENGTH, alias="promptVersion"),
    ]
    rationale: Annotated[str, Field(min_length=1)]
    label: Annotated[str | None, Field(default=None, max_length=LABEL_MAX_LENGTH)]


@router.get(_COLLECTION_PATH, operation_id="listProtectedConfigurations")
async def list_protected_configurations(
    org_id: OrgIdParam,
    request: Request,
) -> JSONResponse:
    # Reading is not a state mutation, so no origin check applies. Membership in
    # the organization is what authorizes the read, and the request scope proves it
    # before anything is loaded.
    scope = await get_request_scope(request, org_id=org_id)
    assert scope.org_id is not None  # get_request_scope enforced membership

    try:
        async with session_scope() as session:
            configurations = await _service.list_configurations(session, org_id=scope.org_id)
    except (CommandNotFoundError, CommandValidationError) as error:
        return _envelope_for(error)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "data": [_configuration_data(configuration) for configuration in configurations],
            "meta": {
                "requestId": f"req_protected_configurations_{scope.org_id}",
                "count": len(configurations),
            },
        },
    )


@router.post(
    _COLLECTION_PATH,
    status_code=status.HTTP_201_CREATED,
    operation_id="draftProtectedConfiguration",
)
async def draft_protected_configuration(
    org_id: OrgIdParam,
    body: DraftProtectedConfigurationBody,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=16, max_length=128)],
) -> JSONResponse:
    verify_csrf_origin(request)
    scope = await get_request_scope(request, org_id=org_id)
    assert scope.org_id is not None  # get_request_scope enforced membership

    try:
        candidate = ConfigurationCandidate(
            policy_version=body.policy_version,
            prompt_version=body.prompt_version,
            rationale=body.rationale,
            label=body.label,
        )
    except CommandValidationError as error:
        return _envelope_for(error)

    command = DraftConfigurationCommand(
        # The authenticated scope is the tenant key, never the raw path value.
        org_id=scope.org_id,
        actor_id=scope.user_id,
        # Capability is derived from the server-resolved membership role only.
        actor_role=scope.role or "",
        candidate=candidate,
        idempotency_key=idempotency_key,
    )

    try:
        async with session_scope() as session:
            configuration = await _service.draft(session, command)
    except (
        CommandForbiddenError,
        CommandNotFoundError,
        StaleVersionConflictError,
        IdempotencyIntentConflictError,
        CommandValidationError,
    ) as error:
        return _envelope_for(error)

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "data": _configuration_data(configuration),
            "meta": {"requestId": f"req_protected_configuration_{configuration.config_id}"},
        },
    )


@router.post(_VALIDATE_PATH, operation_id="validateProtectedConfiguration")
async def validate_protected_configuration(
    org_id: OrgIdParam,
    configuration_id: ConfigurationIdParam,
    request: Request,
) -> JSONResponse:
    verify_csrf_origin(request)
    scope = await get_request_scope(request, org_id=org_id)
    assert scope.org_id is not None  # get_request_scope enforced membership

    parsed_configuration_id = _parse_configuration_id(configuration_id)
    if parsed_configuration_id is None:
        # An unparseable id is a resource that cannot exist in scope: neutral
        # not-found parity, never a distinguishing validation error.
        return _envelope_for(CommandNotFoundError())

    command = ValidateConfigurationCommand(
        org_id=scope.org_id,
        actor_id=scope.user_id,
        actor_role=scope.role or "",
        config_id=parsed_configuration_id,
    )

    try:
        async with session_scope() as session:
            result = await _service.validate(session, command)
    except (
        CommandForbiddenError,
        CommandNotFoundError,
        StaleVersionConflictError,
        IdempotencyIntentConflictError,
        CommandValidationError,
    ) as error:
        return _envelope_for(error)

    return _validation_success(result)


@router.post(_ACTIVATE_PATH, operation_id="activateProtectedConfiguration")
async def activate_protected_configuration(
    org_id: OrgIdParam,
    configuration_id: ConfigurationIdParam,
    request: Request,
) -> JSONResponse:
    verify_csrf_origin(request)
    scope = await get_request_scope(request, org_id=org_id)
    assert scope.org_id is not None  # get_request_scope enforced membership

    parsed_configuration_id = _parse_configuration_id(configuration_id)
    if parsed_configuration_id is None:
        return _envelope_for(CommandNotFoundError())

    command = ActivateConfigurationCommand(
        org_id=scope.org_id,
        actor_id=scope.user_id,
        actor_role=scope.role or "",
        config_id=parsed_configuration_id,
    )

    try:
        async with session_scope() as session:
            result = await _service.activate(session, command)
    except (
        CommandForbiddenError,
        CommandNotFoundError,
        StaleVersionConflictError,
        IdempotencyIntentConflictError,
        CommandValidationError,
    ) as error:
        return _envelope_for(error)

    return _activation_success(result)


def _parse_configuration_id(configuration_id: str) -> UUID | None:
    try:
        return UUID(configuration_id)
    except ValueError:
        return None


def _configuration_data(configuration: ProtectedConfiguration) -> dict[str, object]:
    """Project one binding onto the contract's ``ProtectedConfiguration`` shape.

    Optional fields are omitted rather than sent as null, so a surface can tell
    "never validated" from "validated at an unknown time". ``validationIssues`` is
    always present, including as an empty list, because "no recorded issues" is a
    real, meaningful state for a binding a human has validated.
    """
    data: dict[str, object] = {
        "configurationId": str(configuration.config_id),
        "orgId": str(configuration.org_id),
        "lifecycle": configuration.lifecycle.value,
        "policyVersion": configuration.policy_version,
        "promptVersion": configuration.prompt_version,
        "validationIssues": list(configuration.validation_issues),
        "createdAt": configuration.created_at.isoformat(),
    }
    if configuration.label is not None:
        data["label"] = configuration.label
    if configuration.rationale is not None:
        data["rationale"] = configuration.rationale
    if configuration.activated_by is not None:
        data["activatedBy"] = str(configuration.activated_by)
    if configuration.activated_at is not None:
        data["activatedAt"] = configuration.activated_at.isoformat()
    if configuration.validated_at is not None:
        data["validatedAt"] = configuration.validated_at.isoformat()
    if configuration.superseded_at is not None:
        data["supersededAt"] = configuration.superseded_at.isoformat()
    return data


def _validation_success(result: ConfigurationValidationResult) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "data": {"valid": result.valid, "issues": list(result.issues)},
            "meta": {"requestId": f"req_protected_configuration_validate_{result.config_id}"},
        },
    )


def _activation_success(result: ConfigurationActivationResult) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "data": {
                "configurationId": str(result.config_id),
                "status": result.lifecycle.value,
            },
            "meta": {"requestId": f"req_protected_configuration_activate_{result.config_id}"},
        },
    )


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
    message = getattr(error, "message", "The protected configuration inputs were invalid.")
    return error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code="validation_failed",
        message=message,
    )


__all__ = ["router"]

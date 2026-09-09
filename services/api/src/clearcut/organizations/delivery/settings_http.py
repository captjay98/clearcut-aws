"""Delivery boundary for organization settings reads and the governed update.

This router mounts exactly the two contract operations
``getOrganizationSettings`` and ``updateOrganizationSettings``. Both are
organization-scoped: the authenticated ``org_id`` from the request scope is the
whole tenant key, and it — not the path parameter — is what reaches the command.

The read requires only active membership, which
:func:`~clearcut.identity.delivery.scope.get_request_scope` proves. The update is
a governed mutation: it verifies the request origin, resolves the scope, builds a
typed command whose actor role is server-derived, runs inside one transaction, and
translates typed governed-command errors into the canonical error envelope. The
neutral not-found/forbidden shapes preserve tenant parity.

The request body deliberately has no ``slug`` (the URL identity cannot be
changed) and no evidence-retention duration (evidence is kept until its project
is deleted). ``extra="forbid"`` means a client that sends either is rejected
rather than quietly ignored.
"""

from __future__ import annotations

from typing import Annotated, Literal

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
from clearcut.organizations.adapters.sql_settings_repository import (
    SqlOrganizationSettingsRepository,
)
from clearcut.organizations.application.settings_service import (
    OrganizationSettingsService,
    UpdateOrganizationSettingsCommand,
)
from clearcut.organizations.ports.settings_repository import (
    MonitoringCadence,
    OrganizationSettings,
)
from fastapi import APIRouter, Header, Path, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(tags=["organizations"])

_SETTINGS_PATH = "/api/v1/organizations/{orgId}/settings"

OrgIdParam = Annotated[str, Path(alias="orgId")]

_service = OrganizationSettingsService(repository=SqlOrganizationSettingsRepository())


class UpdateOrganizationSettingsBody(BaseModel):
    """Contract-aligned request body for ``updateOrganizationSettings``.

    The cadence is constrained to the canonical stored vocabulary at the request
    boundary, so an out-of-vocabulary value is a framework 422 before the handler
    runs and can never reach the service or storage. ``extra="forbid"`` rejects
    any field the contract does not define — including ``slug`` and any invented
    retention duration.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str
    jurisdiction: str | None = Field(default=None, max_length=200)
    default_monitoring_cadence: Annotated[
        Literal["off", "manual", "daily", "weekly"],
        Field(alias="defaultMonitoringCadence"),
    ]
    expected_version: Annotated[int, Field(ge=1, alias="expectedVersion")]


@router.get(_SETTINGS_PATH, operation_id="getOrganizationSettings")
async def get_organization_settings(
    org_id: OrgIdParam,
    request: Request,
) -> JSONResponse:
    # Reading is not a state mutation, so no origin check applies. Membership in
    # the organization is what authorizes the read, and the request scope proves
    # it before anything is loaded.
    scope = await get_request_scope(request, org_id=org_id)
    assert scope.org_id is not None  # get_request_scope enforced membership

    try:
        async with session_scope() as session:
            settings = await _service.read(session, org_id=scope.org_id)
    except CommandNotFoundError as error:
        return _envelope_for(error)

    return _success(settings)


@router.patch(_SETTINGS_PATH, operation_id="updateOrganizationSettings")
async def update_organization_settings(
    org_id: OrgIdParam,
    body: UpdateOrganizationSettingsBody,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=16, max_length=128)],
) -> JSONResponse:
    verify_csrf_origin(request)
    scope = await get_request_scope(request, org_id=org_id)
    assert scope.org_id is not None  # get_request_scope enforced membership

    command = UpdateOrganizationSettingsCommand(
        # The authenticated scope is the tenant key, never the raw path value.
        org_id=scope.org_id,
        actor_id=scope.user_id,
        # Capability is derived from the server-resolved membership role only.
        actor_role=scope.role or "",
        name=body.name,
        jurisdiction=body.jurisdiction,
        default_monitoring_cadence=MonitoringCadence(body.default_monitoring_cadence),
        expected_version=body.expected_version,
        idempotency_key=idempotency_key,
    )

    try:
        async with session_scope() as session:
            settings = await _service.update(session, command)
    except (
        CommandForbiddenError,
        CommandNotFoundError,
        StaleVersionConflictError,
        IdempotencyIntentConflictError,
        CommandValidationError,
    ) as error:
        return _envelope_for(error)

    return _success(settings)


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
    message = getattr(error, "message", "The organization settings inputs were invalid.")
    return error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code="validation_failed",
        message=message,
    )


def _success(settings: OrganizationSettings) -> JSONResponse:
    data: dict[str, object] = {
        "orgId": str(settings.org_id),
        "name": settings.name,
        "slug": settings.slug,
        # The stored token is what the contract transports; surfaces render it
        # through their label map rather than printing it.
        "defaultMonitoringCadence": settings.default_monitoring_cadence.value,
        "version": settings.version,
    }
    if settings.jurisdiction is not None:
        data["jurisdiction"] = settings.jurisdiction
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"data": data, "meta": {"requestId": f"req_org_settings_{settings.org_id}"}},
    )


__all__ = ["router"]

"""Canonical Trust read boundaries backed by persisted evaluations in Task 10."""
from typing import Annotated

from clearcut.delivery_errors import capability_unavailable
from clearcut.identity.delivery.scope import get_request_scope
from fastapi import APIRouter, Path, Query, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/v1/organizations/{orgId}", tags=["evaluation", "trust"])
_TRUST_UNAVAILABLE = (
    "Trust evaluations are not available until persisted evaluation reads are configured."
)


async def _authorize(request: Request, org_id: str, project_id: str | None = None) -> None:
    await get_request_scope(request, org_id=org_id, project_id=project_id)


@router.get(
    "/projects/{projectId}/evaluations",
    operation_id="listTrustEvaluations",
)
async def list_trust_evaluations(
    request: Request,
    org_id: Annotated[str, Path(alias="orgId")],
    project_id: Annotated[str, Path(alias="projectId")],
    job_id: Annotated[str | None, Query(alias="jobId")] = None,
) -> JSONResponse:
    await _authorize(request, org_id, project_id)
    return capability_unavailable(_TRUST_UNAVAILABLE)


@router.get(
    "/projects/{projectId}/evaluations/{evaluationId}",
    operation_id="getTrustEvaluation",
)
async def get_trust_evaluation(
    request: Request,
    org_id: Annotated[str, Path(alias="orgId")],
    project_id: Annotated[str, Path(alias="projectId")],
    evaluation_id: Annotated[str, Path(alias="evaluationId")],
) -> JSONResponse:
    await _authorize(request, org_id, project_id)
    return capability_unavailable(_TRUST_UNAVAILABLE)


@router.get("/trust", include_in_schema=False)
@router.get("/rubric", include_in_schema=False)
async def legacy_trust_boundary(
    request: Request,
    org_id: Annotated[str, Path(alias="orgId")],
) -> JSONResponse:
    """Keep old URLs honest until the web client switches to evaluations."""
    await _authorize(request, org_id)
    return capability_unavailable(_TRUST_UNAVAILABLE)


@router.get("/protected-configurations", include_in_schema=False)
async def list_protected_configurations(
    request: Request,
    org_id: Annotated[str, Path(alias="orgId")],
) -> JSONResponse:
    await _authorize(request, org_id)
    return capability_unavailable(
        "Protected configurations are not available until governed reads are configured."
    )

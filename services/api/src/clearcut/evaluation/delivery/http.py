"""Canonical Trust read boundaries backed by persisted evaluations."""
from typing import Annotated
from uuid import UUID

import uuid6
from clearcut.delivery_errors import capability_unavailable, error_response
from clearcut.evaluation.adapters.sql_evaluation_repository import SqlEvaluationRepository
from clearcut.evaluation.application.read_evaluations import (
    ReadEvaluationsService,
    TrustEvaluationNotFound,
    TrustEvaluationView,
)
from clearcut.identity.delivery.scope import get_request_scope
from fastapi import APIRouter, Path, Query, Request, status
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/v1/organizations/{orgId}", tags=["evaluation", "trust"])
_TRUST_UNAVAILABLE = (
    "Trust evaluations are not available until persisted evaluation reads are configured."
)
_EVALUATION_NOT_FOUND = "Evaluation not found"

_read_service = ReadEvaluationsService(repository=SqlEvaluationRepository())

OrgIdParam = Annotated[str, Path(alias="orgId")]
ProjectIdParam = Annotated[str, Path(alias="projectId")]


@router.get(
    "/projects/{projectId}/evaluations",
    operation_id="listTrustEvaluations",
)
async def list_trust_evaluations(
    request: Request,
    org_id: OrgIdParam,
    project_id: ProjectIdParam,
    job_id: Annotated[str | None, Query(alias="jobId")] = None,
) -> JSONResponse:
    # Authorize before reading. A project outside the authenticated organization
    # yields a neutral not-found here, before any row is touched.
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)
    assert scope.org_id is not None
    assert scope.project_id is not None

    parsed_job_id: UUID | None = None
    if job_id is not None:
        parsed_job_id = _parse_uuid(job_id)
        if parsed_job_id is None:
            # An unparseable run identifier cannot match a persisted run, and an
            # empty list is the truthful answer for a filter that matches nothing.
            return _envelope([])

    evaluations = await _read_service.list_evaluations(
        org_id=scope.org_id,
        project_id=scope.project_id,
        run_id=parsed_job_id,
    )
    # No persisted evaluation is an empty collection, not an unavailable
    # capability. The absence is reported as fact rather than as an outage.
    return _envelope([_serialize(evaluation) for evaluation in evaluations])


@router.get(
    "/projects/{projectId}/evaluations/{evaluationId}",
    operation_id="getTrustEvaluation",
)
async def get_trust_evaluation(
    request: Request,
    org_id: OrgIdParam,
    project_id: ProjectIdParam,
    evaluation_id: Annotated[str, Path(alias="evaluationId")],
) -> JSONResponse:
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)
    assert scope.org_id is not None
    assert scope.project_id is not None

    parsed_evaluation_id = _parse_uuid(evaluation_id)
    if parsed_evaluation_id is None:
        # A malformed identifier gets the identical neutral answer as an unknown
        # one, so the shape of a rejected identifier reveals nothing.
        return _not_found()

    result = await _read_service.get_evaluation(
        org_id=scope.org_id,
        project_id=scope.project_id,
        evaluation_id=parsed_evaluation_id,
    )
    if isinstance(result, TrustEvaluationNotFound):
        return _not_found()
    return _envelope(_serialize(result))


@router.get("/trust", include_in_schema=False)
@router.get("/rubric", include_in_schema=False)
async def legacy_trust_boundary(
    request: Request,
    org_id: OrgIdParam,
) -> JSONResponse:
    """Keep old URLs honest until the web client switches to evaluations.

    Evaluations are project-owned, so an organization-wide Trust read has no
    scope to answer from and says so rather than guessing a project.
    """
    await get_request_scope(request, org_id=org_id)
    return capability_unavailable(_TRUST_UNAVAILABLE)


def _parse_uuid(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


def _not_found() -> JSONResponse:
    # The identifier is never echoed: an evaluation that exists in another
    # organization must be indistinguishable from one that never existed.
    return error_response(
        status_code=status.HTTP_404_NOT_FOUND,
        code="not_found",
        message=_EVALUATION_NOT_FOUND,
    )


def _envelope(data: object) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"data": data, "meta": {"requestId": str(uuid6.uuid7())}},
    )


def _serialize(evaluation: TrustEvaluationView) -> dict[str, object]:
    payload: dict[str, object] = {
        "evaluationId": str(evaluation.evaluation_id),
        "orgId": str(evaluation.org_id),
        "projectId": str(evaluation.project_id),
        "runId": str(evaluation.run_id),
        "stage": evaluation.stage.value,
        # Derived from the dimensions below on every read.
        "headlineScore": evaluation.headline_score,
        "scoredDimensionsCount": evaluation.scored_dimensions_count,
        "blockersCount": evaluation.blockers_count,
        "dimensions": [
            {
                "dimension": dimension.dimension.value,
                "status": dimension.status.value,
                # An unscored dimension serializes as null. Zero would assert a
                # judgement that was never made.
                "score": dimension.score,
                "rationale": dimension.rationale,
            }
            for dimension in evaluation.dimensions
        ],
        "gates": [
            {
                "gateName": gate.gate_name,
                "passed": gate.passed,
                "severity": gate.severity.value,
                "details": gate.details,
            }
            for gate in evaluation.gates
        ],
        "provenance": {
            "rubricVersion": evaluation.provenance.rubric_version,
            "promptVersion": evaluation.provenance.prompt_version,
            "policyVersion": evaluation.provenance.policy_version,
            "requestedModel": evaluation.provenance.requested_model,
            "returnedModel": evaluation.provenance.returned_model,
            "inputSha256": evaluation.provenance.input_sha256,
            "latencyMs": evaluation.provenance.latency_ms,
            "totalTokens": evaluation.provenance.total_tokens,
            "repairCount": evaluation.provenance.repair_count,
        },
        "createdAt": evaluation.created_at.isoformat(),
    }
    if evaluation.critique is not None:
        payload["critique"] = evaluation.critique
    return payload

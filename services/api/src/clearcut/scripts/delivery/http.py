"""Canonical screenplay import and read HTTP boundaries."""

from typing import Annotated, Literal
from uuid import UUID

import uuid6
from clearcut.delivery_errors import error_response
from clearcut.identity.delivery.scope import RequestScope, get_request_scope
from clearcut.organizations.delivery.http import verify_csrf_origin
from clearcut.scripts.adapters.sql_import_repository import ProjectScriptProjection
from clearcut.scripts.application.import_script import (
    MAX_SCRIPT_SIZE_BYTES,
    AdjacentDiffView,
    ImportArtifactView,
    ImportConflictError,
    ImportNotFoundError,
    ImportScriptService,
    ImportUnavailableError,
    ImportValidationError,
    ParseRunView,
    ScriptVersionView,
)
from fastapi import (
    APIRouter,
    File,
    Header,
    HTTPException,
    Path,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1", tags=["scripts", "uploads"])

OrgIdParam = Annotated[str, Path(alias="orgId")]
ProjectIdParam = Annotated[str, Path(alias="projectId")]
ArtifactIdParam = Annotated[UUID, Path(alias="artifactId")]
RunIdParam = Annotated[UUID, Path(alias="runId")]
VersionIdParam = Annotated[UUID, Path(alias="versionId")]


class CreateCapabilityBody(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(alias="contentType", min_length=1, max_length=100)


class CanonicalPasteImportBody(BaseModel):
    raw_text: str = Field(alias="rawText", min_length=1)
    format: Literal["fountain", "fdx", "raw"]


def _service(request: Request) -> ImportScriptService:
    return request.app.state.import_script_service


async def _project_scope(
    request: Request, org_id: str, project_id: str
) -> tuple[RequestScope, UUID, UUID]:
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)
    if scope.org_id is None or scope.project_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found in organization",
        )
    return scope, scope.org_id, scope.project_id


def _meta(*, total_count: int | None = None) -> dict[str, str | int]:
    result: dict[str, str | int] = {"requestId": str(uuid6.uuid7())}
    if total_count is not None:
        result["totalCount"] = total_count
    return result


def _expected_error(error: Exception) -> JSONResponse:
    if isinstance(error, ImportValidationError):
        return error_response(
            status_code=error.status_code,
            code="validation_failed",
            message=str(error),
        )
    if isinstance(error, ImportNotFoundError):
        return error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="not_found",
            message=str(error),
        )
    if isinstance(error, ImportConflictError):
        return error_response(
            status_code=status.HTTP_409_CONFLICT,
            code="conflict",
            message=str(error),
        )
    if isinstance(error, ImportUnavailableError):
        return error_response(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="capability_unavailable",
            message=str(error),
            retryable=True,
        )
    raise error


def _artifact_data(artifact: ImportArtifactView) -> dict[str, object]:
    return {
        "artifactId": str(artifact.artifact_id),
        "projectId": str(artifact.project_id),
        "filename": artifact.filename,
        "contentType": artifact.content_type,
        "sizeBytes": artifact.size_bytes,
        "sha256": artifact.sha256_hash,
        "status": artifact.status,
        "createdAt": artifact.created_at.isoformat(),
    }


def _parse_run_data(run: ParseRunView) -> dict[str, object]:
    return {
        "runId": str(run.run_id),
        "artifactId": str(run.artifact_id),
        "status": run.status,
        "parserName": run.parser_name,
        "parserVersion": run.parser_version,
        "sceneCount": run.scene_count,
        "elementCount": run.element_count,
        "warnings": [
            {
                "code": warning.code,
                "line": warning.line_number,
                "message": warning.message,
            }
            for warning in run.warnings
        ],
        "warningsAccepted": run.warnings_accepted,
        "acceptedAt": run.accepted_at.isoformat() if run.accepted_at else None,
        "createdAt": run.created_at.isoformat(),
        "completedAt": run.completed_at.isoformat(),
    }


def _version_data(version: ScriptVersionView) -> dict[str, object]:
    return {
        "versionId": str(version.version_id),
        "scriptId": str(version.script_id),
        "projectId": str(version.project_id),
        "versionNumber": version.version_number,
        "revisionLabel": version.revision_label,
        "title": version.title,
        "ordinal": version.version_number,
        "sourceArtifactId": (
            str(version.source_artifact_id) if version.source_artifact_id else None
        ),
        "parseRunId": str(version.parse_run_id) if version.parse_run_id else None,
        "sourceHash": version.source_hash,
        "parserVersion": version.parser_version,
        "sceneCount": version.scene_count,
        "elementCount": version.element_count,
        "predecessorVersionId": (
            str(version.predecessor_version_id) if version.predecessor_version_id else None
        ),
        "committedByUserId": (
            str(version.committed_by_user_id) if version.committed_by_user_id else None
        ),
        "createdAt": version.created_at.isoformat(),
    }


def _adjacent_diff_data(diff: AdjacentDiffView) -> dict[str, object]:
    return {
        "diffId": str(diff.diff_id),
        "projectId": str(diff.project_id),
        "scriptId": str(diff.script_id),
        "beforeVersionId": str(diff.before_version_id),
        "afterVersionId": str(diff.after_version_id),
        "beforeVersionNumber": diff.before_version_number,
        "afterVersionNumber": diff.after_version_number,
        "algorithmVersion": diff.algorithm_version,
        "impactCounts": dict(diff.impact_counts),
        "changes": [
            {
                "beforeElementId": (
                    str(change.before_element_id) if change.before_element_id else None
                ),
                "afterElementId": (
                    str(change.after_element_id) if change.after_element_id else None
                ),
                "beforeOrdinal": change.before_ordinal,
                "afterOrdinal": change.after_ordinal,
                "beforeText": change.before_text,
                "afterText": change.after_text,
                "changeKind": change.change_kind,
                "confidence": change.confidence,
            }
            for change in diff.changes
        ],
        "createdAt": diff.created_at.isoformat(),
    }


def _script_data(script: ProjectScriptProjection) -> dict[str, object]:
    return {
        "title": script.title,
        "version": script.version_label,
        "versionId": str(script.version_id),
        "scenes": [
            {
                "number": scene.number,
                "slug": scene.slug,
                "page": scene.page,
                "lines": [
                    {
                        "type": line.element_type,
                        "text": line.text,
                        **({"flag": line.flag} if line.flag else {}),
                    }
                    for line in scene.lines
                ],
            }
            for scene in script.scenes
        ],
    }


@router.get(
    "/organizations/{orgId}/projects/{projectId}/script",
    operation_id="getProjectScript",
)
async def get_project_script(request: Request, org_id: OrgIdParam, project_id: ProjectIdParam):
    _, scope_org_id, scope_project_id = await _project_scope(request, org_id, project_id)
    script = await _service(request).get_current_script(
        org_id=scope_org_id,
        project_id=scope_project_id,
    )
    if script is None:
        return error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="not_found",
            message="No committed screenplay version exists for this project.",
        )
    return {"data": _script_data(script), "meta": _meta()}


@router.post(
    "/organizations/{orgId}/projects/{projectId}/upload-capabilities",
    status_code=status.HTTP_201_CREATED,
    operation_id="createUploadCapability",
)
async def create_upload_capability(
    request: Request,
    org_id: OrgIdParam,
    project_id: ProjectIdParam,
    body: CreateCapabilityBody,
):
    verify_csrf_origin(request)
    scope, scope_org_id, scope_project_id = await _project_scope(request, org_id, project_id)
    try:
        capability = await _service(request).create_upload_capability(
            org_id=scope_org_id,
            project_id=scope_project_id,
            actor_id=scope.user_id,
            filename=body.filename,
            content_type=body.content_type,
        )
    except ImportValidationError as error:
        return _expected_error(error)
    return {
        "data": {
            "capabilityId": str(capability.capability_id),
            "uploadUrl": capability.upload_url,
            "nonce": capability.nonce,
            "expiresAt": capability.expires_at.isoformat(),
        },
        "meta": _meta(),
    }


@router.post(
    "/organizations/{orgId}/projects/{projectId}/import-artifacts/{artifactId}:finalize",
    operation_id="finalizeImportArtifact",
)
async def finalize_import_artifact(
    request: Request,
    org_id: OrgIdParam,
    project_id: ProjectIdParam,
    artifact_id: ArtifactIdParam,
    upload_nonce: Annotated[str, Header(alias="X-Upload-Nonce")],
    file: Annotated[UploadFile, File(...)],
):
    verify_csrf_origin(request)
    scope, scope_org_id, scope_project_id = await _project_scope(request, org_id, project_id)
    data = await file.read(MAX_SCRIPT_SIZE_BYTES + 1)
    try:
        artifact = await _service(request).finalize_upload(
            org_id=scope_org_id,
            project_id=scope_project_id,
            actor_id=scope.user_id,
            capability_id=artifact_id,
            nonce=upload_nonce,
            filename=file.filename or "",
            content_type=file.content_type,
            data=data,
        )
    except (
        ImportValidationError,
        ImportNotFoundError,
        ImportConflictError,
        ImportUnavailableError,
    ) as error:
        return _expected_error(error)
    return {"data": _artifact_data(artifact), "meta": _meta()}


@router.post(
    "/organizations/{orgId}/projects/{projectId}/paste-imports",
    status_code=status.HTTP_201_CREATED,
    operation_id="createPasteImport",
)
async def create_paste_import(
    request: Request,
    org_id: OrgIdParam,
    project_id: ProjectIdParam,
    body: CanonicalPasteImportBody,
):
    verify_csrf_origin(request)
    scope, scope_org_id, scope_project_id = await _project_scope(request, org_id, project_id)
    try:
        artifact = await _service(request).create_paste_import(
            org_id=scope_org_id,
            project_id=scope_project_id,
            actor_id=scope.user_id,
            raw_text=body.raw_text,
            source_format=body.format,
        )
    except ImportValidationError as error:
        return _expected_error(error)
    return {"data": _artifact_data(artifact), "meta": _meta()}


@router.post(
    "/organizations/{orgId}/projects/{projectId}/import-artifacts/{artifactId}:parse",
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="parseImportArtifact",
)
async def parse_import_artifact(
    request: Request,
    org_id: OrgIdParam,
    project_id: ProjectIdParam,
    artifact_id: ArtifactIdParam,
):
    verify_csrf_origin(request)
    scope, scope_org_id, scope_project_id = await _project_scope(request, org_id, project_id)
    try:
        run = await _service(request).parse_artifact(
            org_id=scope_org_id,
            project_id=scope_project_id,
            actor_id=scope.user_id,
            artifact_id=artifact_id,
        )
    except (ImportValidationError, ImportNotFoundError, ImportUnavailableError) as error:
        return _expected_error(error)
    return {"data": _parse_run_data(run), "meta": _meta()}


@router.post(
    "/organizations/{orgId}/projects/{projectId}/parse-runs/{runId}:acceptWarnings",
    operation_id="acceptParseWarnings",
)
async def accept_parse_warnings(
    request: Request,
    org_id: OrgIdParam,
    project_id: ProjectIdParam,
    run_id: RunIdParam,
):
    verify_csrf_origin(request)
    scope, scope_org_id, scope_project_id = await _project_scope(request, org_id, project_id)
    try:
        run = await _service(request).accept_warnings(
            org_id=scope_org_id,
            project_id=scope_project_id,
            actor_id=scope.user_id,
            run_id=run_id,
        )
    except (ImportNotFoundError, ImportConflictError) as error:
        return _expected_error(error)
    return {"data": _parse_run_data(run), "meta": _meta()}


@router.post(
    "/organizations/{orgId}/projects/{projectId}/parse-runs/{runId}:commitVersion",
    status_code=status.HTTP_201_CREATED,
    operation_id="commitScriptVersion",
)
async def commit_script_version(
    request: Request,
    org_id: OrgIdParam,
    project_id: ProjectIdParam,
    run_id: RunIdParam,
):
    verify_csrf_origin(request)
    scope, scope_org_id, scope_project_id = await _project_scope(request, org_id, project_id)
    try:
        version = await _service(request).commit_version_one(
            org_id=scope_org_id,
            project_id=scope_project_id,
            run_id=run_id,
            actor_id=scope.user_id,
        )
    except (ImportNotFoundError, ImportConflictError) as error:
        return _expected_error(error)
    return {"data": _version_data(version), "meta": _meta()}


@router.get(
    "/organizations/{orgId}/projects/{projectId}/script-versions",
    operation_id="listProjectVersions",
)
async def list_project_versions(
    request: Request,
    org_id: OrgIdParam,
    project_id: ProjectIdParam,
) -> dict:
    _, scope_org_id, scope_project_id = await _project_scope(request, org_id, project_id)
    versions = await _service(request).list_versions(
        org_id=scope_org_id,
        project_id=scope_project_id,
    )
    return {
        "data": [_version_data(version) for version in versions],
        "meta": _meta(total_count=len(versions)),
    }


@router.get(
    "/organizations/{orgId}/projects/{projectId}/script-versions/{versionId}",
    operation_id="getProjectVersion",
)
async def get_project_version(
    request: Request,
    org_id: OrgIdParam,
    project_id: ProjectIdParam,
    version_id: VersionIdParam,
):
    _, scope_org_id, scope_project_id = await _project_scope(request, org_id, project_id)
    version = await _service(request).get_version(
        org_id=scope_org_id,
        project_id=scope_project_id,
        version_id=version_id,
    )
    if version is None:
        return error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="not_found",
            message="Script version was not found.",
        )
    return {"data": _version_data(version), "meta": _meta()}


@router.get(
    "/organizations/{orgId}/projects/{projectId}/script-versions/{versionId}/diff",
    operation_id="getScriptVersionDiff",
)
async def get_script_version_diff(
    request: Request,
    org_id: OrgIdParam,
    project_id: ProjectIdParam,
    version_id: VersionIdParam,
):
    _, scope_org_id, scope_project_id = await _project_scope(request, org_id, project_id)
    diff = await _service(request).get_adjacent_diff(
        org_id=scope_org_id,
        project_id=scope_project_id,
        after_version_id=version_id,
    )
    if diff is None:
        # Neutral 404 for a foreign project/version, v1, or any version without an
        # adjacent predecessor diff. The scope check above already denied cross-tenant
        # access; here a missing diff is indistinguishable from a missing version.
        return error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="not_found",
            message="No adjacent diff exists for this script version.",
        )
    return {"data": _adjacent_diff_data(diff), "meta": _meta()}

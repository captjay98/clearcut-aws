from typing import Annotated
from uuid import UUID

from clearcut.organizations.delivery.http import get_authenticated_user_id, verify_csrf_origin
from clearcut.scripts.application.upload_service import UploadService
from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1", tags=["scripts", "uploads"])


class CreateCapabilityBody(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(alias="contentType", min_length=1, max_length=100)


@router.post(
    "/organizations/{org_id}/projects/{project_id}/upload-capabilities",
    status_code=status.HTTP_201_CREATED,
)
async def create_upload_capability(
    org_id: UUID,
    project_id: UUID,
    body: CreateCapabilityBody,
    request: Request,
) -> dict:
    verify_csrf_origin(request)
    actor_id = await get_authenticated_user_id(request)
    upload_service: UploadService = request.app.state.upload_service

    capability, upload_url = await upload_service.create_upload_capability(
        org_id=org_id,
        project_id=project_id,
        actor_id=actor_id,
        filename=body.filename,
        content_type=body.content_type,
    )

    return {
        "data": {
            "capabilityId": str(capability.capability_id),
            "uploadUrl": upload_url,
            "nonce": capability.nonce,
            "expiresAt": capability.expires_at.isoformat(),
        },
        "meta": {"requestId": "req_upload_cap"},
    }


@router.post(
    "/organizations/{org_id}/projects/{project_id}/import-artifacts/finalize",
    status_code=status.HTTP_201_CREATED,
)
async def finalize_import_artifact(
    org_id: UUID,
    project_id: UUID,
    capability_id: UUID,
    request: Request,
    file: Annotated[UploadFile, File(...)],
) -> dict:
    verify_csrf_origin(request)
    actor_id = await get_authenticated_user_id(request)
    upload_service: UploadService = request.app.state.upload_service

    data = await file.read()
    try:
        artifact = await upload_service.finalize_upload(
            org_id=org_id,
            project_id=project_id,
            actor_id=actor_id,
            capability_id=capability_id,
            data=data,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from None

    return {
        "data": {
            "artifactId": str(artifact.artifact_id),
            "filename": artifact.filename,
            "contentType": artifact.content_type,
            "sizeBytes": artifact.size_bytes,
            "sha256": artifact.sha256_hash,
            "status": artifact.status,
            "createdAt": artifact.created_at.isoformat(),
        },
        "meta": {"requestId": "req_finalize_artifact"},
    }

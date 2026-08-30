from typing import Annotated
from uuid import UUID

import sqlalchemy as sa
from clearcut.database import session_scope
from clearcut.organizations.delivery.http import get_authenticated_user_id, verify_csrf_origin
from clearcut.scripts.application.upload_service import UploadService
from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1", tags=["scripts", "uploads"])


class CreateCapabilityBody(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(alias="contentType", min_length=1, max_length=100)


@router.get("/organizations/{org_id}/projects/{project_id}/script")
async def get_project_script(org_id: str, project_id: str) -> JSONResponse:
    async with session_scope() as session:
        res = await session.execute(
            sa.text("""
                SELECT e.id, e.version_id, e.ordinal, e.element_type, e.text, e.scene_number, e.page_number,
                       s.tag as flag
                FROM script_elements e
                LEFT JOIN element_spans s ON s.element_id = e.id
                ORDER BY e.ordinal ASC
            """)
        )
        rows = res.fetchall()

        scenes_map = {}
        for r in rows:
            sc_num = r.scene_number or 1
            if sc_num not in scenes_map:
                scenes_map[sc_num] = {
                    "number": sc_num,
                    "slug": f"SCENE {sc_num}",
                    "page": r.page_number or 1,
                    "lines": [],
                }
            if r.element_type == "scene_heading":
                scenes_map[sc_num]["slug"] = r.text
            else:
                line_obj = {"type": r.element_type, "text": r.text}
                if r.flag:
                    line_obj["flag"] = r.flag
                scenes_map[sc_num]["lines"].append(line_obj)

        scenes = list(scenes_map.values())

        return JSONResponse(content={
            "data": {
                "title": "Borrowed Light",
                "version": "v1",
                "scenes": scenes,
            }
        })


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

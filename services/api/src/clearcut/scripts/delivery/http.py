import hashlib
import json
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID
import uuid6
import sqlalchemy as sa
from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field

from clearcut.database import session_scope
from clearcut.identity.delivery.scope import get_request_scope
from clearcut.organizations.delivery.http import verify_csrf_origin
from clearcut.scripts.application.upload_service import UploadService

router = APIRouter(prefix="/api/v1", tags=["scripts", "uploads"])


class CreateCapabilityBody(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(alias="contentType", min_length=1, max_length=100)


class PasteImportBody(BaseModel):
    text: str = Field(min_length=1)
    title: str = Field(default="Pasted Script", min_length=1, max_length=200)


class CommitVersionBody(BaseModel):
    title: str | None = None
    sourceArtifactId: str | None = None
    diffNotes: str | None = None


@router.get("/organizations/{org_id}/projects/{project_id}/script")
async def get_project_script(org_id: str, project_id: str, request: Request) -> dict:
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)
    async with session_scope() as session:
        # Fetch latest version for this project
        ver_res = await session.execute(
            sa.text("""
                SELECT v.id, v.ordinal, s.title
                FROM script_versions v
                JOIN scripts s ON s.id = v.script_id
                WHERE v.org_id = :org_id AND v.project_id = :project_id
                ORDER BY v.ordinal DESC
                LIMIT 1
            """),
            {"org_id": str(scope.org_id), "project_id": str(scope.project_id)},
        )
        ver_row = ver_res.mappings().first()

        scenes = []
        script_title = ver_row["title"] if ver_row else "Untitled Script"
        version_label = f"v{ver_row['ordinal']}" if ver_row else "v1"

        if ver_row:
            res = await session.execute(
                sa.text("""
                    SELECT e.id, e.version_id, e.ordinal, e.element_type, e.text, e.scene_number, e.page_number,
                           s.tag as flag
                    FROM script_elements e
                    LEFT JOIN element_spans s ON s.element_id = e.id
                    WHERE e.version_id = :version_id
                    ORDER BY e.ordinal ASC
                """),
                {"version_id": str(ver_row["id"])},
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

        return {
            "data": {
                "title": script_title,
                "version": version_label,
                "scenes": scenes,
            },
            "meta": {"requestId": "req_get_script"},
        }


@router.post(
    "/organizations/{org_id}/projects/{project_id}/upload-capabilities",
    status_code=status.HTTP_201_CREATED,
)
async def create_upload_capability(
    org_id: str,
    project_id: str,
    body: CreateCapabilityBody,
    request: Request,
) -> dict:
    verify_csrf_origin(request)
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)
    upload_service: UploadService = request.app.state.upload_service

    capability, upload_url = await upload_service.create_upload_capability(
        org_id=scope.org_id,
        project_id=scope.project_id,
        actor_id=scope.user_id,
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
    org_id: str,
    project_id: str,
    capability_id: str,
    request: Request,
    file: Annotated[UploadFile, File(...)],
) -> dict:
    verify_csrf_origin(request)
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)
    upload_service: UploadService = request.app.state.upload_service

    data = await file.read()
    try:
        artifact = await upload_service.finalize_upload(
            org_id=scope.org_id,
            project_id=scope.project_id,
            actor_id=scope.user_id,
            capability_id=UUID(capability_id),
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


@router.post(
    "/organizations/{org_id}/projects/{project_id}/imports:paste",
    status_code=status.HTTP_201_CREATED,
)
async def create_paste_import(
    org_id: str,
    project_id: str,
    body: PasteImportBody,
    request: Request,
) -> dict:
    verify_csrf_origin(request)
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)
    artifact_id = uuid6.uuid7()
    sha256 = hashlib.sha256(body.text.encode("utf-8")).hexdigest()
    now = datetime.now(UTC)

    return {
        "data": {
            "artifactId": str(artifact_id),
            "filename": f"{body.title}.txt",
            "contentType": "text/plain",
            "sizeBytes": len(body.text.encode("utf-8")),
            "sha256": sha256,
            "status": "ready_to_parse",
            "createdAt": now.isoformat(),
        },
        "meta": {"requestId": "req_paste_import"},
    }


@router.get("/organizations/{org_id}/projects/{project_id}/script-versions")
async def list_project_versions(
    org_id: str, project_id: str, request: Request
) -> dict:
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)
    async with session_scope() as session:
        res = await session.execute(
            sa.text("""
                SELECT v.id, v.script_id, v.ordinal, v.source_hash, v.parser_version, v.created_at, s.title
                FROM script_versions v
                JOIN scripts s ON s.id = v.script_id
                WHERE v.org_id = :org_id AND v.project_id = :project_id
                ORDER BY v.ordinal DESC
            """),
            {"org_id": str(scope.org_id), "project_id": str(scope.project_id)},
        )
        rows = res.fetchall()
        return {
            "data": [
                {
                    "versionId": str(r.id),
                    "scriptId": str(r.script_id),
                    "title": r.title,
                    "ordinal": r.ordinal,
                    "sourceHash": r.source_hash,
                    "parserVersion": r.parser_version,
                    "createdAt": r.created_at.isoformat() if hasattr(r.created_at, "isoformat") else str(r.created_at),
                }
                for r in rows
            ],
            "meta": {"requestId": "req_list_versions", "count": len(rows)},
        }

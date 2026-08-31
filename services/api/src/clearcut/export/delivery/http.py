import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID
import uuid6
import sqlalchemy as sa
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from clearcut.database import session_scope
from clearcut.identity.delivery.scope import get_request_scope
from clearcut.organizations.delivery.http import verify_csrf_origin

router = APIRouter(
    prefix="/api/v1/organizations/{org_id}/projects/{project_id}",
    tags=["export", "reports"],
)


class CreateReportSnapshotBody(BaseModel):
    scriptVersionId: str | None = None


class ReleaseReportBody(BaseModel):
    snapshotId: str
    attestation: str = Field(min_length=1)


@router.get("/report")
async def get_report_status(org_id: str, project_id: str, request: Request) -> dict:
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)
    async with session_scope() as session:
        res = await session.execute(
            sa.text("""
                SELECT s.id, s.script_version_id, s.status, s.content_hash, s.created_at,
                       v.ordinal as version_ordinal
                FROM report_snapshots s
                JOIN script_versions v ON v.id = s.script_version_id
                WHERE s.org_id = :org_id AND s.project_id = :project_id
                ORDER BY s.created_at DESC
                LIMIT 1
            """),
            {"org_id": str(scope.org_id), "project_id": str(scope.project_id)},
        )
        row = res.mappings().first()
        if row:
            return {
                "data": {
                    "snapshotId": str(row["id"]),
                    "versionLabel": f"v{row['version_ordinal']}",
                    "contentHash": row["content_hash"],
                    "status": row["status"],
                    "isReleased": row["status"] == "released",
                    "createdAt": row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else str(row["created_at"]),
                }
            }

        # If no snapshot yet, return initial draft status
        return {
            "data": {
                "snapshotId": None,
                "versionLabel": "v1",
                "contentHash": None,
                "status": "draft",
                "isReleased": False,
            }
        }


@router.post("/report-snapshots", status_code=status.HTTP_201_CREATED)
async def create_report_snapshot(
    org_id: str, project_id: str, body: CreateReportSnapshotBody, request: Request
) -> dict:
    verify_csrf_origin(request)
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)
    now = datetime.now(UTC)
    snapshot_id = uuid6.uuid7()

    async with session_scope() as session:
        # Resolve script version
        if body.scriptVersionId:
            ver_id = UUID(body.scriptVersionId)
        else:
            ver_res = await session.execute(
                sa.text("""
                    SELECT id FROM script_versions
                    WHERE org_id = :org_id AND project_id = :project_id
                    ORDER BY ordinal DESC LIMIT 1
                """),
                {"org_id": str(scope.org_id), "project_id": str(scope.project_id)},
            )
            ver_row = ver_res.mappings().first()
            if not ver_row:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No script version found to snapshot")
            ver_id = UUID(str(ver_row["id"]))

        # Compute binding manifest and content hash
        manifest = {
            "org_id": str(scope.org_id),
            "project_id": str(scope.project_id),
            "script_version_id": str(ver_id),
            "generated_at": now.isoformat(),
        }
        manifest_json = json.dumps(manifest, sort_keys=True)
        content_hash = hashlib.sha256(manifest_json.encode("utf-8")).hexdigest()

        await session.execute(
            sa.text("""
                INSERT INTO report_snapshots (id, org_id, project_id, script_version_id, status, content_hash, binding_manifest, created_at)
                VALUES (:id, :org_id, :project_id, :script_version_id, 'draft', :content_hash, :binding_manifest, :created_at)
            """),
            {
                "id": str(snapshot_id),
                "org_id": str(scope.org_id),
                "project_id": str(scope.project_id),
                "script_version_id": str(ver_id),
                "content_hash": content_hash,
                "binding_manifest": manifest_json,
                "created_at": now,
            },
        )

    return {
        "data": {
            "snapshotId": str(snapshot_id),
            "orgId": str(scope.org_id),
            "projectId": str(scope.project_id),
            "scriptVersionId": str(ver_id),
            "status": "draft",
            "contentHash": content_hash,
            "createdAt": now.isoformat(),
        },
        "meta": {"requestId": "req_create_snapshot"},
    }


@router.post("/report-releases", status_code=status.HTTP_201_CREATED)
async def release_report(
    org_id: str, project_id: str, body: ReleaseReportBody, request: Request
) -> dict:
    verify_csrf_origin(request)
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)
    if scope.role not in ["owner", "admin", "reviewer"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied to release report")

    release_id = uuid6.uuid7()
    audit_id = uuid6.uuid7()
    now = datetime.now(UTC)

    async with session_scope() as session:
        # Verify snapshot
        snap_res = await session.execute(
            sa.text("""
                SELECT id, script_version_id, content_hash FROM report_snapshots
                WHERE id = :id AND org_id = :org_id AND project_id = :project_id
            """),
            {
                "id": body.snapshotId,
                "org_id": str(scope.org_id),
                "project_id": str(scope.project_id),
            },
        )
        snap_row = snap_res.mappings().first()
        if not snap_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report snapshot not found")

        # Update snapshot status
        await session.execute(
            sa.text("UPDATE report_snapshots SET status = 'released' WHERE id = :id"),
            {"id": body.snapshotId},
        )

        # Log immutable audit event
        await session.execute(
            sa.text("""
                INSERT INTO audit_events (id, org_id, project_id, action, actor_id, target_id, target_type, details, created_at)
                VALUES (:id, :org_id, :project_id, 'report.released', :actor_id, :target_id, 'report_snapshot', :details, :created_at)
            """),
            {
                "id": str(audit_id),
                "org_id": str(scope.org_id),
                "project_id": str(scope.project_id),
                "actor_id": str(scope.user_id),
                "target_id": body.snapshotId,
                "details": json.dumps({"attestation": body.attestation, "contentHash": snap_row["content_hash"]}),
                "created_at": now,
            },
        )

    return {
        "data": {
            "releaseId": str(release_id),
            "snapshotId": body.snapshotId,
            "status": "released",
            "attestation": body.attestation,
            "releasedAt": now.isoformat(),
        },
        "meta": {"requestId": "req_release_report"},
    }

"""Tenant-scoped immutable clearance report generation, release, and export."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Annotated, Any

import sqlalchemy as sa
import uuid6
from clearcut.database import session_scope
from clearcut.export.application.report_pipeline import (
    LEGAL_BOUNDARY,
    REPORT_GENERATOR_VERSION,
    REPORT_SCHEMA_VERSION,
    content_hash,
    payload_hash,
    render_html,
)
from clearcut.identity.delivery.scope import get_request_scope
from clearcut.organizations.delivery.http import verify_csrf_origin
from fastapi import APIRouter, HTTPException, Path, Request, status
from fastapi.responses import HTMLResponse
from pydantic import UUID7, BaseModel, Field

router = APIRouter(
    prefix="/api/v1/organizations/{orgId}/projects/{projectId}",
    tags=["export", "reports"],
)

OrgIdParam = Annotated[str, Path(alias="orgId")]
ProjectIdParam = Annotated[str, Path(alias="projectId")]
SnapshotIdParam = Annotated[str, Path(alias="snapshotId")]
ReleaseIdParam = Annotated[str, Path(alias="releaseId")]


class CreateReportSnapshotBody(BaseModel):
    script_version_id: UUID7 | None = Field(default=None, alias="scriptVersionId")


class CanonicalReleaseReportBody(BaseModel):
    attestation: str = Field(min_length=40, max_length=2000)


class ReleaseReportBody(BaseModel):
    snapshot_id: str = Field(alias="snapshotId")
    attestation: str = Field(min_length=40, max_length=2000)


def _request_meta(*, total_count: int | None = None) -> dict[str, object]:
    meta: dict[str, object] = {"requestId": str(uuid6.uuid7())}
    if total_count is not None:
        meta["totalCount"] = total_count
    return meta


def _as_json(value: object) -> dict[str, Any]:
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    if isinstance(value, dict):
        return value
    raise RuntimeError("Stored report binding manifest is not an object")


def _iso(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).isoformat()
        except ValueError:
            return value
    return str(value)


def _require_governed_report_role(scope: Any) -> None:
    if scope.role not in {"owner", "admin", "reviewer"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Report generation and release require an authorized accountable reviewer",
        )


def _validate_release_attestation(attestation: str) -> str:
    normalized = " ".join(attestation.split())
    lowered = normalized.lower()
    if "not legal advice" not in lowered or "final legal clearance" not in lowered:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Release attestation must acknowledge that the frozen snapshot is not legal "
                "advice or final legal clearance"
            ),
        )
    return normalized


async def _authorize(request: Request, org_id: str, project_id: str) -> Any:
    return await get_request_scope(request, org_id=org_id, project_id=project_id)


async def _version_binding(
    session: Any,
    *,
    org_id: str,
    project_id: str,
    version_id: str | None,
) -> dict[str, Any]:
    requested_filter = "AND version.id = :version_id" if version_id else ""
    result = await session.execute(
        sa.text(
            f"""
            SELECT version.id, version.script_id, version.ordinal, version.source_hash,
                   version.parser_version, version.created_at,
                   script.title AS script_title, project.title AS project_title
            FROM script_versions AS version
            JOIN scripts AS script
              ON script.id = version.script_id
             AND script.org_id = version.org_id
             AND script.project_id = version.project_id
            JOIN projects AS project
              ON project.id = version.project_id
             AND project.org_id = version.org_id
            WHERE version.org_id = :org_id
              AND version.project_id = :project_id
              {requested_filter}
            ORDER BY version.ordinal DESC
            LIMIT 1
            """
        ),
        {
            "org_id": org_id,
            "project_id": project_id,
            "version_id": version_id,
        },
    )
    row = result.mappings().first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Script version not found in project",
        )
    if not row["source_hash"] or not row["parser_version"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Script version is missing required immutable report bindings",
        )
    return dict(row)


async def _assemble_manifest(
    session: Any,
    *,
    org_id: str,
    project_id: str,
    version: dict[str, Any],
) -> dict[str, Any]:
    item_rows = (
        (
            await session.execute(
                sa.text(
                    """
                SELECT id, category, text, status, workflow_status, research_status,
                       disposition_status, assigned_to_user_id, version, created_at
                FROM clearance_items
                WHERE org_id = :org_id AND project_id = :project_id
                  AND version_id = :version_id
                ORDER BY created_at, id
                """
                ),
                {
                    "org_id": org_id,
                    "project_id": project_id,
                    "version_id": str(version["id"]),
                },
            )
        )
        .mappings()
        .all()
    )

    claim_rows = (
        (
            await session.execute(
                sa.text(
                    """
                SELECT claim.id, claim.item_id, claim.stance, claim.authority_tier,
                       claim.claim_text, claim.provenance_excerpt, claim.created_at,
                       source.id AS source_id, source.url, source.title, source.publisher,
                       source.excerpt, source.origin, source.sha256_hash,
                       source.retrieved_at
                FROM evidence_claims AS claim
                JOIN source_snapshots AS source
                  ON source.id = claim.snapshot_id
                 AND source.org_id = claim.org_id
                 AND source.project_id = claim.project_id
                 AND source.item_id = claim.item_id
                JOIN clearance_items AS item
                  ON item.id = claim.item_id
                 AND item.org_id = claim.org_id
                 AND item.project_id = claim.project_id
                WHERE claim.org_id = :org_id AND claim.project_id = :project_id
                  AND item.version_id = :version_id
                ORDER BY claim.item_id, claim.created_at, claim.id
                """
                ),
                {
                    "org_id": org_id,
                    "project_id": project_id,
                    "version_id": str(version["id"]),
                },
            )
        )
        .mappings()
        .all()
    )

    conflict_rows = (
        (
            await session.execute(
                sa.text(
                    """
                SELECT conflict.id, conflict.item_id, conflict.description,
                       conflict.created_at
                FROM evidence_conflicts AS conflict
                JOIN clearance_items AS item
                  ON item.id = conflict.item_id
                 AND item.org_id = conflict.org_id
                 AND item.project_id = conflict.project_id
                WHERE conflict.org_id = :org_id AND conflict.project_id = :project_id
                  AND item.version_id = :version_id
                ORDER BY conflict.item_id, conflict.created_at, conflict.id
                """
                ),
                {
                    "org_id": org_id,
                    "project_id": project_id,
                    "version_id": str(version["id"]),
                },
            )
        )
        .mappings()
        .all()
    )

    decision_rows = (
        (
            await session.execute(
                sa.text(
                    """
                SELECT decision.id, decision.item_id, decision.actor_id,
                       decision.decision_kind, decision.decision_value,
                       decision.rationale, decision.resulting_version,
                       decision.created_at
                FROM governed_decision_records AS decision
                JOIN clearance_items AS item
                  ON item.id = decision.item_id
                 AND item.org_id = decision.org_id
                 AND item.project_id = decision.project_id
                WHERE decision.org_id = :org_id AND decision.project_id = :project_id
                  AND item.version_id = :version_id
                ORDER BY decision.item_id, decision.created_at, decision.id
                """
                ),
                {
                    "org_id": org_id,
                    "project_id": project_id,
                    "version_id": str(version["id"]),
                },
            )
        )
        .mappings()
        .all()
    )

    monitoring_count = int(
        await session.scalar(
            sa.text(
                """
                SELECT COUNT(*)
                FROM monitoring_watches AS watch
                JOIN clearance_items AS item
                  ON item.id = watch.item_id
                 AND item.org_id = watch.org_id
                 AND item.project_id = watch.project_id
                WHERE watch.org_id = :org_id AND watch.project_id = :project_id
                  AND item.version_id = :version_id
                """
            ),
            {
                "org_id": org_id,
                "project_id": project_id,
                "version_id": str(version["id"]),
            },
        )
        or 0
    )

    evaluation = (
        (
            await session.execute(
                sa.text(
                    """
                SELECT id, stage, headline_score, scored_dimensions_count,
                       blockers_count, created_at
                FROM agent_evaluations
                WHERE org_id = :org_id AND project_id = :project_id
                ORDER BY created_at DESC
                LIMIT 1
                """
                ),
                {"org_id": org_id, "project_id": project_id},
            )
        )
        .mappings()
        .first()
    )
    policy = (
        (
            await session.execute(
                sa.text(
                    """
                SELECT id, policy_version, prompt_version, lifecycle, created_at
                FROM protected_configurations
                WHERE org_id = :org_id
                ORDER BY created_at DESC
                LIMIT 1
                """
                ),
                {"org_id": org_id},
            )
        )
        .mappings()
        .first()
    )

    claims_by_item: dict[str, list[dict[str, Any]]] = {}
    for row in claim_rows:
        claims_by_item.setdefault(str(row["item_id"]), []).append(
            {
                "claimId": str(row["id"]),
                "stance": row["stance"],
                "authorityTier": row["authority_tier"],
                "claimText": row["claim_text"],
                "provenanceExcerpt": row["provenance_excerpt"],
                "source": {
                    "snapshotId": str(row["source_id"]),
                    "url": row["url"],
                    "title": row["title"],
                    "publisher": row["publisher"],
                    "excerpt": row["excerpt"],
                    "origin": row["origin"],
                    "sha256Hash": row["sha256_hash"],
                    "retrievedAt": _iso(row["retrieved_at"]),
                },
            }
        )

    conflicts_by_item: dict[str, list[dict[str, Any]]] = {}
    for row in conflict_rows:
        conflicts_by_item.setdefault(str(row["item_id"]), []).append(
            {
                "conflictId": str(row["id"]),
                "description": row["description"],
                "createdAt": _iso(row["created_at"]),
            }
        )

    decisions_by_item: dict[str, list[dict[str, Any]]] = {}
    for row in decision_rows:
        decisions_by_item.setdefault(str(row["item_id"]), []).append(
            {
                "decisionId": str(row["id"]),
                "actorId": str(row["actor_id"]),
                "kind": row["decision_kind"],
                "decision": row["decision_value"],
                "rationale": row["rationale"],
                "resultingVersion": row["resulting_version"],
                "createdAt": _iso(row["created_at"]),
            }
        )

    items: list[dict[str, Any]] = []
    for row in item_rows:
        item_id = str(row["id"])
        claims = claims_by_item.get(item_id, [])
        items.append(
            {
                "itemId": item_id,
                "category": row["category"],
                "entityName": row["text"],
                "status": row["status"],
                "workflowStatus": row["workflow_status"],
                "researchStatus": row["research_status"],
                "dispositionStatus": row["disposition_status"],
                "assignedTo": (
                    str(row["assigned_to_user_id"])
                    if row["assigned_to_user_id"] is not None
                    else None
                ),
                "itemVersion": row["version"],
                "claimCount": len(claims),
                "evidenceState": ("cited" if claims else "unresolved_zero_evidence"),
                "claims": claims,
                "conflicts": conflicts_by_item.get(item_id, []),
                "decisions": decisions_by_item.get(item_id, []),
            }
        )

    open_item_count = sum(item["status"] not in {"resolved", "closed"} for item in items)
    return {
        "schemaVersion": REPORT_SCHEMA_VERSION,
        "generatorVersion": REPORT_GENERATOR_VERSION,
        "project": {
            "projectId": project_id,
            "title": version["project_title"],
        },
        "scriptVersion": {
            "versionId": str(version["id"]),
            "scriptId": str(version["script_id"]),
            "scriptTitle": version["script_title"],
            "ordinal": version["ordinal"],
            "sourceHash": version["source_hash"],
            "parserVersion": version["parser_version"],
            "createdAt": _iso(version["created_at"]),
        },
        "items": items,
        "openItemCount": open_item_count,
        "monitoring": {"watchCount": monitoring_count},
        "evaluation": (
            {
                "status": "available",
                "evaluationId": str(evaluation["id"]),
                "stage": evaluation["stage"],
                "headlineScore": evaluation["headline_score"],
                "scoredDimensionsCount": evaluation["scored_dimensions_count"],
                "blockersCount": evaluation["blockers_count"],
                "createdAt": _iso(evaluation["created_at"]),
            }
            if evaluation
            else {"status": "unavailable"}
        ),
        "policyBinding": (
            {
                "status": "available",
                "configurationId": str(policy["id"]),
                "policyVersion": policy["policy_version"],
                "promptVersion": policy["prompt_version"],
                "lifecycle": policy["lifecycle"],
                "createdAt": _iso(policy["created_at"]),
            }
            if policy
            else {"status": "unavailable"}
        ),
        "legalBoundary": LEGAL_BOUNDARY,
    }


def _snapshot_projection(row: Any) -> dict[str, Any]:
    return {
        "snapshotId": str(row["id"]),
        "projectId": str(row["project_id"]),
        "versionId": str(row["script_version_id"]),
        "generatedAt": _iso(row["created_at"]),
        "status": row["status"],
        "contentHash": row["content_hash"],
        "bindingManifest": _as_json(row["binding_manifest"]),
        "artifactId": str(row["artifact_id"]),
    }


async def _snapshot_row(
    session: Any,
    *,
    org_id: str,
    project_id: str,
    snapshot_id: str,
) -> Any:
    return (
        (
            await session.execute(
                sa.text(
                    """
                SELECT snapshot.id, snapshot.org_id, snapshot.project_id,
                       snapshot.script_version_id, snapshot.status,
                       snapshot.content_hash, snapshot.binding_manifest,
                       snapshot.created_at, artifact.id AS artifact_id,
                       artifact.content_hash AS artifact_hash,
                       artifact.media_type, artifact.status AS artifact_status
                FROM report_snapshots AS snapshot
                JOIN export_artifacts AS artifact
                  ON artifact.snapshot_id = snapshot.id
                 AND artifact.org_id = snapshot.org_id
                 AND artifact.project_id = snapshot.project_id
                WHERE snapshot.id = :snapshot_id
                  AND snapshot.org_id = :org_id
                  AND snapshot.project_id = :project_id
                """
                ),
                {
                    "snapshot_id": snapshot_id,
                    "org_id": org_id,
                    "project_id": project_id,
                },
            )
        )
        .mappings()
        .first()
    )


@router.get("/report-preview", operation_id="previewReport")
async def preview_report(
    request: Request, org_id: OrgIdParam, project_id: ProjectIdParam
) -> dict[str, object]:
    scope = await _authorize(request, org_id, project_id)
    async with session_scope() as session:
        rows = (
            (
                await session.execute(
                    sa.text(
                        """
                    SELECT category, COUNT(*) AS item_count,
                           SUM(CASE WHEN status IN ('resolved', 'closed') THEN 1 ELSE 0 END)
                             AS resolved_count
                    FROM clearance_items
                    WHERE org_id = :org_id AND project_id = :project_id
                    GROUP BY category
                    ORDER BY category
                    """
                    ),
                    {
                        "org_id": str(scope.org_id),
                        "project_id": str(scope.project_id),
                    },
                )
            )
            .mappings()
            .all()
        )
    total = sum(int(row["item_count"]) for row in rows)
    resolved = sum(int(row["resolved_count"] or 0) for row in rows)
    unresolved = total - resolved
    return {
        "data": {
            "projectId": str(scope.project_id),
            "totalItems": total,
            "clearedItems": resolved,
            "flaggedItems": unresolved,
            "unresolvedRisk": unresolved,
            "categories": [
                {"category": row["category"], "count": int(row["item_count"])} for row in rows
            ],
        },
        "meta": _request_meta(),
    }


@router.get("/report", include_in_schema=False)
async def get_report_status(
    request: Request, org_id: OrgIdParam, project_id: ProjectIdParam
) -> dict[str, object]:
    scope = await _authorize(request, org_id, project_id)
    async with session_scope() as session:
        row = (
            (
                await session.execute(
                    sa.text(
                        """
                    SELECT snapshot.id, snapshot.org_id, snapshot.project_id,
                           snapshot.script_version_id, snapshot.status,
                           snapshot.content_hash, snapshot.binding_manifest,
                           snapshot.created_at, artifact.id AS artifact_id
                    FROM report_snapshots AS snapshot
                    JOIN export_artifacts AS artifact ON artifact.snapshot_id = snapshot.id
                    WHERE snapshot.org_id = :org_id AND snapshot.project_id = :project_id
                    ORDER BY snapshot.created_at DESC, snapshot.id DESC
                    LIMIT 1
                    """
                    ),
                    {
                        "org_id": str(scope.org_id),
                        "project_id": str(scope.project_id),
                    },
                )
            )
            .mappings()
            .first()
        )
    return {
        "data": _snapshot_projection(row) if row else None,
        "meta": _request_meta(),
    }


@router.post(
    "/report-snapshots",
    status_code=status.HTTP_201_CREATED,
    operation_id="generateReportSnapshot",
)
async def create_report_snapshot(
    request: Request,
    org_id: OrgIdParam,
    project_id: ProjectIdParam,
    body: CreateReportSnapshotBody,
) -> dict[str, object]:
    verify_csrf_origin(request)
    scope = await _authorize(request, org_id, project_id)
    _require_governed_report_role(scope)
    snapshot_id = uuid6.uuid7()
    artifact_id = uuid6.uuid7()
    audit_id = uuid6.uuid7()
    now = datetime.now(UTC)

    async with session_scope() as session:
        version = await _version_binding(
            session,
            org_id=str(scope.org_id),
            project_id=str(scope.project_id),
            version_id=(str(body.script_version_id) if body.script_version_id else None),
        )
        manifest = await _assemble_manifest(
            session,
            org_id=str(scope.org_id),
            project_id=str(scope.project_id),
            version=version,
        )
        manifest_hash = payload_hash(manifest)
        html_content = render_html(manifest, manifest_hash)
        artifact_hash = content_hash(html_content)
        await session.execute(
            sa.text(
                """
                INSERT INTO report_snapshots (
                    id, org_id, project_id, script_version_id, status,
                    content_hash, binding_manifest, created_at
                ) VALUES (
                    :id, :org_id, :project_id, :version_id, 'generated',
                    :content_hash, :binding_manifest, :created_at
                )
                """
            ),
            {
                "id": str(snapshot_id),
                "org_id": str(scope.org_id),
                "project_id": str(scope.project_id),
                "version_id": str(version["id"]),
                "content_hash": manifest_hash,
                "binding_manifest": json.dumps(manifest, sort_keys=True),
                "created_at": now,
            },
        )
        await session.execute(
            sa.text(
                """
                INSERT INTO export_artifacts (
                    id, snapshot_id, org_id, project_id, media_type,
                    content_hash, content, status, created_at
                ) VALUES (
                    :id, :snapshot_id, :org_id, :project_id, 'text/html',
                    :content_hash, :content, 'generated', :created_at
                )
                """
            ),
            {
                "id": str(artifact_id),
                "snapshot_id": str(snapshot_id),
                "org_id": str(scope.org_id),
                "project_id": str(scope.project_id),
                "content_hash": artifact_hash,
                "content": html_content,
                "created_at": now,
            },
        )
        await session.execute(
            sa.text(
                """
                INSERT INTO authoritative_audit_events (
                    id, org_id, project_id, actor_id, action,
                    target_type, target_id, payload_redacted, occurred_at,
                    correlation_id
                ) VALUES (
                    :id, :org_id, :project_id, :actor_id, 'report.generated',
                    'report_snapshot', :target_id, :payload, :occurred_at,
                    :id
                )
                """
            ),
            {
                "id": str(audit_id),
                "org_id": str(scope.org_id),
                "project_id": str(scope.project_id),
                "actor_id": str(scope.user_id),
                "target_id": str(snapshot_id),
                "payload": json.dumps(
                    {
                        "contentHash": manifest_hash,
                        "scriptVersionId": str(version["id"]),
                        "artifactId": str(artifact_id),
                    },
                    sort_keys=True,
                ),
                "occurred_at": now,
            },
        )

    return {
        "data": {
            "snapshotId": str(snapshot_id),
            "projectId": str(scope.project_id),
            "versionId": str(version["id"]),
            "generatedAt": now.isoformat(),
            "status": "generated",
            "contentHash": manifest_hash,
            "bindingManifest": manifest,
            "artifactId": str(artifact_id),
        },
        "meta": _request_meta(),
    }


@router.get("/report-snapshots/{snapshotId}", operation_id="getReportSnapshot")
async def get_report_snapshot(
    request: Request,
    org_id: OrgIdParam,
    project_id: ProjectIdParam,
    snapshot_id: SnapshotIdParam,
) -> dict[str, object]:
    scope = await _authorize(request, org_id, project_id)
    async with session_scope() as session:
        row = await _snapshot_row(
            session,
            org_id=str(scope.org_id),
            project_id=str(scope.project_id),
            snapshot_id=snapshot_id,
        )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return {"data": _snapshot_projection(row), "meta": _request_meta()}


@router.post(
    "/report-snapshots/{snapshotId}:release",
    operation_id="releaseReport",
)
async def canonical_release_report(
    request: Request,
    org_id: OrgIdParam,
    project_id: ProjectIdParam,
    snapshot_id: SnapshotIdParam,
    body: CanonicalReleaseReportBody,
) -> dict[str, object]:
    verify_csrf_origin(request)
    scope = await _authorize(request, org_id, project_id)
    _require_governed_report_role(scope)
    attestation = _validate_release_attestation(body.attestation)
    release_id = uuid6.uuid7()
    audit_id = uuid6.uuid7()
    now = datetime.now(UTC)

    async with session_scope() as session:
        snapshot = await _snapshot_row(
            session,
            org_id=str(scope.org_id),
            project_id=str(scope.project_id),
            snapshot_id=snapshot_id,
        )
        if snapshot is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Report not found",
            )
        existing = (
            (
                await session.execute(
                    sa.text(
                        """
                    SELECT id, released_by, attestation, created_at
                    FROM report_releases
                    WHERE snapshot_id = :snapshot_id
                      AND org_id = :org_id AND project_id = :project_id
                    """
                    ),
                    {
                        "snapshot_id": snapshot_id,
                        "org_id": str(scope.org_id),
                        "project_id": str(scope.project_id),
                    },
                )
            )
            .mappings()
            .first()
        )
        if existing:
            if existing["attestation"] != attestation:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Frozen snapshot was already released with another attestation",
                )
            release_id = existing["id"]
            now = existing["created_at"]
        else:
            await session.execute(
                sa.text(
                    """
                    INSERT INTO report_releases (
                        id, snapshot_id, org_id, project_id, released_by,
                        attestation, created_at
                    ) VALUES (
                        :id, :snapshot_id, :org_id, :project_id, :released_by,
                        :attestation, :created_at
                    )
                    """
                ),
                {
                    "id": str(release_id),
                    "snapshot_id": snapshot_id,
                    "org_id": str(scope.org_id),
                    "project_id": str(scope.project_id),
                    "released_by": str(scope.user_id),
                    "attestation": attestation,
                    "created_at": now,
                },
            )
            await session.execute(
                sa.text(
                    "UPDATE report_snapshots SET status = 'released' "
                    "WHERE id = :snapshot_id AND org_id = :org_id AND project_id = :project_id"
                ),
                {
                    "snapshot_id": snapshot_id,
                    "org_id": str(scope.org_id),
                    "project_id": str(scope.project_id),
                },
            )
            await session.execute(
                sa.text(
                    "UPDATE export_artifacts SET status = 'released' "
                    "WHERE snapshot_id = :snapshot_id AND org_id = :org_id "
                    "AND project_id = :project_id"
                ),
                {
                    "snapshot_id": snapshot_id,
                    "org_id": str(scope.org_id),
                    "project_id": str(scope.project_id),
                },
            )
            await session.execute(
                sa.text(
                    """
                    INSERT INTO authoritative_audit_events (
                        id, org_id, project_id, actor_id, action,
                        target_type, target_id, payload_redacted, occurred_at,
                        correlation_id
                    ) VALUES (
                        :id, :org_id, :project_id, :actor_id, 'report.released',
                        'report_release', :target_id, :payload, :occurred_at,
                        :id
                    )
                    """
                ),
                {
                    "id": str(audit_id),
                    "org_id": str(scope.org_id),
                    "project_id": str(scope.project_id),
                    "actor_id": str(scope.user_id),
                    "target_id": str(release_id),
                    "payload": json.dumps(
                        {
                            "snapshotId": snapshot_id,
                            "contentHash": snapshot["content_hash"],
                            "attestation": attestation,
                        },
                        sort_keys=True,
                    ),
                    "occurred_at": now,
                },
            )

    download_url = (
        f"/api/v1/organizations/{scope.org_id}/projects/{scope.project_id}"
        f"/report-releases/{release_id}/artifact-content"
    )
    return {
        "data": {
            "releaseId": str(release_id),
            "snapshotId": snapshot_id,
            "releasedBy": str(scope.user_id),
            "releasedAt": _iso(now),
            "attestation": attestation,
            "contentHash": snapshot["content_hash"],
            "artifactId": str(snapshot["artifact_id"]),
            "downloadUrl": download_url,
        },
        "meta": _request_meta(),
    }


@router.get("/report-history", operation_id="listReportHistory")
async def list_report_history(
    request: Request, org_id: OrgIdParam, project_id: ProjectIdParam
) -> dict[str, object]:
    scope = await _authorize(request, org_id, project_id)
    async with session_scope() as session:
        rows = (
            (
                await session.execute(
                    sa.text(
                        """
                    SELECT snapshot.id AS snapshot_id, snapshot.script_version_id,
                           snapshot.status, snapshot.content_hash, snapshot.created_at,
                           release.id AS release_id, release.released_by,
                           release.attestation, release.created_at AS released_at,
                           artifact.id AS artifact_id, artifact.content_hash AS artifact_hash
                    FROM report_snapshots AS snapshot
                    JOIN export_artifacts AS artifact ON artifact.snapshot_id = snapshot.id
                    LEFT JOIN report_releases AS release ON release.snapshot_id = snapshot.id
                    WHERE snapshot.org_id = :org_id AND snapshot.project_id = :project_id
                    ORDER BY snapshot.created_at DESC, snapshot.id DESC
                    """
                    ),
                    {
                        "org_id": str(scope.org_id),
                        "project_id": str(scope.project_id),
                    },
                )
            )
            .mappings()
            .all()
        )
    history = [
        {
            "snapshotId": str(row["snapshot_id"]),
            "versionId": str(row["script_version_id"]),
            "status": row["status"],
            "contentHash": row["content_hash"],
            "generatedAt": _iso(row["created_at"]),
            "artifactId": str(row["artifact_id"]),
            "artifactHash": row["artifact_hash"],
            "releaseId": str(row["release_id"]) if row["release_id"] else None,
            "releasedBy": str(row["released_by"]) if row["released_by"] else None,
            "attestation": row["attestation"],
            "releasedAt": _iso(row["released_at"]) if row["released_at"] else None,
        }
        for row in rows
    ]
    return {
        "data": history,
        "meta": _request_meta(total_count=len(history)),
    }


async def _released_artifact(
    session: Any,
    *,
    org_id: str,
    project_id: str,
    release_id: str,
) -> Any:
    return (
        (
            await session.execute(
                sa.text(
                    """
                SELECT release.id AS release_id, release.snapshot_id,
                       snapshot.content_hash AS manifest_hash,
                       artifact.id AS artifact_id, artifact.media_type,
                       artifact.content_hash AS artifact_hash,
                       artifact.content, artifact.status
                FROM report_releases AS release
                JOIN report_snapshots AS snapshot
                  ON snapshot.id = release.snapshot_id
                 AND snapshot.org_id = release.org_id
                 AND snapshot.project_id = release.project_id
                JOIN export_artifacts AS artifact
                  ON artifact.snapshot_id = snapshot.id
                 AND artifact.org_id = snapshot.org_id
                 AND artifact.project_id = snapshot.project_id
                WHERE release.id = :release_id
                  AND release.org_id = :org_id AND release.project_id = :project_id
                  AND snapshot.status = 'released' AND artifact.status = 'released'
                """
                ),
                {
                    "release_id": release_id,
                    "org_id": org_id,
                    "project_id": project_id,
                },
            )
        )
        .mappings()
        .first()
    )


@router.get(
    "/report-releases/{releaseId}/artifact-metadata",
    operation_id="getReportDownloadMetadata",
)
async def get_report_download_metadata(
    request: Request,
    org_id: OrgIdParam,
    project_id: ProjectIdParam,
    release_id: ReleaseIdParam,
) -> dict[str, object]:
    scope = await _authorize(request, org_id, project_id)
    async with session_scope() as session:
        artifact = await _released_artifact(
            session,
            org_id=str(scope.org_id),
            project_id=str(scope.project_id),
            release_id=release_id,
        )
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    download_url = (
        f"/api/v1/organizations/{scope.org_id}/projects/{scope.project_id}"
        f"/report-releases/{release_id}/artifact-content"
    )
    return {
        "data": {
            "releaseId": str(artifact["release_id"]),
            "snapshotId": str(artifact["snapshot_id"]),
            "artifactId": str(artifact["artifact_id"]),
            "mediaType": artifact["media_type"],
            "contentHash": artifact["manifest_hash"],
            "artifactHash": artifact["artifact_hash"],
            "sizeBytes": len(artifact["content"].encode("utf-8")),
            "status": artifact["status"],
            "downloadUrl": download_url,
        },
        "meta": _request_meta(),
    }


@router.get(
    "/report-releases/{releaseId}/artifact",
    operation_id="downloadReleasedReport",
)
async def download_released_report(
    request: Request,
    org_id: OrgIdParam,
    project_id: ProjectIdParam,
    release_id: ReleaseIdParam,
) -> dict[str, object]:
    metadata = await get_report_download_metadata(
        request,
        org_id,
        project_id,
        release_id,
    )
    return {
        "downloadUrl": metadata["data"]["downloadUrl"],
    }


@router.get(
    "/report-releases/{releaseId}/artifact-content",
    include_in_schema=False,
)
async def download_released_report_content(
    request: Request,
    org_id: OrgIdParam,
    project_id: ProjectIdParam,
    release_id: ReleaseIdParam,
) -> HTMLResponse:
    scope = await _authorize(request, org_id, project_id)
    async with session_scope() as session:
        artifact = await _released_artifact(
            session,
            org_id=str(scope.org_id),
            project_id=str(scope.project_id),
            release_id=release_id,
        )
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return HTMLResponse(
        content=artifact["content"],
        headers={
            "Content-Disposition": (f'attachment; filename="clearcut-report-{release_id}.html"'),
            "ETag": f'"{artifact["artifact_hash"]}"',
        },
    )


@router.post(
    "/report-releases",
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def legacy_release_report(
    request: Request,
    org_id: OrgIdParam,
    project_id: ProjectIdParam,
    body: ReleaseReportBody,
) -> dict[str, object]:
    canonical = CanonicalReleaseReportBody(attestation=body.attestation)
    return await canonical_release_report(
        request,
        org_id,
        project_id,
        body.snapshot_id,
        canonical,
    )

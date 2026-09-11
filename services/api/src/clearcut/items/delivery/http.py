import hashlib
from datetime import datetime
from typing import Annotated
from uuid import UUID

import sqlalchemy as sa
import uuid6
from clearcut.commanding.errors import (
    CommandForbiddenError,
    CommandNotFoundError,
    CommandValidationError,
    IdempotencyIntentConflictError,
    StaleVersionConflictError,
)
from clearcut.database import session_scope
from clearcut.delivery_errors import error_response
from clearcut.identity.delivery.scope import get_request_scope
from clearcut.items.adapters.sql_command_repository import SqlItemCommandRepository
from clearcut.items.adapters.sql_read_repository import SqlItemReadRepository
from clearcut.items.application.assign_item import AssignItemCommand, AssignItemService
from clearcut.items.application.read_models import (
    ClearanceItemDetailResponse,
    ItemDetailResponseMeta,
)
from clearcut.items.ports.command_repository import PersistedAssignment
from clearcut.organizations.delivery.http import verify_csrf_origin
from fastapi import APIRouter, Header, HTTPException, Path, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

prefix = "/api/v1/organizations/{orgId}/projects/{projectId}/clearance-items"
router = APIRouter(prefix=prefix, tags=["items"])

OrgIdParam = Annotated[str, Path(alias="orgId")]
ProjectIdParam = Annotated[str, Path(alias="projectId")]
ItemIdParam = Annotated[str, Path(alias="itemId")]

_item_repository = SqlItemCommandRepository()
_assign_service = AssignItemService(repository=_item_repository)
_read_repository = SqlItemReadRepository()

LIST_ITEMS_QUERY = sa.text("""
    SELECT i.id, i.project_id, i.version_id, i.version, i.category, i.text, i.status,
           i.disposition_status, i.assigned_to_user_id, i.due_at,
           e.text AS context_text, e.scene_number AS scene_number,
           e.page_number AS page_number,
           dc.uncertainty AS uncertainty,
           (SELECT count(*) FROM evidence_claims c
            WHERE c.item_id = i.id
              AND c.org_id = i.org_id
              AND c.project_id = i.project_id) as claims_count,
           (SELECT count(*) FROM evidence_claims c
            WHERE c.item_id = i.id AND c.org_id = i.org_id
              AND c.project_id = i.project_id AND c.stance = 'disagrees') as disagree_count
    FROM clearance_items i
    LEFT JOIN script_elements e ON e.id = i.element_id
    LEFT JOIN detection_candidates dc ON dc.id = i.detection_candidate_id
    WHERE i.org_id = :org_id AND i.project_id = :project_id
      AND (CAST(:category AS text) IS NULL OR i.category = CAST(:category AS text))
      AND (CAST(:item_status AS text) IS NULL OR i.status = CAST(:item_status AS text))
    ORDER BY e.ordinal ASC, i.created_at ASC
""")

# Categories whose clearance failure most often blocks a production.
_HIGH_RISK_CATEGORIES = {
    "real_persons_living",
    "products_and_trademarks",
    "copyrighted_works",
    "music_and_lyrics",
}

# Detection emits an ordinal uncertainty; invert it to a comparable confidence
# for the worklist. These are derived presentation values, not stored facts.
_CONFIDENCE_BY_UNCERTAINTY = {"low": 90, "medium": 70, "high": 45}


def _derive_display_status(
    status: str,
    disposition: str | None,
    claim_count: int,
    sources_disagree: bool,
) -> str:
    """Map the domain state triple to the worklist's human-readable status.

    The raw `status` is preserved on the item; this is the reviewer-facing label
    the mock worklist shows and filters on. A disposition is a settled human
    decision and always wins over the automated state beneath it.
    """
    disposition_labels = {
        "approved_as_is": "Accepted",
        "rewrite_required": "Rewrite required",
        "refer_to_counsel": "With specialist",
        "declined": "Declined",
    }
    if disposition and disposition not in {"undisposed", ""}:
        return disposition_labels.get(disposition, "Resolved")
    if status in {"cleared", "resolved", "verified"}:
        return "Verified"
    if sources_disagree:
        return "Sources disagree"
    if claim_count > 0:
        return "Needs your call"
    return "Could not verify" if status == "researched" else "Needs research"


def _derive_severity(category: str, uncertainty: str | None) -> str:
    """Worst-first triage hint from category risk and detection uncertainty."""
    high_risk = category in _HIGH_RISK_CATEGORIES
    if uncertainty == "high":
        return "High" if high_risk else "Medium"
    if uncertainty == "medium":
        return "High" if high_risk else "Medium"
    return "Medium" if high_risk else "Low"


class AssignClearanceItemBody(BaseModel):
    """Contract-aligned request body for ``assignClearanceItem``.

    ``assigneeId`` is the target member; ``null`` unassigns the item. Assignment
    is operational, so both assign and unassign are first-class outcomes.
    ``dueAt`` is an optional ISO 8601 due date; ``null`` or absent leaves/clears
    the due date as specified, consistent with how ``assigneeId`` behaves.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    assignee_id: Annotated[str | None, Field(alias="assigneeId")] = None
    due_at: Annotated[datetime | None, Field(alias="dueAt")] = None
    expected_version: Annotated[int, Field(ge=1, alias="expectedVersion")]
    intent_hash: Annotated[str, Field(min_length=1, alias="intentHash")]


class ReferItemBody(BaseModel):
    target_role: str = Field(alias="targetRole")
    notes: str


class AddCommentBody(BaseModel):
    content: str
    parent_comment_id: str | None = Field(default=None, alias="parentCommentId")


class ProposeRewriteBody(BaseModel):
    original_text: str = Field(alias="originalText")
    proposed_text: str = Field(alias="proposedText")
    rationale: str | None = None


@router.get("", operation_id="listClearanceItems")
async def list_items(
    org_id: OrgIdParam,
    project_id: ProjectIdParam,
    request: Request,
    category: Annotated[str | None, Query()] = None,
    item_status: Annotated[str | None, Query(alias="status")] = None,
) -> dict:
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)
    async with session_scope() as session:
        result = await session.execute(
            LIST_ITEMS_QUERY,
            {
                "org_id": str(scope.org_id),
                "project_id": str(scope.project_id),
                "category": category,
                "item_status": item_status,
            },
        )
        rows = result.fetchall()
        items = []
        for r in rows:
            confidence = _CONFIDENCE_BY_UNCERTAINTY.get(r.uncertainty or "", 70)
            item = {
                "itemId": str(r.id),
                "projectId": str(r.project_id),
                "versionId": str(r.version_id),
                "version": int(r.version),
                "category": r.category,
                "entityName": r.text,
                "status": r.status,
                "disposition": r.disposition_status or "undisposed",
                "claimCount": r.claims_count,
                "severity": _derive_severity(r.category, r.uncertainty),
                "confidence": confidence,
                "sourcesDisagree": bool(r.disagree_count),
                "displayStatus": _derive_display_status(
                    r.status,
                    r.disposition_status,
                    r.claims_count,
                    bool(r.disagree_count),
                ),
            }
            if r.scene_number is not None:
                item["scene"] = int(r.scene_number)
            if getattr(r, "page_number", None) is not None:
                item["page"] = int(r.page_number)
            if r.due_at is not None:
                item["dueAt"] = r.due_at.isoformat()
            if r.context_text is not None:
                item["contextText"] = r.context_text
            if r.assigned_to_user_id is not None:
                item["assignedTo"] = str(r.assigned_to_user_id)
            items.append(item)
    return {"data": items, "meta": {"requestId": str(uuid6.uuid7()), "totalCount": len(items)}}


@router.get(
    "/{itemId}",
    operation_id="getClearanceItem",
    response_model=ClearanceItemDetailResponse,
    response_model_exclude_none=True,
)
async def get_item(
    org_id: OrgIdParam, project_id: ProjectIdParam, item_id: ItemIdParam, request: Request
) -> ClearanceItemDetailResponse:
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)
    parsed_item_id = _parse_uuid(item_id)
    if parsed_item_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clearance item not found",
        )

    assert scope.org_id is not None
    assert scope.project_id is not None
    try:
        async with session_scope() as session:
            detail = await _read_repository.load_detail(
                session,
                org_id=scope.org_id,
                project_id=scope.project_id,
                item_id=parsed_item_id,
                actor_id=scope.user_id,
                actor_role=scope.role or "",
            )
    except CommandForbiddenError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error.message,
        ) from error
    except CommandNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error.message,
        ) from error

    return ClearanceItemDetailResponse(
        data=detail,
        meta=ItemDetailResponseMeta(request_id=str(uuid6.uuid7())),
    )


@router.get("/{itemId}/evidence")
async def get_item_evidence(
    org_id: OrgIdParam, project_id: ProjectIdParam, item_id: ItemIdParam, request: Request
) -> dict:
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)
    try:
        parsed_item_id = UUID(item_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found"
        ) from None

    async with session_scope() as session:
        src_res = await session.execute(
            sa.text("""
                SELECT c.id as claim_id, c.stance, c.authority_tier, c.claim_text, c.provenance_excerpt,
                       s.title as source_title, s.url as source_url, s.publisher, s.retrieved_at
                FROM evidence_claims c
                JOIN source_snapshots s ON s.id = c.snapshot_id
                WHERE c.item_id = :item_id AND c.org_id = :org_id AND c.project_id = :project_id
                ORDER BY c.created_at ASC
            """),
            {
                "item_id": str(parsed_item_id),
                "org_id": str(scope.org_id),
                "project_id": str(scope.project_id),
            },
        )
        claims = [
            {
                "claimId": str(s.claim_id),
                "sourceTitle": s.source_title,
                "sourceUrl": s.source_url,
                "publisher": s.publisher,
                "stance": s.stance,
                "authorityTier": s.authority_tier,
                "claimText": s.claim_text,
                "provenanceExcerpt": s.provenance_excerpt,
                "retrievedAt": s.retrieved_at.isoformat()
                if hasattr(s.retrieved_at, "isoformat")
                else str(s.retrieved_at),
            }
            for s in src_res.fetchall()
        ]
        return {"data": claims, "meta": {"count": len(claims)}}


class BulkAssignClearanceItemsBody(BaseModel):
    """Assign a set of clearance items to one member in a single request.

    ``itemIds`` are the selected items; ``assigneeId`` is the target member, or
    null to unassign them all. ``dueAt`` is an optional shared due date. Unlike
    the single-item command, per-item expected_version and intent_hash are NOT
    supplied by the client: the server loads each item's current version and
    derives a deterministic per-item intent from the batch idempotency key, so a
    selection can be assigned without the client tracking each item's version.
    Each item is still assigned through the same governed command, so each keeps
    its own accountable receipt and audit event.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    item_ids: Annotated[list[str], Field(alias="itemIds", min_length=1, max_length=200)]
    assignee_id: Annotated[str | None, Field(alias="assigneeId")] = None
    due_at: Annotated[datetime | None, Field(alias="dueAt")] = None


@router.post(":bulkAssign", operation_id="bulkAssignClearanceItems")
async def bulk_assign_items(
    org_id: OrgIdParam,
    project_id: ProjectIdParam,
    body: BulkAssignClearanceItemsBody,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=16, max_length=128)],
) -> JSONResponse:
    verify_csrf_origin(request)
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)
    assert scope.org_id is not None
    assert scope.project_id is not None

    parsed_assignee_id: UUID | None = None
    if body.assignee_id is not None:
        parsed_assignee_id = _parse_uuid(body.assignee_id)
        if parsed_assignee_id is None:
            return _assign_error(CommandNotFoundError())

    # Reject duplicate ids up front so the batch cannot assign the same item
    # twice under two derived keys.
    seen: set[str] = set()
    parsed_item_ids: list[UUID] = []
    for raw in body.item_ids:
        if raw in seen:
            continue
        seen.add(raw)
        parsed = _parse_uuid(raw)
        if parsed is None:
            return _assign_error(CommandNotFoundError())
        parsed_item_ids.append(parsed)

    results: list[dict[str, object]] = []
    # Each item is assigned in its own governed unit of work so one item's
    # stale-version conflict or absence does not roll back the rest; the batch
    # reports a per-item outcome. A per-item idempotency key derived from the
    # batch key keeps a retried batch idempotent.
    for parsed_item_id in parsed_item_ids:
        item_key = f"{idempotency_key}:{parsed_item_id}"
        intent_hash = hashlib.sha256(
            f"bulk-assign:{parsed_item_id}:{parsed_assignee_id}:{body.due_at}".encode()
        ).hexdigest()
        try:
            async with session_scope() as session:
                item = await _item_repository.load_scoped_item(
                    session,
                    org_id=scope.org_id,
                    project_id=scope.project_id,
                    item_id=parsed_item_id,
                )
                if item is None:
                    raise CommandNotFoundError()
                command = AssignItemCommand(
                    org_id=scope.org_id,
                    project_id=scope.project_id,
                    item_id=parsed_item_id,
                    actor_id=scope.user_id,
                    actor_role=scope.role or "",
                    assignee_id=parsed_assignee_id,
                    due_at=body.due_at,
                    expected_version=item.version,
                    intent_hash=intent_hash,
                    idempotency_key=item_key,
                )
                result = await _assign_service.assign(session, command)
            results.append(
                {
                    "itemId": str(parsed_item_id),
                    "outcome": "assigned",
                    "resultingVersion": result.resulting_version,
                }
            )
        except (
            CommandForbiddenError,
            CommandNotFoundError,
            StaleVersionConflictError,
            IdempotencyIntentConflictError,
            CommandValidationError,
        ) as error:
            # A forbidden actor fails the whole batch; per-item conflicts and
            # not-found are reported per item without aborting the rest.
            if isinstance(error, CommandForbiddenError):
                return _assign_error(error)
            results.append(
                {
                    "itemId": str(parsed_item_id),
                    "outcome": type(error).__name__,
                }
            )

    assigned = sum(1 for r in results if r["outcome"] == "assigned")
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "data": {"results": results, "assignedCount": assigned, "totalCount": len(results)},
            "meta": {"requestId": str(uuid6.uuid7())},
        },
    )


@router.post("/{itemId}:assign", operation_id="assignClearanceItem")
async def assign_item(
    org_id: OrgIdParam,
    project_id: ProjectIdParam,
    item_id: ItemIdParam,
    body: AssignClearanceItemBody,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=16, max_length=128)],
) -> JSONResponse:
    verify_csrf_origin(request)
    scope = await get_request_scope(request, org_id=org_id, project_id=project_id)

    parsed_item_id = _parse_uuid(item_id)
    if parsed_item_id is None:
        # An unparseable item id is a resource that cannot exist in scope: neutral
        # not-found parity, never a distinguishing validation error.
        return _assign_error(CommandNotFoundError())

    parsed_assignee_id: UUID | None = None
    if body.assignee_id is not None:
        parsed_assignee_id = _parse_uuid(body.assignee_id)
        if parsed_assignee_id is None:
            # An unparseable assignee id cannot be an active member in scope.
            return _assign_error(CommandNotFoundError())

    assert scope.org_id is not None  # get_request_scope enforced org membership
    assert scope.project_id is not None  # get_request_scope enforced project scope

    command = AssignItemCommand(
        org_id=scope.org_id,
        project_id=scope.project_id,
        item_id=parsed_item_id,
        actor_id=scope.user_id,
        actor_role=scope.role or "",
        assignee_id=parsed_assignee_id,
        due_at=body.due_at,
        expected_version=body.expected_version,
        intent_hash=body.intent_hash,
        idempotency_key=idempotency_key,
    )

    try:
        async with session_scope() as session:
            result = await _assign_service.assign(session, command)
    except (
        CommandForbiddenError,
        CommandNotFoundError,
        StaleVersionConflictError,
        IdempotencyIntentConflictError,
        CommandValidationError,
    ) as error:
        return _assign_error(error)

    return _assign_success(result)


def _parse_uuid(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


def _assign_error(error: Exception) -> JSONResponse:
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
    message = getattr(error, "message", "The assignment inputs were invalid.")
    return error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code="validation_failed",
        message=message,
    )


def _assign_success(result: PersistedAssignment) -> JSONResponse:
    data: dict[str, object] = {
        "itemId": str(result.item_id),
        "projectId": str(result.project_id),
        "version": result.resulting_version,
        "category": result.category,
        "entityName": result.entity_name,
        "status": result.status,
        "claimCount": result.cited_claim_count,
    }
    if result.version_id is not None:
        data["versionId"] = str(result.version_id)
    if result.context_text is not None:
        data["contextText"] = result.context_text
    # Only surface a disposition that is part of the canonical vocabulary; the
    # storage default ("undisposed") is not a contract disposition value.
    if result.disposition_status is not None and result.disposition_status != "undisposed":
        data["disposition"] = result.disposition_status
    if result.assigned_to_user_id is not None:
        data["assignedTo"] = str(result.assigned_to_user_id)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"data": data, "meta": {"requestId": str(uuid6.uuid7())}},
    )

"""Typed authoritative read models for the clearance-item detail projection."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReadModel(BaseModel):
    """Base model that accepts Python names and emits canonical camel-case aliases."""

    model_config = ConfigDict(populate_by_name=True, frozen=True)


class EvidenceState(ReadModel):
    status: str
    unresolved: bool = True
    claim_count: int = Field(serialization_alias="claimCount", ge=0)
    reason: str


class EvidenceClaimRead(ReadModel):
    claim_id: str = Field(serialization_alias="claimId")
    snapshot_id: str = Field(serialization_alias="snapshotId")
    claim_text: str = Field(serialization_alias="claimText")
    stance: str
    authority_tier: str = Field(serialization_alias="authorityTier")
    provenance_excerpt: str = Field(serialization_alias="provenanceExcerpt")
    created_at: datetime = Field(serialization_alias="createdAt")


class SourceSnapshotRead(ReadModel):
    snapshot_id: str = Field(serialization_alias="snapshotId")
    url: str
    title: str
    publisher: str
    excerpt: str
    origin: str
    retrieved_at: datetime = Field(serialization_alias="retrievedAt")


class EvidenceConflictRead(ReadModel):
    conflict_id: str = Field(serialization_alias="conflictId")
    description: str
    created_at: datetime = Field(serialization_alias="createdAt")


class DecisionRecordRead(ReadModel):
    record_id: str = Field(serialization_alias="recordId")
    kind: str
    value: str
    rationale: str
    actor_id: str = Field(serialization_alias="actorId")
    expected_version: int = Field(serialization_alias="expectedVersion")
    resulting_version: int = Field(serialization_alias="resultingVersion")
    created_at: datetime = Field(serialization_alias="createdAt")


class ReferralRead(ReadModel):
    referral_id: str = Field(serialization_alias="referralId")
    target_role: str = Field(serialization_alias="targetRole")
    question: str
    notes: str | None = None
    status: str
    submitted_by_actor_id: str = Field(serialization_alias="submittedByActorId")
    acknowledged_by_actor_id: str | None = Field(
        default=None,
        serialization_alias="acknowledgedByActorId",
    )
    submitted_at: datetime = Field(serialization_alias="submittedAt")
    acknowledged_at: datetime | None = Field(default=None, serialization_alias="acknowledgedAt")


class CommentRevisionRead(ReadModel):
    revision_id: str = Field(serialization_alias="revisionId")
    ordinal: int = Field(ge=1)
    author_id: str = Field(serialization_alias="authorId")
    body: str
    created_at: datetime = Field(serialization_alias="createdAt")
    mention_recipient_ids: list[str] = Field(serialization_alias="mentionRecipientIds")


class CommentRead(ReadModel):
    comment_id: str = Field(serialization_alias="commentId")
    author_id: str = Field(serialization_alias="authorId")
    parent_id: str | None = Field(default=None, serialization_alias="parentId")
    reply_depth: int = Field(serialization_alias="replyDepth", ge=0, le=1)
    created_at: datetime = Field(serialization_alias="createdAt")
    revisions: list[CommentRevisionRead]


class CapabilityRead(ReadModel):
    action: str
    allowed: bool
    explanation: str


class ClearanceItemDetail(ReadModel):
    item_id: str = Field(serialization_alias="itemId")
    project_id: str = Field(serialization_alias="projectId")
    version_id: str = Field(serialization_alias="versionId")
    version: int = Field(ge=1)
    category: str
    entity_name: str = Field(serialization_alias="entityName")
    context_text: str | None = Field(default=None, serialization_alias="contextText")
    scene: int | None = None
    page: int | None = None
    status: str
    workflow_status: str = Field(serialization_alias="workflowStatus")
    research_status: str = Field(serialization_alias="researchStatus")
    disposition: str | None = None
    assigned_to: str | None = Field(default=None, serialization_alias="assignedTo")
    evidence_state: EvidenceState = Field(serialization_alias="evidenceState")
    claims: list[EvidenceClaimRead]
    snapshots: list[SourceSnapshotRead]
    conflicts: list[EvidenceConflictRead]
    decisions: list[DecisionRecordRead]
    referrals: list[ReferralRead]
    comments: list[CommentRead]
    capabilities: list[CapabilityRead]


class ItemDetailResponseMeta(ReadModel):
    request_id: str = Field(serialization_alias="requestId")


class ClearanceItemDetailResponse(ReadModel):
    data: ClearanceItemDetail
    meta: ItemDetailResponseMeta


__all__ = [
    "CapabilityRead",
    "ClearanceItemDetail",
    "ClearanceItemDetailResponse",
    "CommentRead",
    "CommentRevisionRead",
    "DecisionRecordRead",
    "EvidenceClaimRead",
    "EvidenceConflictRead",
    "EvidenceState",
    "ItemDetailResponseMeta",
    "ReferralRead",
    "SourceSnapshotRead",
]

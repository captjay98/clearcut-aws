from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from clearcut.detection.domain.candidates import ClearanceCategory


class ResearchStatus(StrEnum):
    NOT_STARTED = "not_started"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AssessmentStatus(StrEnum):
    UNASSESSED = "unassessed"
    ASSESSED = "assessed"


class WorkflowStatus(StrEnum):
    OPEN = "open"
    ASSIGNED = "assigned"
    IN_REVIEW = "in_review"
    RESOLVED = "resolved"


class RemediationStatus(StrEnum):
    NONE = "none"
    SCRIPT_REWRITE_PROPOSED = "script_rewrite_proposed"
    SCRIPT_REWRITE_ACCEPTED = "script_rewrite_accepted"
    LICENSE_OBTAINED = "license_obtained"


class DispositionStatus(StrEnum):
    UNDISPOSED = "undisposed"
    APPROVED_AS_IS = "approved_as_is"
    APPROVED_WITH_MODIFICATION = "approved_with_modification"
    BLOCKED = "blocked"


class ClearanceItemDisplayStatus(StrEnum):
    AWAITING_RESEARCH = "awaiting_research"
    NEEDS_REVIEW = "needs_review"
    IN_DISCUSSION = "in_discussion"
    REWRITE_PENDING = "rewrite_pending"
    CLEARED = "cleared"
    BLOCKED = "blocked"


def derive_display_status(
    research: ResearchStatus,
    workflow: WorkflowStatus,
    disposition: DispositionStatus,
    remediation: RemediationStatus,
) -> ClearanceItemDisplayStatus:
    if disposition == DispositionStatus.BLOCKED:
        return ClearanceItemDisplayStatus.BLOCKED
    if disposition in {
        DispositionStatus.APPROVED_AS_IS,
        DispositionStatus.APPROVED_WITH_MODIFICATION,
    }:
        return ClearanceItemDisplayStatus.CLEARED
    if remediation in {
        RemediationStatus.SCRIPT_REWRITE_PROPOSED,
        RemediationStatus.SCRIPT_REWRITE_ACCEPTED,
    }:
        return ClearanceItemDisplayStatus.REWRITE_PENDING
    if workflow == WorkflowStatus.IN_REVIEW:
        return ClearanceItemDisplayStatus.IN_DISCUSSION
    if research in {ResearchStatus.COMPLETED, ResearchStatus.FAILED}:
        return ClearanceItemDisplayStatus.NEEDS_REVIEW
    return ClearanceItemDisplayStatus.AWAITING_RESEARCH


@dataclass(frozen=True)
class ItemProjection:
    item_id: UUID
    org_id: UUID
    project_id: UUID
    script_id: UUID
    version_id: UUID
    element_id: UUID
    category: ClearanceCategory
    text: str
    scene_number: int | None
    research_status: ResearchStatus
    workflow_status: WorkflowStatus
    disposition_status: DispositionStatus
    display_status: ClearanceItemDisplayStatus
    assigned_to_user_id: UUID | None
    flags_count: int
    claims_count: int
    conflicts_count: int


@dataclass(frozen=True)
class ProjectClearanceSummary:
    total_items: int
    needs_review_count: int
    cleared_count: int
    blocked_count: int
    rewrite_pending_count: int
    awaiting_research_count: int

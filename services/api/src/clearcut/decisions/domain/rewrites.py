from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

import uuid6


class RewriteProposalStatus(StrEnum):
    DRAFT = "draft"
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    MATERIALIZED = "materialized"
    SUPERSEDED = "superseded"


@dataclass(frozen=True)
class RewriteProposal:
    proposal_id: UUID
    org_id: UUID
    project_id: UUID
    item_id: UUID
    source_version_id: UUID
    proposer_id: UUID
    element_id: UUID
    original_text: str
    proposed_text: str
    rationale: str
    status: RewriteProposalStatus
    approver_id: UUID | None = None
    rejection_reason: str | None = None
    created_at: datetime = datetime.now(UTC)
    updated_at: datetime = datetime.now(UTC)

    @classmethod
    def create(
        cls,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        source_version_id: UUID,
        proposer_id: UUID,
        element_id: UUID,
        original_text: str,
        proposed_text: str,
        rationale: str,
    ) -> "RewriteProposal":
        now = datetime.now(UTC)
        return cls(
            proposal_id=uuid6.uuid7(),
            org_id=org_id,
            project_id=project_id,
            item_id=item_id,
            source_version_id=source_version_id,
            proposer_id=proposer_id,
            element_id=element_id,
            original_text=original_text.strip(),
            proposed_text=proposed_text.strip(),
            rationale=rationale.strip(),
            status=RewriteProposalStatus.PROPOSED,
            created_at=now,
            updated_at=now,
        )

    def approve(self, approver_id: UUID) -> "RewriteProposal":
        return RewriteProposal(
            proposal_id=self.proposal_id,
            org_id=self.org_id,
            project_id=self.project_id,
            item_id=self.item_id,
            source_version_id=self.source_version_id,
            proposer_id=self.proposer_id,
            element_id=self.element_id,
            original_text=self.original_text,
            proposed_text=self.proposed_text,
            rationale=self.rationale,
            status=RewriteProposalStatus.APPROVED,
            approver_id=approver_id,
            rejection_reason=None,
            created_at=self.created_at,
            updated_at=datetime.now(UTC),
        )

    def reject(self, rejecter_id: UUID, reason: str) -> "RewriteProposal":
        return RewriteProposal(
            proposal_id=self.proposal_id,
            org_id=self.org_id,
            project_id=self.project_id,
            item_id=self.item_id,
            source_version_id=self.source_version_id,
            proposer_id=self.proposer_id,
            element_id=self.element_id,
            original_text=self.original_text,
            proposed_text=self.proposed_text,
            rationale=self.rationale,
            status=RewriteProposalStatus.REJECTED,
            approver_id=rejecter_id,
            rejection_reason=reason.strip(),
            created_at=self.created_at,
            updated_at=datetime.now(UTC),
        )

    def withdraw(self) -> "RewriteProposal":
        return RewriteProposal(
            proposal_id=self.proposal_id,
            org_id=self.org_id,
            project_id=self.project_id,
            item_id=self.item_id,
            source_version_id=self.source_version_id,
            proposer_id=self.proposer_id,
            element_id=self.element_id,
            original_text=self.original_text,
            proposed_text=self.proposed_text,
            rationale=self.rationale,
            status=RewriteProposalStatus.WITHDRAWN,
            approver_id=None,
            rejection_reason=None,
            created_at=self.created_at,
            updated_at=datetime.now(UTC),
        )

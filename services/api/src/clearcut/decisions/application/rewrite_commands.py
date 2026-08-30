from uuid import UUID

from clearcut.decisions.domain.models import AuditEvent
from clearcut.decisions.domain.rewrites import (
    RewriteProposal,
)
from clearcut.organizations.domain.capabilities import Role, has_capability


class RewriteCommandService:
    def __init__(self) -> None:
        self.proposals: dict[UUID, RewriteProposal] = {}
        self.audits: list[AuditEvent] = []

    async def propose_rewrite(
        self,
        org_id: UUID,
        project_id: UUID,
        item_id: UUID,
        source_version_id: UUID,
        proposer_id: UUID,
        proposer_role: Role,
        element_id: UUID,
        original_text: str,
        proposed_text: str,
        rationale: str,
    ) -> tuple[RewriteProposal, AuditEvent]:
        if not has_capability(proposer_role, "rewrite:propose"):
            raise PermissionError(
                f"Insufficient capability for role '{proposer_role.value}' to propose rewrites."
            )

        proposal = RewriteProposal.create(
            org_id=org_id,
            project_id=project_id,
            item_id=item_id,
            source_version_id=source_version_id,
            proposer_id=proposer_id,
            element_id=element_id,
            original_text=original_text,
            proposed_text=proposed_text,
            rationale=rationale,
        )
        self.proposals[proposal.proposal_id] = proposal

        audit = AuditEvent.create(
            org_id=org_id,
            project_id=project_id,
            action="rewrite_proposed",
            actor_id=proposer_id,
            target_id=proposal.proposal_id,
            target_type="rewrite_proposal",
            details={
                "item_id": str(item_id),
                "proposed_text": proposed_text,
                "rationale": rationale,
            },
        )
        self.audits.append(audit)

        return proposal, audit

    async def approve_rewrite(
        self,
        org_id: UUID,
        project_id: UUID,
        proposal_id: UUID,
        approver_id: UUID,
        approver_role: Role,
        rationale: str,
    ) -> tuple[RewriteProposal, AuditEvent]:
        proposal = self.proposals.get(proposal_id)
        if not proposal:
            raise ValueError("Rewrite proposal not found")

        # Maker-checker validation: Proposer cannot approve own proposal
        if proposal.proposer_id == approver_id:
            raise PermissionError(
                "Maker-checker violation: proposer cannot approve own rewrite"
            )

        if not has_capability(approver_role, "rewrite:approve"):
            raise PermissionError(
                f"Insufficient capability for role '{approver_role.value}' to approve rewrites."
            )

        approved = proposal.approve(approver_id)
        self.proposals[proposal_id] = approved

        audit = AuditEvent.create(
            org_id=org_id,
            project_id=project_id,
            action="rewrite_approved",
            actor_id=approver_id,
            target_id=proposal_id,
            target_type="rewrite_proposal",
            details={
                "proposal_id": str(proposal_id),
                "rationale": rationale,
            },
        )
        self.audits.append(audit)

        return approved, audit

import pytest
import uuid6
from clearcut.decisions.application.rewrite_commands import RewriteCommandService
from clearcut.decisions.domain.rewrites import RewriteProposalStatus
from clearcut.organizations.domain.capabilities import Role


@pytest.mark.asyncio
async def test_propose_and_approve_rewrite_lifecycle():
    service = RewriteCommandService()
    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    item_id = uuid6.uuid7()
    version_id = uuid6.uuid7()
    element_id = uuid6.uuid7()
    proposer_id = uuid6.uuid7()
    approver_id = uuid6.uuid7()

    # 1. Propose rewrite (e.g. by Editor)
    proposal, audit_prop = await service.propose_rewrite(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        source_version_id=version_id,
        proposer_id=proposer_id,
        proposer_role=Role.EDITOR,
        element_id=element_id,
        original_text="Coca-Cola",
        proposed_text="Sparkling Soda",
        rationale="Replace trademark with generic Greeked brand",
    )
    assert proposal.status == RewriteProposalStatus.PROPOSED
    assert audit_prop.action == "rewrite_proposed"

    # 2. Approve rewrite by different actor (e.g. Reviewer)
    approved, audit_app = await service.approve_rewrite(
        org_id=org_id,
        project_id=project_id,
        proposal_id=proposal.proposal_id,
        approver_id=approver_id,
        approver_role=Role.REVIEWER,
        rationale="Approved Greeking change for clearance",
    )
    assert approved.status == RewriteProposalStatus.APPROVED
    assert approved.approver_id == approver_id
    assert audit_app.action == "rewrite_approved"

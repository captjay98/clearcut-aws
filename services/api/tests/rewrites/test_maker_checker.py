import pytest
import uuid6
from clearcut.decisions.application.rewrite_commands import RewriteCommandService
from clearcut.organizations.domain.capabilities import Role


@pytest.mark.asyncio
async def test_proposer_cannot_approve_own_rewrite_maker_checker():
    service = RewriteCommandService()
    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    item_id = uuid6.uuid7()
    version_id = uuid6.uuid7()
    element_id = uuid6.uuid7()
    user_id = uuid6.uuid7()

    # User proposes rewrite as Admin
    proposal, _ = await service.propose_rewrite(
        org_id=org_id,
        project_id=project_id,
        item_id=item_id,
        source_version_id=version_id,
        proposer_id=user_id,
        proposer_role=Role.ADMIN,
        element_id=element_id,
        original_text="Ferrari",
        proposed_text="Sports Car",
        rationale="Generic sports car",
    )

    # Same user attempts to approve their own proposal -> Must fail maker-checker rule
    with pytest.raises(
        PermissionError,
        match="Maker-checker violation: proposer cannot approve own rewrite",
    ):
        await service.approve_rewrite(
            org_id=org_id,
            project_id=project_id,
            proposal_id=proposal.proposal_id,
            approver_id=user_id,
            approver_role=Role.ADMIN,
            rationale="Trying to self-approve",
        )

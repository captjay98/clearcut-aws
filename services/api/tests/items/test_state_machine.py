from clearcut.detection.domain.item_state import (
    ClearanceItemDisplayStatus,
    DispositionStatus,
    RemediationStatus,
    ResearchStatus,
    WorkflowStatus,
    derive_display_status,
)


def test_derive_display_status_rules():
    # If blocked, always BLOCKED
    assert derive_display_status(
        research=ResearchStatus.COMPLETED,
        workflow=WorkflowStatus.OPEN,
        disposition=DispositionStatus.BLOCKED,
        remediation=RemediationStatus.NONE
    ) == ClearanceItemDisplayStatus.BLOCKED

    # If approved as is, CLEARED
    assert derive_display_status(
        research=ResearchStatus.COMPLETED,
        workflow=WorkflowStatus.RESOLVED,
        disposition=DispositionStatus.APPROVED_AS_IS,
        remediation=RemediationStatus.NONE
    ) == ClearanceItemDisplayStatus.CLEARED

    # If rewrite proposed, REWRITE_PENDING
    assert derive_display_status(
        research=ResearchStatus.COMPLETED,
        workflow=WorkflowStatus.OPEN,
        disposition=DispositionStatus.UNDISPOSED,
        remediation=RemediationStatus.SCRIPT_REWRITE_PROPOSED
    ) == ClearanceItemDisplayStatus.REWRITE_PENDING

    # If research not started, AWAITING_RESEARCH
    assert derive_display_status(
        research=ResearchStatus.NOT_STARTED,
        workflow=WorkflowStatus.OPEN,
        disposition=DispositionStatus.UNDISPOSED,
        remediation=RemediationStatus.NONE
    ) == ClearanceItemDisplayStatus.AWAITING_RESEARCH

import pytest
import uuid6
from clearcut.organizations.domain.invitations import Invitation, InvitationStatus


def test_invitation_lifecycle():
    org_id = uuid6.uuid7()
    inviter = uuid6.uuid7()

    invitation = Invitation.create(
        org_id=org_id,
        invited_by_user_id=inviter,
        email="colleague@production.com",
        role="reviewer",
        token_hash="sample_token_hash"
    )

    assert invitation.status == InvitationStatus.PENDING
    assert invitation.is_active()

    # Accept by matching email
    invitation.accept("colleague@production.com")
    assert invitation.status == InvitationStatus.ACCEPTED
    assert not invitation.is_active()
    assert invitation.accepted_at is not None

def test_invitation_rejects_wrong_email():
    invitation = Invitation.create(
        org_id=uuid6.uuid7(),
        invited_by_user_id=uuid6.uuid7(),
        email="target@production.com",
        role="editor",
        token_hash="hash"
    )

    with pytest.raises(ValueError, match="Invitation email does not match"):
        invitation.accept("wrong_actor@evil.com")

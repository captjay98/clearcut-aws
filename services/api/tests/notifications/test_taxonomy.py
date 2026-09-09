from clearcut.collaboration.domain.notifications import NotificationTier


def test_notification_tiers_and_model():
    # The middle tier is "action": the inbox groups it under "Needs your action",
    # which states what the reader must do rather than how loud the row is.
    assert NotificationTier.URGENT == "urgent"
    assert NotificationTier.ACTION == "action"
    assert NotificationTier.INFORMATIONAL == "informational"
    assert [tier.value for tier in NotificationTier] == ["urgent", "action", "informational"]

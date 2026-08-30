from clearcut.collaboration.domain.notifications import NotificationTier


def test_notification_tiers_and_model():
    assert NotificationTier.URGENT == "urgent"
    assert NotificationTier.STANDARD == "standard"
    assert NotificationTier.INFORMATIONAL == "informational"

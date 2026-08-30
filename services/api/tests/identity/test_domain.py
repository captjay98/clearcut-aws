from datetime import UTC, datetime, timedelta

import uuid6
from clearcut.identity.domain.models import Session, normalize_email


def test_normalize_email():
    assert normalize_email("  User.NAME@Example.COM  ") == "user.name@example.com"

def test_session_lifecycle():
    user_id = uuid6.uuid7()
    session = Session.create(user_id=user_id, token_hash="dummy_hash", ttl_hours=24)

    assert session.is_active()
    assert session.user_id == user_id
    assert session.revoked_at is None

    session.revoke()
    assert not session.is_active()
    assert session.revoked_at is not None

def test_session_expiration():
    user_id = uuid6.uuid7()
    past_time = datetime.now(UTC) - timedelta(hours=1)
    session = Session(
        session_id=uuid6.uuid7(),
        user_id=user_id,
        token_hash="hash",
        created_at=past_time - timedelta(hours=24),
        expires_at=past_time,
        revoked_at=None,
    )
    assert not session.is_active()

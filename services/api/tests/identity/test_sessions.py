import pytest
from clearcut.identity.adapters.in_memory import InMemoryIdentityRepository
from clearcut.identity.adapters.local_identity import Argon2idIdentityProvider
from clearcut.identity.application.session_service import SessionService


@pytest.mark.asyncio
async def test_session_creation_and_retrieval():
    repo = InMemoryIdentityRepository()
    id_provider = Argon2idIdentityProvider()
    service = SessionService(repository=repo, identity_provider=id_provider)

    # Register user
    user = await repo.create_user_with_password(
        email="test@clearcut.app",
        password_hash=id_provider.hash_password("Password123!")
    )

    # Create session
    session, token = await service.create_session(
        email="test@clearcut.app",
        password="Password123!",
        ip_address="127.0.0.1",
        user_agent="pytest"
    )
    assert token is not None
    assert len(token) >= 32

    # Verify context
    context = await service.get_session_context(token)
    assert context is not None
    assert context.authenticated
    assert context.user_id == user.user_id
    assert context.email == "test@clearcut.app"

    # Revoke session
    revoked = await service.revoke_current_session(token)
    assert revoked is True

    # Context after revoke
    context_after = await service.get_session_context(token)
    assert context_after is None or not context_after.authenticated

@pytest.mark.asyncio
async def test_invalid_login_returns_none():
    repo = InMemoryIdentityRepository()
    id_provider = Argon2idIdentityProvider()
    service = SessionService(repository=repo, identity_provider=id_provider)

    with pytest.raises(ValueError, match="Invalid credentials"):
        await service.create_session(
            email="nonexistent@clearcut.app",
            password="WrongPassword!",
            ip_address="127.0.0.1",
            user_agent="pytest"
        )

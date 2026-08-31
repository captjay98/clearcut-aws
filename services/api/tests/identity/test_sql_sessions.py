import pytest
from clearcut.database import session_scope
from clearcut.init_db import init_and_seed_db
from clearcut.identity.adapters.local_identity import Argon2idIdentityProvider
from clearcut.identity.adapters.sql_repository import DatabaseIdentityRepository, SqlIdentityRepository
from clearcut.identity.application.session_service import SessionService


@pytest.mark.asyncio
async def test_sql_session_persistence_and_restart_safety():
    await init_and_seed_db()
    id_provider = Argon2idIdentityProvider()
    db_repo = DatabaseIdentityRepository()
    service1 = SessionService(repository=db_repo, identity_provider=id_provider)

    email = "restart_safe@clearcut.app"
    password = "SafePassword123!"

    user = await db_repo.create_user_with_password(
        email=email,
        password_hash=id_provider.hash_password(password),
    )

    session, token = await service1.create_session(
        email=email,
        password=password,
        ip_address="127.0.0.1",
        user_agent="pytest-client-1",
    )
    assert token is not None

    # Simulate server restart with entirely new repo and service instances
    new_db_repo = DatabaseIdentityRepository()
    service2 = SessionService(repository=new_db_repo, identity_provider=id_provider)

    context = await service2.get_session_context(token)
    assert context is not None
    assert context.authenticated is True
    assert context.user_id == user.user_id
    assert context.email == email

    # Revoke in service2
    revoked = await service2.revoke_current_session(token)
    assert revoked is True

    # Check in another new instance service3
    service3 = SessionService(repository=DatabaseIdentityRepository(), identity_provider=id_provider)
    context_revoked = await service3.get_session_context(token)
    assert context_revoked.authenticated is False

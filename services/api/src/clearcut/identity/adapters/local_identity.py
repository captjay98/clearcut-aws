import argon2
from clearcut.identity.ports.identity_provider import IdentityProviderPort


class Argon2idIdentityProvider(IdentityProviderPort):
    def __init__(self) -> None:
        # RFC 9106 recommended parameters for interactive logins
        self._hasher = argon2.PasswordHasher(
            time_cost=3,
            memory_cost=65536,
            parallelism=4,
            hash_len=32,
            type=argon2.Type.ID,
        )

    def hash_password(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify_password(self, password_hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except Exception:
            return False

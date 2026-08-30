from clearcut.identity.adapters.local_identity import Argon2idIdentityProvider


def test_argon2id_hash_and_verify():
    provider = Argon2idIdentityProvider()
    password = "SuperSecretPassword123!"

    pw_hash = provider.hash_password(password)
    assert pw_hash.startswith("$argon2id$")
    assert provider.verify_password(pw_hash, password)
    assert not provider.verify_password(pw_hash, "WrongPassword!")

def test_generic_credential_rejection():
    provider = Argon2idIdentityProvider()
    # Dummy verification timing proof
    assert not provider.verify_password("$argon2id$v=19$m=65536,t=3,p=4$dummy$dummy", "password")

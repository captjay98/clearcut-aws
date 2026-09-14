"""AWS Secrets Manager resolver conformance: plain text, JSON key extraction, TTL cache, and fail-closed error handling."""

from __future__ import annotations

import json
import time
from typing import Any

import pytest
from botocore.exceptions import ClientError
from clearcut.bootstrap.aws_secrets import AwsSecretsManagerResolver
from clearcut.bootstrap.secrets import (
    SecretResolutionError,
    SecretResolver,
    build_secret_resolver,
)
from clearcut.bootstrap.settings import SecretBackend, SecretsSettings
from pydantic import SecretStr


class FakeAwsSecretsClient:
    """Injected fake boto3 Secrets Manager client."""

    def __init__(self, secrets: dict[str, str | bytes] | None = None) -> None:
        self.secrets: dict[str, str | bytes] = secrets or {}
        self.calls: list[str] = []
        self.failure: Exception | None = None

    def get_secret_value(self, *, SecretId: str) -> dict[str, Any]:  # noqa: N803
        self.calls.append(SecretId)
        if self.failure:
            raise self.failure
        if SecretId not in self.secrets:
            error_response = {
                "Error": {
                    "Code": "ResourceNotFoundException",
                    "Message": f"Secret {SecretId} not found.",
                }
            }
            raise ClientError(error_response, "GetSecretValue")

        val = self.secrets[SecretId]
        if isinstance(val, bytes):
            return {"SecretBinary": val}
        return {"SecretString": val}


def test_aws_secrets_plain_text_resolution() -> None:
    """Resolving a plain-text secret returns masked SecretStr."""
    client = FakeAwsSecretsClient({"my-secret-id": "sk-parallel-secret-12345"})
    resolver = AwsSecretsManagerResolver(client=client, region="us-east-1")

    assert isinstance(resolver, SecretResolver)
    secret = resolver.resolve("my-secret-id")
    assert isinstance(secret, SecretStr)
    assert secret.get_secret_value() == "sk-parallel-secret-12345"
    assert "sk-parallel-secret-12345" not in repr(secret)
    assert "sk-parallel-secret-12345" not in str(secret)


def test_aws_secrets_json_key_extraction() -> None:
    """JSON key extraction works via #fragment syntax and json_key parameter."""
    payload = json.dumps({"api_key": "sk-parallel-val", "other": "unused"})
    client = FakeAwsSecretsClient({"clearcut/keys": payload})
    resolver = AwsSecretsManagerResolver(client=client, region="us-east-1")

    # Via #fragment syntax
    secret1 = resolver.resolve("clearcut/keys#api_key")
    assert secret1.get_secret_value() == "sk-parallel-val"

    # Via json_key kwarg
    secret2 = resolver.resolve("clearcut/keys", json_key="api_key")
    assert secret2.get_secret_value() == "sk-parallel-val"


def test_aws_secrets_missing_json_key_raises() -> None:
    """Missing key in JSON payload raises SecretResolutionError."""
    payload = json.dumps({"api_key": "val"})
    client = FakeAwsSecretsClient({"clearcut/keys": payload})
    resolver = AwsSecretsManagerResolver(client=client, region="us-east-1")

    with pytest.raises(SecretResolutionError, match="Key 'missing_key' not found"):
        resolver.resolve("clearcut/keys#missing_key")


def test_aws_secrets_invalid_json_raises() -> None:
    """Invalid JSON when key extraction requested raises SecretResolutionError."""
    client = FakeAwsSecretsClient({"clearcut/raw": "not-valid-json"})
    resolver = AwsSecretsManagerResolver(client=client, region="us-east-1")

    with pytest.raises(SecretResolutionError, match="is not valid JSON"):
        resolver.resolve("clearcut/raw#some_key")


def test_aws_secrets_binary_payload_resolution() -> None:
    """Binary UTF-8 encoded secret resolves correctly."""
    client = FakeAwsSecretsClient({"clearcut/bin": b"binary-secret-val"})
    resolver = AwsSecretsManagerResolver(client=client, region="us-east-1")

    secret = resolver.resolve("clearcut/bin")
    assert secret.get_secret_value() == "binary-secret-val"


def test_aws_secrets_empty_payload_raises() -> None:
    """Empty secret payload raises SecretResolutionError."""
    client = FakeAwsSecretsClient({"clearcut/empty": ""})
    resolver = AwsSecretsManagerResolver(client=client, region="us-east-1")

    with pytest.raises(SecretResolutionError, match="empty"):
        resolver.resolve("clearcut/empty")


def test_aws_secrets_ttl_cache() -> None:
    """Resolving same secret within TTL makes only one SDK call."""
    client = FakeAwsSecretsClient({"clearcut/cached": "cached-val"})
    resolver = AwsSecretsManagerResolver(client=client, region="us-east-1", ttl_seconds=60)

    res1 = resolver.resolve("clearcut/cached")
    res2 = resolver.resolve("clearcut/cached")
    res3 = resolver.resolve("clearcut/cached")

    assert res1.get_secret_value() == "cached-val"
    assert res2.get_secret_value() == "cached-val"
    assert res3.get_secret_value() == "cached-val"
    assert len(client.calls) == 1


def test_aws_secrets_cache_expiration() -> None:
    """Resolving after TTL expires triggers a fresh SDK call."""
    client = FakeAwsSecretsClient({"clearcut/short": "val1"})
    resolver = AwsSecretsManagerResolver(client=client, region="us-east-1", ttl_seconds=0.01)

    resolver.resolve("clearcut/short")
    assert len(client.calls) == 1

    time.sleep(0.02)
    client.secrets["clearcut/short"] = "val2"
    res2 = resolver.resolve("clearcut/short")

    assert res2.get_secret_value() == "val2"
    assert len(client.calls) == 2


@pytest.mark.parametrize(
    ("error_code", "expected_msg"),
    [
        ("ResourceNotFoundException", "not found"),
        ("AccessDeniedException", "Access denied"),
        ("DecryptionFailureException", "Decryption failed"),
    ],
)
def test_aws_secrets_client_error_classification(error_code: str, expected_msg: str) -> None:
    """AWS client errors are mapped to classified SecretResolutionErrors."""
    client = FakeAwsSecretsClient()
    error_response = {
        "Error": {
            "Code": error_code,
            "Message": f"Simulated {error_code}",
        }
    }
    client.failure = ClientError(error_response, "GetSecretValue")
    resolver = AwsSecretsManagerResolver(client=client, region="us-east-1")

    with pytest.raises(SecretResolutionError) as exc_info:
        resolver.resolve("clearcut/failing")
    assert expected_msg.lower() in str(exc_info.value).lower()


def test_aws_secrets_no_environ_fallback(monkeypatch) -> None:
    """AWS Secrets Manager backend never falls back to os.environ on failure."""
    monkeypatch.setenv("LEAKED_SECRET", "super-secret-from-env")
    client = FakeAwsSecretsClient()  # Empty client -> ResourceNotFoundException
    resolver = AwsSecretsManagerResolver(client=client, region="us-east-1")

    with pytest.raises(SecretResolutionError):
        resolver.resolve("LEAKED_SECRET")


def test_build_secret_resolver_aws_backend() -> None:
    """build_secret_resolver constructs AwsSecretsManagerResolver for AWS_SECRETS_MANAGER."""
    settings = SecretsSettings(
        backend=SecretBackend.AWS_SECRETS_MANAGER,
        parallel_secret_arn="arn:aws:secretsmanager:us-east-1:123456789012:secret:clearcut/parallel",
    )
    fake_client = FakeAwsSecretsClient()
    resolver = build_secret_resolver(
        settings,
        client=fake_client,
        aws_region="us-east-1",
    )

    assert isinstance(resolver, AwsSecretsManagerResolver)

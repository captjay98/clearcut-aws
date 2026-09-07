"""Secret resolution conformance across Environment, Host, and Secret Manager backends."""
from __future__ import annotations

import traceback
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from clearcut.bootstrap.secrets import (
    EnvironmentSecretResolver,
    HostSecretResolver,
    SecretManagerResolver,
    SecretResolutionError,
    SecretResolver,
    build_secret_resolver,
)
from clearcut.bootstrap.settings import SecretBackend, SecretsSettings
from pydantic import SecretStr


class FakeSecretManagerClient:
    """Injected fake Secret Manager client for testing without cloud calls."""

    def __init__(self, secrets: dict[str, str] | None = None) -> None:
        self.secrets = secrets or {}
        self.calls: list[str] = []
        self.failure: Exception | None = None

    def access_secret_version(self, request: dict[str, str] | None = None, name: str | None = None) -> Any:
        secret_name = name or (request.get("name") if request else "")
        self.calls.append(secret_name or "")
        if self.failure:
            raise self.failure
        if secret_name not in self.secrets:
            raise RuntimeError(f"Secret {secret_name} not found")
        payload_bytes = self.secrets[secret_name].encode("utf-8")
        return SimpleNamespace(payload=SimpleNamespace(data=payload_bytes))


def test_environment_secret_resolution() -> None:
    environ = {"PARALLEL_API_KEY": "sk-parallel-test-12345"}
    resolver = EnvironmentSecretResolver(environ=environ)
    assert isinstance(resolver, SecretResolver)

    secret = resolver.resolve("PARALLEL_API_KEY")
    assert isinstance(secret, SecretStr)
    assert secret.get_secret_value() == "sk-parallel-test-12345"
    assert "sk-parallel-test-12345" not in repr(secret)
    assert "sk-parallel-test-12345" not in str(secret)


def test_environment_secret_missing_raises_typed_redacted_error() -> None:
    resolver = EnvironmentSecretResolver(environ={})
    with pytest.raises(SecretResolutionError) as exc_info:
        resolver.resolve("MISSING_KEY")

    assert "MISSING_KEY" in str(exc_info.value)
    assert "environment" in str(exc_info.value).lower()


def test_environment_secret_blank_raises_typed_error() -> None:
    resolver = EnvironmentSecretResolver(environ={"EMPTY_KEY": "   "})
    with pytest.raises(SecretResolutionError):
        resolver.resolve("EMPTY_KEY")


def test_host_secret_resolution(tmp_path: Path) -> None:
    secret_file = tmp_path / "PARALLEL_API_KEY"
    secret_file.write_text("sk-host-parallel-secret\n", encoding="utf-8")

    resolver = HostSecretResolver(secrets_dir=tmp_path)
    assert isinstance(resolver, SecretResolver)

    secret = resolver.resolve("PARALLEL_API_KEY")
    assert isinstance(secret, SecretStr)
    assert secret.get_secret_value() == "sk-host-parallel-secret"
    assert "sk-host-parallel-secret" not in repr(secret)


def test_host_secret_missing_raises_typed_error(tmp_path: Path) -> None:
    resolver = HostSecretResolver(secrets_dir=tmp_path)
    with pytest.raises(SecretResolutionError) as exc_info:
        resolver.resolve("NONEXISTENT_SECRET")

    assert "NONEXISTENT_SECRET" in str(exc_info.value)


@pytest.mark.parametrize("invalid_key", ["", "../escape", "sub/dir", "a/../b", "a\\b", "a\x00b"])
def test_host_secret_rejects_unsafe_paths(tmp_path: Path, invalid_key: str) -> None:
    resolver = HostSecretResolver(secrets_dir=tmp_path)
    with pytest.raises((SecretResolutionError, ValueError)):
        resolver.resolve(invalid_key)


def test_host_secret_blank_content_raises_typed_error(tmp_path: Path) -> None:
    secret_file = tmp_path / "BLANK_SECRET"
    secret_file.write_text("   \n", encoding="utf-8")

    resolver = HostSecretResolver(secrets_dir=tmp_path)
    with pytest.raises(SecretResolutionError):
        resolver.resolve("BLANK_SECRET")


def test_secret_manager_resolution_with_simple_name() -> None:
    fake_client = FakeSecretManagerClient(
        {"projects/my-gcp-project/secrets/PARALLEL_API_KEY/versions/latest": "sm-secret-val-999"}
    )
    resolver = SecretManagerResolver(client=fake_client, project_id="my-gcp-project")
    assert isinstance(resolver, SecretResolver)

    secret = resolver.resolve("PARALLEL_API_KEY")
    assert isinstance(secret, SecretStr)
    assert secret.get_secret_value() == "sm-secret-val-999"
    assert fake_client.calls == ["projects/my-gcp-project/secrets/PARALLEL_API_KEY/versions/latest"]


def test_secret_manager_resolution_with_full_path() -> None:
    full_path = "projects/custom-project/secrets/CUSTOM_SECRET/versions/2"
    fake_client = FakeSecretManagerClient({full_path: "version-2-value"})
    resolver = SecretManagerResolver(client=fake_client, project_id="ignored-project")

    secret = resolver.resolve(full_path)
    assert secret.get_secret_value() == "version-2-value"
    assert fake_client.calls == [full_path]


def test_secret_manager_provider_failure_is_typed_redacted() -> None:
    fake_client = FakeSecretManagerClient()
    fake_client.failure = RuntimeError("sensitive-credential-traceback-leak")
    resolver = SecretManagerResolver(client=fake_client, project_id="my-gcp-project")

    with pytest.raises(SecretResolutionError) as exc_info:
        resolver.resolve("PARALLEL_API_KEY")

    formatted_trace = "".join(traceback.format_exception(exc_info.value))
    assert "sensitive-credential-traceback-leak" not in formatted_trace
    assert "Secret resolution failed" in str(exc_info.value)


def test_no_cross_backend_fallback(tmp_path: Path) -> None:
    environ = {"TEST_SECRET": "env-val"}
    host_file = tmp_path / "TEST_SECRET"
    host_file.write_text("host-val", encoding="utf-8")
    sm_client = FakeSecretManagerClient(
        {"projects/p/secrets/TEST_SECRET/versions/latest": "sm-val"}
    )

    # Environment backend does not read host or SM
    env_resolver = EnvironmentSecretResolver(environ=environ)
    assert env_resolver.resolve("TEST_SECRET").get_secret_value() == "env-val"
    with pytest.raises(SecretResolutionError):
        env_resolver.resolve("OTHER_SECRET")

    # Host backend does not fall back to environment
    host_resolver = HostSecretResolver(secrets_dir=tmp_path)
    assert host_resolver.resolve("TEST_SECRET").get_secret_value() == "host-val"
    with pytest.raises(SecretResolutionError):
        host_resolver.resolve("MISSING_FROM_HOST")

    # Secret manager does not fall back to host or environment
    sm_resolver = SecretManagerResolver(client=sm_client, project_id="p")
    assert sm_resolver.resolve("TEST_SECRET").get_secret_value() == "sm-val"
    with pytest.raises(SecretResolutionError):
        sm_resolver.resolve("MISSING_FROM_SM")


@pytest.mark.parametrize(
    ("backend", "expected_cls"),
    [
        (SecretBackend.ENVIRONMENT, EnvironmentSecretResolver),
        (SecretBackend.HOST, HostSecretResolver),
        (SecretBackend.SECRET_MANAGER, SecretManagerResolver),
    ],
)
def test_build_secret_resolver_factory(tmp_path: Path, backend: SecretBackend, expected_cls: type) -> None:
    settings = SecretsSettings(backend=backend)
    fake_client = FakeSecretManagerClient()
    resolver = build_secret_resolver(
        settings,
        client=fake_client,
        environ={"FOO": "bar"},
        host_secrets_dir=tmp_path,
        project_id="test-proj",
    )
    assert isinstance(resolver, expected_cls)

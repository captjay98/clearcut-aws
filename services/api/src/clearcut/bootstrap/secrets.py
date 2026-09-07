"""Secret resolution backends with redacted error handling."""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from clearcut.bootstrap.settings import SecretBackend, SecretsSettings
from pydantic import SecretStr

DEFAULT_HOST_SECRETS_DIR = Path("/run/secrets")


class SecretResolutionError(RuntimeError):
    """Raised when a secret cannot be resolved, without leaking sensitive payload data."""


def _validate_safe_name(name: str) -> str:
    if not name or "\x00" in name or "\\" in name or "/" in name or ".." in name:
        raise ValueError(f"Invalid secret name: '{name}'")
    return name


class SecretResolver(ABC):
    """Abstract port for resolving secrets by name."""

    @abstractmethod
    def resolve(self, name: str) -> SecretStr:
        """Resolve a named secret to a SecretStr, failing closed if unavailable."""
        raise NotImplementedError


class EnvironmentSecretResolver(SecretResolver):
    """Resolves secrets from process environment or injected dictionary."""

    def __init__(self, environ: Mapping[str, str] | None = None) -> None:
        self._environ = os.environ if environ is None else environ

    def resolve(self, name: str) -> SecretStr:
        value = self._environ.get(name)
        if value is None or not value.strip():
            raise SecretResolutionError(f"Secret '{name}' not found in environment.")
        return SecretStr(value.strip())


class HostSecretResolver(SecretResolver):
    """Resolves secrets from host-mounted files (e.g., /run/secrets/{name})."""

    def __init__(self, secrets_dir: Path | str | None = None) -> None:
        self._secrets_dir = Path(secrets_dir) if secrets_dir is not None else DEFAULT_HOST_SECRETS_DIR

    def resolve(self, name: str) -> SecretStr:
        try:
            safe_name = _validate_safe_name(name)
        except ValueError as err:
            raise SecretResolutionError(f"Invalid host secret name: '{name}'") from err

        file_path = self._secrets_dir / safe_name
        try:
            # Prevent directory traversal escaping secrets_dir
            resolved = file_path.resolve()
            if not resolved.is_relative_to(self._secrets_dir.resolve()):
                raise SecretResolutionError(f"Path traversal detected for secret: '{name}'")
            if not resolved.is_file():
                raise SecretResolutionError(f"Secret file for '{name}' not found or not a regular file.")
            content = resolved.read_text(encoding="utf-8").strip()
            if not content:
                raise SecretResolutionError(f"Secret file for '{name}' is empty.")
            return SecretStr(content)
        except SecretResolutionError:
            raise
        except Exception:
            raise SecretResolutionError(f"Secret file for '{name}' could not be read.") from None


class SecretManagerResolver(SecretResolver):
    """Resolves secrets from Google Cloud Secret Manager using injected or default client."""

    def __init__(self, client: Any = None, project_id: str | None = None) -> None:
        self._client = client
        self._project_id = project_id

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from google.cloud import secretmanager

                self._client = secretmanager.SecretManagerServiceClient()
            except Exception:
                raise SecretResolutionError("Failed to initialize Google Secret Manager client.") from None
        return self._client

    def resolve(self, name: str) -> SecretStr:
        client = self._get_client()
        if "/" in name:
            secret_path = name
        else:
            if not self._project_id:
                raise SecretResolutionError(
                    f"Cannot resolve simple secret name '{name}' without configured project_id."
                )
            secret_path = f"projects/{self._project_id}/secrets/{name}/versions/latest"

        try:
            try:
                response = client.access_secret_version(request={"name": secret_path})
            except TypeError:
                response = client.access_secret_version(name=secret_path)
            data = response.payload.data.decode("utf-8").strip()
            if not data:
                raise SecretResolutionError(f"Secret '{name}' payload is empty.")
            return SecretStr(data)
        except SecretResolutionError:
            raise
        except Exception:
            raise SecretResolutionError(f"Secret resolution failed from Secret Manager for '{name}'.") from None


def build_secret_resolver(
    settings: SecretsSettings,
    *,
    client: Any = None,
    environ: Mapping[str, str] | None = None,
    host_secrets_dir: Path | str | None = None,
    project_id: str | None = None,
) -> SecretResolver:
    """Build the explicitly selected secret resolver based on settings."""
    if settings.backend is SecretBackend.ENVIRONMENT:
        return EnvironmentSecretResolver(environ=environ)
    if settings.backend is SecretBackend.HOST:
        return HostSecretResolver(secrets_dir=host_secrets_dir)
    if settings.backend is SecretBackend.SECRET_MANAGER:
        return SecretManagerResolver(client=client, project_id=project_id)
    raise SecretResolutionError(f"Unsupported secret backend: {settings.backend}")

"""AWS Secrets Manager resolver with client injection, bounded TTL caching, and JSON key extraction."""
from __future__ import annotations

import json
import threading
import time
from typing import Any

from botocore.exceptions import ClientError
from clearcut.bootstrap.secrets import SecretResolutionError, SecretResolver
from pydantic import SecretStr


class AwsSecretsManagerResolver(SecretResolver):
    """Resolves secrets from AWS Secrets Manager using IAM Task Roles with TTL caching.

    Fail-closed: never falls back to environment variables or host files on failure.
    Thread-safe bounded in-memory cache to prevent excessive AWS API calls and cost.
    Supports JSON key extraction via either the `json_key` argument or a `name#key` fragment.
    """

    def __init__(
        self,
        *,
        client: Any = None,
        region_name: str | None = None,
        region: str | None = None,
        cache_ttl_seconds: float = 300.0,
        ttl_seconds: float | None = None,
        max_cache_size: int = 128,
    ) -> None:
        self._client = client
        self._region_name = region or region_name
        effective_ttl = ttl_seconds if ttl_seconds is not None else cache_ttl_seconds
        self._cache_ttl_seconds = max(0.0, effective_ttl)
        self._max_cache_size = max(1, max_cache_size)
        self._cache: dict[str, tuple[SecretStr, float]] = {}
        self._lock = threading.Lock()

    def _get_client(self) -> Any:
        if self._client is None:
            import boto3
            from botocore.config import Config

            self._client = boto3.client(
                "secretsmanager",
                region_name=self._region_name,
                config=Config(
                    connect_timeout=5,
                    read_timeout=10,
                    retries={"total_max_attempts": 2},
                ),
            )
        return self._client

    def resolve(self, name: str, *, json_key: str | None = None) -> SecretStr:
        """Resolve a secret by name or ARN, optionally extracting a JSON key."""
        target_name = name.strip()
        target_key = json_key

        if "#" in target_name and target_key is None:
            target_name, target_key = target_name.split("#", 1)

        cache_key = f"{target_name}#{target_key}" if target_key else target_name

        with self._lock:
            now = time.monotonic()
            if cache_key in self._cache:
                cached_secret, expires_at = self._cache[cache_key]
                if now < expires_at:
                    return cached_secret

        client = self._get_client()
        try:
            response = client.get_secret_value(SecretId=target_name)
        except ClientError as error:
            error_code = error.response.get("Error", {}).get("Code", "")
            if error_code == "ResourceNotFoundException":
                raise SecretResolutionError(
                    f"Secret '{target_name}' not found in AWS Secrets Manager."
                ) from None
            if error_code == "AccessDeniedException":
                raise SecretResolutionError(
                    f"Access denied resolving secret '{target_name}' from AWS Secrets Manager."
                ) from None
            if error_code in {"DecryptionFailure", "DecryptionFailureException"}:
                raise SecretResolutionError(
                    f"KMS decryption failed for secret '{target_name}'."
                ) from None
            raise SecretResolutionError(
                f"Secret resolution failed from AWS Secrets Manager for '{target_name}'."
            ) from None
        except SecretResolutionError:
            raise
        except Exception:
            raise SecretResolutionError(
                f"Secret resolution failed from AWS Secrets Manager for '{target_name}'."
            ) from None

        payload = response.get("SecretString")
        if payload is None:
            raw_binary = response.get("SecretBinary")
            if raw_binary is not None:
                if isinstance(raw_binary, bytes):
                    payload = raw_binary.decode("utf-8")
                else:
                    payload = str(raw_binary)
        if payload is None:
            raise SecretResolutionError(f"Secret '{target_name}' payload is empty.")

        payload = payload.strip()
        if not payload:
            raise SecretResolutionError(f"Secret '{target_name}' payload is empty.")

        if target_key is not None:
            try:
                parsed = json.loads(payload)
            except Exception:
                raise SecretResolutionError(
                    f"Secret '{target_name}' payload is not valid JSON."
                ) from None
            if not isinstance(parsed, dict):
                raise SecretResolutionError(
                    f"Secret '{target_name}' payload is not a JSON object."
                )
            if target_key not in parsed:
                raise SecretResolutionError(
                    f"Key '{target_key}' not found in secret '{target_name}'."
                )
            field_value = str(parsed[target_key]).strip()
            if not field_value:
                raise SecretResolutionError(
                    f"Key '{target_key}' in secret '{target_name}' is empty."
                )
            resolved = SecretStr(field_value)
        else:
            resolved = SecretStr(payload)

        with self._lock:
            now = time.monotonic()
            if len(self._cache) >= self._max_cache_size:
                expired = [k for k, (_, exp) in self._cache.items() if now >= exp]
                for k in expired:
                    del self._cache[k]
                if len(self._cache) >= self._max_cache_size:
                    oldest_k = next(iter(self._cache))
                    del self._cache[oldest_k]
            self._cache[cache_key] = (resolved, now + self._cache_ttl_seconds)

        return resolved

    def invalidate(self, name: str | None = None) -> None:
        """Evict a specific secret or the entire cache."""
        with self._lock:
            if name is None:
                self._cache.clear()
            else:
                target = name.strip()
                keys_to_remove = [
                    k for k in self._cache if k == target or k.startswith(f"{target}#")
                ]
                for k in keys_to_remove:
                    del self._cache[k]

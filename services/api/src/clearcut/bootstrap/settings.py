"""Validated deployment-profile settings with fail-closed adapter selection."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

LOCAL_SQLITE_URL = "sqlite+aiosqlite:////tmp/clearcut.db"


def validate_hosted_database_url(database_url: str) -> None:
    """Validate a hosted database URL without exposing credentials in errors."""
    try:
        parsed_url = make_url(database_url)
        backend_name = parsed_url.get_backend_name()
        driver_name = parsed_url.drivername
        host = parsed_url.host
        database = parsed_url.database
        _ = parsed_url.port
    except (ArgumentError, ValueError):
        raise ValueError(
            "Hosted deployment profiles require a valid PostgreSQL SQLAlchemy URL "
            "with host and database."
        ) from None

    if backend_name != "postgresql":
        raise ValueError(
            "Hosted deployment profiles require a valid PostgreSQL SQLAlchemy URL."
        )
    if driver_name != "postgresql+asyncpg":
        raise ValueError(
            "Hosted deployment profiles require the supported PostgreSQL async "
            "driver (asyncpg)."
        )
    if not host or not database:
        raise ValueError(
            "Hosted deployment profiles require a valid PostgreSQL SQLAlchemy URL "
            "with host and database."
        )


class DeploymentProfile(StrEnum):
    LOCAL = "local"
    PORTABLE = "portable"
    GCP = "gcp"


class StorageAdapter(StrEnum):
    FILESYSTEM = "filesystem"
    S3 = "s3"
    GCS = "gcs"


class DispatchAdapter(StrEnum):
    LOCAL = "local"
    POSTGRES = "postgres"
    CLOUD_TASKS = "cloud_tasks"


class AuthenticationAdapter(StrEnum):
    BUILTIN = "builtin"
    FIREBASE = "firebase"


class SecretBackend(StrEnum):
    ENVIRONMENT = "environment"
    HOST = "host"
    SECRET_MANAGER = "secret_manager"


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class DatabaseSettings(_FrozenModel):
    url: str = Field(min_length=1)


class StorageSettings(_FrozenModel):
    adapter: StorageAdapter
    path: Path | None = None
    ephemeral: bool = False
    bucket: str | None = None
    project_id: str | None = None
    endpoint_url: str | None = None
    access_key_id: SecretStr | None = None
    secret_access_key: SecretStr | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_ephemeral_for_adapter(cls, value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        data = dict(value)
        try:
            adapter = StorageAdapter(data.get("adapter"))
        except (TypeError, ValueError):
            return data
        if adapter in {StorageAdapter.S3, StorageAdapter.GCS}:
            if "ephemeral" in data:
                raise ValueError(
                    f"{adapter.value.upper()} storage does not accept the filesystem-only "
                    "ephemeral setting."
                )
            if "path" in data:
                raise ValueError(
                    f"{adapter.value.upper()} storage does not accept the filesystem-only "
                    "path setting."
                )
            data["ephemeral"] = False
        else:
            data.setdefault("ephemeral", True)
        return data


class DispatchSettings(_FrozenModel):
    adapter: DispatchAdapter
    project_id: str | None = None
    location: str | None = None
    queue: str | None = None
    target_url: str | None = None
    audience: str | None = None
    service_account_email: str | None = None


class AuthenticationSettings(_FrozenModel):
    adapter: AuthenticationAdapter
    project_id: str | None = None
    audience: str | None = None


class SecretsSettings(_FrozenModel):
    backend: SecretBackend


_PROFILE_DEFAULTS: dict[DeploymentProfile, dict[str, StrEnum]] = {
    DeploymentProfile.LOCAL: {
        "storage": StorageAdapter.FILESYSTEM,
        "dispatch": DispatchAdapter.LOCAL,
        "authentication": AuthenticationAdapter.BUILTIN,
        "secrets": SecretBackend.ENVIRONMENT,
    },
    DeploymentProfile.PORTABLE: {
        "storage": StorageAdapter.S3,
        "dispatch": DispatchAdapter.POSTGRES,
        "authentication": AuthenticationAdapter.BUILTIN,
        "secrets": SecretBackend.HOST,
    },
    DeploymentProfile.GCP: {
        "storage": StorageAdapter.GCS,
        "dispatch": DispatchAdapter.CLOUD_TASKS,
        "authentication": AuthenticationAdapter.BUILTIN,
        "secrets": SecretBackend.SECRET_MANAGER,
    },
}


class ClearcutSettings(BaseSettings):
    """Immutable settings selected from one explicit deployment profile."""

    model_config = SettingsConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
    )

    profile: DeploymentProfile
    database: DatabaseSettings
    storage: StorageSettings
    dispatch: DispatchSettings
    authentication: AuthenticationSettings
    secrets: SecretsSettings
    paid_providers_enabled: frozenset[Literal["gemini", "parallel"]] = frozenset()

    @model_validator(mode="before")
    @classmethod
    def _apply_profile_defaults(cls, value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        data = dict(value)
        try:
            profile = DeploymentProfile(data.get("profile", DeploymentProfile.LOCAL))
        except ValueError:
            return data
        data["profile"] = profile
        defaults = _PROFILE_DEFAULTS[profile]
        for section, field_name in (
            ("storage", "adapter"),
            ("dispatch", "adapter"),
            ("authentication", "adapter"),
            ("secrets", "backend"),
        ):
            nested = dict(data.get(section) or {})
            nested.setdefault(field_name, defaults[section])
            data[section] = nested
        return data

    @model_validator(mode="after")
    def _validate_profile_contract(self) -> Self:
        if self.profile in {DeploymentProfile.PORTABLE, DeploymentProfile.GCP}:
            validate_hosted_database_url(self.database.url)
            if self.storage.adapter is StorageAdapter.FILESYSTEM and (
                self.profile is DeploymentProfile.GCP or self.storage.ephemeral
            ):
                raise ValueError(
                    "Hosted deployment profiles reject ephemeral filesystem storage."
                )

        allowed_storage = {
            DeploymentProfile.LOCAL: {StorageAdapter.FILESYSTEM},
            DeploymentProfile.PORTABLE: {
                StorageAdapter.FILESYSTEM,
                StorageAdapter.S3,
            },
            DeploymentProfile.GCP: {StorageAdapter.GCS, StorageAdapter.S3},
        }
        required_dispatch = {
            DeploymentProfile.LOCAL: DispatchAdapter.LOCAL,
            DeploymentProfile.PORTABLE: DispatchAdapter.POSTGRES,
            DeploymentProfile.GCP: DispatchAdapter.CLOUD_TASKS,
        }
        allowed_authentication = {
            DeploymentProfile.LOCAL: {AuthenticationAdapter.BUILTIN},
            DeploymentProfile.PORTABLE: {AuthenticationAdapter.BUILTIN},
            DeploymentProfile.GCP: {
                AuthenticationAdapter.BUILTIN,
                AuthenticationAdapter.FIREBASE,
            },
        }
        required_secrets = {
            DeploymentProfile.LOCAL: SecretBackend.ENVIRONMENT,
            DeploymentProfile.PORTABLE: SecretBackend.HOST,
            DeploymentProfile.GCP: SecretBackend.SECRET_MANAGER,
        }
        if self.storage.adapter not in allowed_storage[self.profile]:
            raise ValueError("Storage adapter contradicts the selected profile.")
        if self.dispatch.adapter is not required_dispatch[self.profile]:
            raise ValueError("Dispatch adapter contradicts the selected profile.")
        if self.authentication.adapter not in allowed_authentication[self.profile]:
            raise ValueError("Authentication adapter contradicts the selected profile.")
        if self.secrets.backend is not required_secrets[self.profile]:
            raise ValueError("Secret backend contradicts the selected profile.")

        if self.storage.adapter is StorageAdapter.FILESYSTEM and self.storage.path is None:
            raise ValueError("Filesystem storage requires a path.")
        if self.storage.adapter is StorageAdapter.FILESYSTEM and any(
            (
                self.storage.bucket,
                self.storage.project_id,
                self.storage.endpoint_url,
                self.storage.access_key_id,
                self.storage.secret_access_key,
            )
        ):
            raise ValueError("Filesystem storage does not accept hosted storage fields.")
        if self.storage.adapter is StorageAdapter.S3 and self.storage.path is not None:
            raise ValueError("S3 storage does not accept a filesystem path.")
        if self.storage.adapter is StorageAdapter.S3 and self.storage.project_id is not None:
            raise ValueError("S3 storage does not accept a GCS project_id.")
        if self.storage.adapter is StorageAdapter.GCS and any(
            (
                self.storage.path,
                self.storage.endpoint_url,
                self.storage.access_key_id,
                self.storage.secret_access_key,
            )
        ):
            raise ValueError("GCS storage does not accept filesystem or S3 fields.")
        if self.storage.adapter is StorageAdapter.S3 and not self.storage.bucket:
            raise ValueError("S3 storage requires a bucket.")
        if self.storage.adapter is StorageAdapter.GCS and not all(
            (self.storage.project_id, self.storage.bucket)
        ):
            raise ValueError("GCS storage requires project_id and bucket.")
        cloud_tasks_fields = (
            self.dispatch.project_id,
            self.dispatch.location,
            self.dispatch.queue,
            self.dispatch.target_url,
            self.dispatch.audience,
            self.dispatch.service_account_email,
        )
        if (
            self.dispatch.adapter is not DispatchAdapter.CLOUD_TASKS
            and any(cloud_tasks_fields)
        ):
            raise ValueError(
                f"{self.dispatch.adapter.value} dispatch does not accept Cloud Tasks fields."
            )
        if self.dispatch.adapter is DispatchAdapter.CLOUD_TASKS and not all(
            cloud_tasks_fields
        ):
            raise ValueError(
                "Cloud Tasks dispatch requires project_id, location, queue, target_url, "
                "audience, and service_account_email."
            )
        if self.authentication.adapter is AuthenticationAdapter.BUILTIN and any(
            (self.authentication.project_id, self.authentication.audience)
        ):
            raise ValueError(
                "Built-in authentication does not accept Firebase configuration."
            )
        if self.authentication.adapter is AuthenticationAdapter.FIREBASE and not all(
            (self.authentication.project_id, self.authentication.audience)
        ):
            raise ValueError("Firebase authentication requires project_id and audience.")
        return self

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> Self:
        """Build settings from environment without constructing any runtime adapter."""
        source = os.environ if environ is None else environ
        profile = source.get("CLEARCUT_DEPLOYMENT_PROFILE", "local").strip().lower()
        database_url = source.get("DATABASE_URL", "").strip()
        if not database_url and profile == DeploymentProfile.LOCAL:
            database_url = LOCAL_SQLITE_URL

        storage: dict[str, Any] = {}
        dispatch: dict[str, Any] = {}
        authentication: dict[str, Any] = {}
        secrets: dict[str, Any] = {}
        optional_values = (
            (
                storage,
                {
                    "adapter": "CLEARCUT_STORAGE_ADAPTER",
                    "path": "CLEARCUT_STORAGE_PATH",
                    "ephemeral": "CLEARCUT_STORAGE_EPHEMERAL",
                    "bucket": "CLEARCUT_STORAGE_BUCKET",
                    "project_id": "CLEARCUT_STORAGE_PROJECT_ID",
                    "endpoint_url": "CLEARCUT_STORAGE_ENDPOINT_URL",
                    "access_key_id": "CLEARCUT_STORAGE_ACCESS_KEY_ID",
                    "secret_access_key": "CLEARCUT_STORAGE_SECRET_ACCESS_KEY",
                },
            ),
            (
                dispatch,
                {
                    "adapter": "CLEARCUT_DISPATCH_ADAPTER",
                    "project_id": "CLEARCUT_CLOUD_TASKS_PROJECT_ID",
                    "location": "CLEARCUT_CLOUD_TASKS_LOCATION",
                    "queue": "CLEARCUT_CLOUD_TASKS_QUEUE",
                    "target_url": "CLEARCUT_CLOUD_TASKS_TARGET_URL",
                    "audience": "CLEARCUT_CLOUD_TASKS_AUDIENCE",
                    "service_account_email": "CLEARCUT_CLOUD_TASKS_SERVICE_ACCOUNT_EMAIL",
                },
            ),
            (
                authentication,
                {
                    "adapter": "CLEARCUT_AUTHENTICATION_ADAPTER",
                    "project_id": "CLEARCUT_FIREBASE_PROJECT_ID",
                    "audience": "CLEARCUT_FIREBASE_AUDIENCE",
                },
            ),
            (secrets, {"backend": "CLEARCUT_SECRET_BACKEND"}),
        )
        for target, fields in optional_values:
            for field_name, variable in fields.items():
                value = source.get(variable)
                if value is not None and value.strip():
                    target[field_name] = value.strip()
        if profile == DeploymentProfile.LOCAL and "path" not in storage:
            storage["path"] = str(Path(tempfile.gettempdir()) / "clearcut-storage")

        paid_providers = frozenset(
            name.strip()
            for name in source.get("CLEARCUT_PAID_PROVIDERS_ENABLED", "").split(",")
            if name.strip()
        )
        return cls.model_validate(
            {
                "profile": profile,
                "database": {"url": database_url},
                "storage": storage,
                "dispatch": dispatch,
                "authentication": authentication,
                "secrets": secrets,
                "paid_providers_enabled": paid_providers,
            }
        )

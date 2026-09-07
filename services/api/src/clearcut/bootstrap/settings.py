"""Validated deployment-profile settings with fail-closed adapter selection."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal, NoReturn, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

LOCAL_SQLITE_URL = "sqlite+aiosqlite:////tmp/clearcut.db"


def validate_hosted_database_url(database_url: str | SecretStr) -> None:
    """Validate a hosted database URL without exposing credentials in errors."""
    url_value = (
        database_url.get_secret_value()
        if isinstance(database_url, SecretStr)
        else database_url
    )
    try:
        parsed_url = make_url(url_value)
        backend_name = parsed_url.get_backend_name()
        driver_name = parsed_url.drivername
        host = parsed_url.host
        database = parsed_url.database
        port = parsed_url.port
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
    if not host or not database or (port is not None and not 1 <= port <= 65_535):
        raise ValueError(
            "Hosted deployment profiles require a valid PostgreSQL SQLAlchemy URL "
            "with host, database, and a port between 1 and 65535."
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
    url: SecretStr = Field(min_length=1)


class FilesystemStorageSettings(_FrozenModel):
    adapter: Literal[StorageAdapter.FILESYSTEM] = StorageAdapter.FILESYSTEM
    path: Path
    ephemeral: bool = True


class S3StorageSettings(_FrozenModel):
    adapter: Literal[StorageAdapter.S3] = StorageAdapter.S3
    bucket: str = Field(min_length=1)
    endpoint_url: str | None = None
    region: str | None = None
    access_key_id: SecretStr | None = None
    secret_access_key: SecretStr | None = None


class GCSStorageSettings(_FrozenModel):
    adapter: Literal[StorageAdapter.GCS] = StorageAdapter.GCS
    bucket: str = Field(min_length=1)
    project_id: str = Field(min_length=1)


StorageSettings = Annotated[
    FilesystemStorageSettings | S3StorageSettings | GCSStorageSettings,
    Field(discriminator="adapter"),
]


class DispatchSettings(_FrozenModel):
    adapter: DispatchAdapter
    enabled: bool = True
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

    def _raise_redacted_validation_error(self, message: str) -> NoReturn:
        raise ValidationError.from_exception_data(
            self.__class__.__name__,
            [
                {
                    "type": "value_error",
                    "loc": (),
                    "input": self.model_dump(mode="json"),
                    "ctx": {"error": ValueError(message)},
                }
            ],
        )

    @model_validator(mode="after")
    def _validate_profile_contract(self) -> Self:
        if self.profile in {DeploymentProfile.PORTABLE, DeploymentProfile.GCP}:
            try:
                validate_hosted_database_url(self.database.url)
            except ValueError as error:
                self._raise_redacted_validation_error(str(error))
            if self.storage.adapter is StorageAdapter.FILESYSTEM and (
                self.profile is DeploymentProfile.GCP or self.storage.ephemeral
            ):
                self._raise_redacted_validation_error(
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
            self._raise_redacted_validation_error(
                "Storage adapter contradicts the selected profile."
            )
        if self.dispatch.adapter is not required_dispatch[self.profile]:
            self._raise_redacted_validation_error(
                "Dispatch adapter contradicts the selected profile."
            )
        if (
            self.profile in {DeploymentProfile.PORTABLE, DeploymentProfile.GCP}
            and not self.dispatch.enabled
        ):
            self._raise_redacted_validation_error(
                "Hosted deployment profiles require dispatch to remain enabled."
            )
        if self.authentication.adapter not in allowed_authentication[self.profile]:
            self._raise_redacted_validation_error(
                "Authentication adapter contradicts the selected profile."
            )
        if self.secrets.backend is not required_secrets[self.profile]:
            self._raise_redacted_validation_error(
                "Secret backend contradicts the selected profile."
            )

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
            self._raise_redacted_validation_error(
                f"{self.dispatch.adapter.value} dispatch does not accept Cloud Tasks fields."
            )
        if self.dispatch.adapter is DispatchAdapter.CLOUD_TASKS and not all(
            cloud_tasks_fields
        ):
            self._raise_redacted_validation_error(
                "Cloud Tasks dispatch requires project_id, location, queue, target_url, "
                "audience, and service_account_email."
            )
        if self.authentication.adapter is AuthenticationAdapter.BUILTIN and any(
            (self.authentication.project_id, self.authentication.audience)
        ):
            self._raise_redacted_validation_error(
                "Built-in authentication does not accept Firebase configuration."
            )
        if self.authentication.adapter is AuthenticationAdapter.FIREBASE and not all(
            (self.authentication.project_id, self.authentication.audience)
        ):
            self._raise_redacted_validation_error(
                "Firebase authentication requires project_id and audience."
            )
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
                    "region": "CLEARCUT_STORAGE_REGION",
                    "access_key_id": "CLEARCUT_STORAGE_ACCESS_KEY_ID",
                    "secret_access_key": "CLEARCUT_STORAGE_SECRET_ACCESS_KEY",
                },
            ),
            (
                dispatch,
                {
                    "adapter": "CLEARCUT_DISPATCH_ADAPTER",
                    "enabled": "CLEARCUT_DISPATCH_ENABLED",
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

        legacy_dispatch_mode = source.get("CLEARCUT_JOB_DISPATCH_MODE", "").strip().lower()
        if profile == DeploymentProfile.LOCAL and legacy_dispatch_mode:
            if legacy_dispatch_mode not in {"disabled", "local"}:
                raise ValueError(
                    "CLEARCUT_JOB_DISPATCH_MODE must be 'disabled' or 'local'."
                )
            dispatch.setdefault("enabled", legacy_dispatch_mode == "local")

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

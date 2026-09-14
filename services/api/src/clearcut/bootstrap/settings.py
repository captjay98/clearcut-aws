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
        database_url.get_secret_value() if isinstance(database_url, SecretStr) else database_url
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
        raise ValueError("Hosted deployment profiles require a valid PostgreSQL SQLAlchemy URL.")
    if driver_name != "postgresql+asyncpg":
        raise ValueError(
            "Hosted deployment profiles require the supported PostgreSQL async driver (asyncpg)."
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
    AWS = "aws"


class StorageAdapter(StrEnum):
    FILESYSTEM = "filesystem"
    S3 = "s3"
    GCS = "gcs"


class DispatchAdapter(StrEnum):
    LOCAL = "local"
    POSTGRES = "postgres"
    CLOUD_TASKS = "cloud_tasks"
    SQS = "sqs"


class AuthenticationAdapter(StrEnum):
    BUILTIN = "builtin"
    FIREBASE = "firebase"


class SecretBackend(StrEnum):
    ENVIRONMENT = "environment"
    HOST = "host"
    SECRET_MANAGER = "secret_manager"
    AWS_SECRETS_MANAGER = "aws_secrets_manager"


class ModelBackend(StrEnum):
    GEMINI = "gemini"
    BEDROCK = "bedrock"


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
    queue_url: str | None = None
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
    parallel_secret_arn: str | None = None


class StaticDeliverySettings(_FrozenModel):
    enabled: bool = False
    site_dist: Path | None = None
    workspace_dist: Path | None = None


_PROFILE_DEFAULTS: dict[DeploymentProfile, dict[str, StrEnum]] = {
    DeploymentProfile.LOCAL: {
        "storage": StorageAdapter.FILESYSTEM,
        "dispatch": DispatchAdapter.LOCAL,
        "authentication": AuthenticationAdapter.BUILTIN,
        "secrets": SecretBackend.ENVIRONMENT,
        "model_backend": ModelBackend.GEMINI,
    },
    DeploymentProfile.PORTABLE: {
        "storage": StorageAdapter.S3,
        "dispatch": DispatchAdapter.POSTGRES,
        "authentication": AuthenticationAdapter.BUILTIN,
        "secrets": SecretBackend.HOST,
        "model_backend": ModelBackend.GEMINI,
    },
    DeploymentProfile.GCP: {
        "storage": StorageAdapter.GCS,
        "dispatch": DispatchAdapter.CLOUD_TASKS,
        "authentication": AuthenticationAdapter.BUILTIN,
        "secrets": SecretBackend.SECRET_MANAGER,
        "model_backend": ModelBackend.GEMINI,
    },
    DeploymentProfile.AWS: {
        "storage": StorageAdapter.S3,
        "dispatch": DispatchAdapter.SQS,
        "authentication": AuthenticationAdapter.BUILTIN,
        "secrets": SecretBackend.AWS_SECRETS_MANAGER,
        "model_backend": ModelBackend.BEDROCK,
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
    model_backend: ModelBackend = ModelBackend.GEMINI
    aws_region: str | None = None
    bedrock_detection_model: str | None = None
    bedrock_research_model: str | None = None
    bedrock_synthesis_model: str | None = None
    bedrock_judge_model: str | None = None
    gcp_project: str | None = None
    static_delivery: StaticDeliverySettings = StaticDeliverySettings()
    paid_providers_enabled: frozenset[Literal["gemini", "parallel", "bedrock"]] = frozenset()
    paid_provider_cost_acknowledged: bool = False
    paid_provider_concurrency_limits: dict[Literal["gemini", "parallel", "bedrock"], int] = Field(
        default_factory=lambda: {"gemini": 1, "parallel": 1, "bedrock": 1}
    )


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
        data.setdefault("model_backend", defaults.get("model_backend", ModelBackend.GEMINI))
        static_delivery = dict(data.get("static_delivery") or {})
        static_delivery.setdefault("enabled", profile is not DeploymentProfile.LOCAL)
        data["static_delivery"] = static_delivery
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
        if self.profile in {DeploymentProfile.PORTABLE, DeploymentProfile.GCP, DeploymentProfile.AWS}:
            try:
                validate_hosted_database_url(self.database.url)
            except ValueError as error:
                self._raise_redacted_validation_error(str(error))
            if self.storage.adapter is StorageAdapter.FILESYSTEM and (
                self.profile in {DeploymentProfile.GCP, DeploymentProfile.AWS} or self.storage.ephemeral
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
            DeploymentProfile.AWS: {StorageAdapter.S3},
        }
        required_dispatch = {
            DeploymentProfile.LOCAL: DispatchAdapter.LOCAL,
            DeploymentProfile.PORTABLE: DispatchAdapter.POSTGRES,
            DeploymentProfile.GCP: DispatchAdapter.CLOUD_TASKS,
            DeploymentProfile.AWS: DispatchAdapter.SQS,
        }
        allowed_authentication = {
            DeploymentProfile.LOCAL: {AuthenticationAdapter.BUILTIN},
            DeploymentProfile.PORTABLE: {AuthenticationAdapter.BUILTIN},
            DeploymentProfile.GCP: {
                AuthenticationAdapter.BUILTIN,
                AuthenticationAdapter.FIREBASE,
            },
            DeploymentProfile.AWS: {AuthenticationAdapter.BUILTIN},
        }
        required_secrets = {
            DeploymentProfile.LOCAL: SecretBackend.ENVIRONMENT,
            DeploymentProfile.PORTABLE: SecretBackend.HOST,
            DeploymentProfile.GCP: SecretBackend.SECRET_MANAGER,
            DeploymentProfile.AWS: SecretBackend.AWS_SECRETS_MANAGER,
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
            self.profile in {DeploymentProfile.PORTABLE, DeploymentProfile.GCP, DeploymentProfile.AWS}
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
        if self.profile is DeploymentProfile.AWS and any(cloud_tasks_fields):
            self._raise_redacted_validation_error(
                "Hosted AWS mode rejects contradictory GCP configuration."
            )
        if self.dispatch.adapter is not DispatchAdapter.CLOUD_TASKS and any(cloud_tasks_fields):
            self._raise_redacted_validation_error(
                f"{self.dispatch.adapter.value} dispatch does not accept Cloud Tasks fields."
            )
        if self.dispatch.adapter is DispatchAdapter.CLOUD_TASKS and not all(cloud_tasks_fields):
            self._raise_redacted_validation_error(
                "Cloud Tasks dispatch requires project_id, location, queue, target_url, "
                "audience, and service_account_email."
            )
        if self.authentication.adapter is AuthenticationAdapter.BUILTIN and any(
            (self.authentication.project_id, self.authentication.audience)
        ):
            if self.profile is DeploymentProfile.AWS:
                self._raise_redacted_validation_error(
                    "Hosted AWS mode rejects contradictory GCP configuration."
                )
            self._raise_redacted_validation_error(
                "Built-in authentication does not accept Firebase configuration."
            )
        if self.authentication.adapter is AuthenticationAdapter.FIREBASE and not all(
            (self.authentication.project_id, self.authentication.audience)
        ):
            self._raise_redacted_validation_error(
                "Firebase authentication requires project_id and audience."
            )

        if self.profile is DeploymentProfile.AWS:
            if isinstance(self.storage, S3StorageSettings):
                if self.storage.access_key_id is not None or self.storage.secret_access_key is not None:
                    self._raise_redacted_validation_error(
                        "Hosted AWS deployment profile rejects static AWS credentials; use IAM task roles."
                    )
                if self.storage.endpoint_url is not None:
                    self._raise_redacted_validation_error(
                        "Hosted AWS deployment profile rejects custom storage emulator endpoints."
                    )
                if not self.storage.bucket:
                    self._raise_redacted_validation_error(
                        "Hosted AWS mode requires storage bucket."
                    )
            if not self.aws_region or not self.aws_region.strip():
                self._raise_redacted_validation_error(
                    "Hosted AWS mode requires AWS region to be configured."
                )
            if not self.dispatch.queue_url or not self.dispatch.queue_url.strip():
                self._raise_redacted_validation_error(
                    "SQS dispatch requires queue_url."
                )
            if not self.secrets.parallel_secret_arn or not self.secrets.parallel_secret_arn.strip():
                self._raise_redacted_validation_error(
                    "AWS Secrets Manager backend requires parallel_secret_arn to be configured."
                )
            if self.model_backend is not ModelBackend.BEDROCK:
                self._raise_redacted_validation_error(
                    "Hosted AWS profile requires Bedrock model backend."
                )
            if not self.bedrock_detection_model or not self.bedrock_detection_model.strip():
                self._raise_redacted_validation_error(
                    "Hosted AWS profile requires bedrock_detection_model."
                )
            if not self.bedrock_research_model or not self.bedrock_research_model.strip():
                self._raise_redacted_validation_error(
                    "Hosted AWS profile requires bedrock_research_model."
                )
            if not self.bedrock_judge_model or not self.bedrock_judge_model.strip():
                self._raise_redacted_validation_error(
                    "Hosted AWS profile requires bedrock_judge_model."
                )
            if self.gcp_project:
                self._raise_redacted_validation_error(
                    "Hosted AWS mode rejects contradictory GCP configuration."
                )
            if getattr(self.storage, "project_id", None):
                self._raise_redacted_validation_error(
                    "Hosted AWS mode rejects contradictory GCP configuration."
                )

        if self.paid_providers_enabled and not self.paid_provider_cost_acknowledged:
            self._raise_redacted_validation_error(
                "Paid provider enablement requires explicit cost acknowledgement."
            )
        if any(limit <= 0 for limit in self.paid_provider_concurrency_limits.values()):
            self._raise_redacted_validation_error(
                "Paid provider concurrency limits must be positive."
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
        static_delivery: dict[str, Any] = {}
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
                    "queue_url": "CLEARCUT_SQS_QUEUE_URL",
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
            (
                secrets,
                {
                    "backend": "CLEARCUT_SECRET_BACKEND",
                    "parallel_secret_arn": "CLEARCUT_PARALLEL_SECRET_ARN",
                },
            ),
            (
                static_delivery,
                {
                    "enabled": "CLEARCUT_STATIC_DELIVERY_ENABLED",
                    "site_dist": "CLEARCUT_SITE_DIST_PATH",
                    "workspace_dist": "CLEARCUT_WORKSPACE_DIST_PATH",
                },
            ),
        )
        for target, fields in optional_values:
            for field_name, variable in fields.items():
                value = source.get(variable)
                if value is not None and value.strip():
                    target[field_name] = value.strip()
        if profile == DeploymentProfile.LOCAL and "path" not in storage:
            storage["path"] = str(Path(tempfile.gettempdir()) / "clearcut-storage")

        if "endpoint_url" not in storage:
            endpoint = source.get("AWS_ENDPOINT_URL") or source.get("S3_ENDPOINT_URL")
            if endpoint and endpoint.strip():
                storage["endpoint_url"] = endpoint.strip()

        if "access_key_id" not in storage:
            ak = source.get("AWS_ACCESS_KEY_ID")
            if ak and ak.strip():
                storage["access_key_id"] = ak.strip()
        if "secret_access_key" not in storage:
            sk = source.get("AWS_SECRET_ACCESS_KEY")
            if sk and sk.strip():
                storage["secret_access_key"] = sk.strip()

        aws_region = (
            source.get("AWS_REGION")
            or source.get("AWS_DEFAULT_REGION")
            or source.get("CLEARCUT_STORAGE_REGION")
        )
        if aws_region and aws_region.strip():
            aws_region = aws_region.strip()
            if "region" not in storage:
                storage["region"] = aws_region
        else:
            aws_region = None

        bedrock_detection_model = source.get("CLEARCUT_BEDROCK_DETECTION_MODEL")
        if bedrock_detection_model:
            bedrock_detection_model = bedrock_detection_model.strip()
        bedrock_research_model = source.get("CLEARCUT_BEDROCK_RESEARCH_MODEL")
        if bedrock_research_model:
            bedrock_research_model = bedrock_research_model.strip()
        bedrock_synthesis_model = source.get("CLEARCUT_BEDROCK_SYNTHESIS_MODEL")
        if bedrock_synthesis_model:
            bedrock_synthesis_model = bedrock_synthesis_model.strip()
        elif bedrock_research_model:
            bedrock_synthesis_model = bedrock_research_model
        bedrock_judge_model = source.get("CLEARCUT_BEDROCK_JUDGE_MODEL")
        if bedrock_judge_model:
            bedrock_judge_model = bedrock_judge_model.strip()

        model_backend = source.get("CLEARCUT_MODEL_BACKEND")
        if model_backend and model_backend.strip():
            model_backend = model_backend.strip().lower()
        else:
            model_backend = None

        gcp_project = (
            source.get("GOOGLE_CLOUD_PROJECT")
            or source.get("CLEARCUT_GCP_PROJECT")
            or source.get("GCP_PROJECT")
            or source.get("GCS_BUCKET")
            or source.get("CLOUD_TASKS_QUEUE")
        )
        gcp_project = gcp_project.strip() if gcp_project and gcp_project.strip() else None

        legacy_dispatch_mode = source.get("CLEARCUT_JOB_DISPATCH_MODE", "").strip().lower()
        if profile == DeploymentProfile.LOCAL and legacy_dispatch_mode:
            if legacy_dispatch_mode not in {"disabled", "local"}:
                raise ValueError("CLEARCUT_JOB_DISPATCH_MODE must be 'disabled' or 'local'.")
            dispatch.setdefault("enabled", legacy_dispatch_mode == "local")

        paid_providers = frozenset(
            name.strip().lower()
            for name in source.get("CLEARCUT_PAID_PROVIDERS_ENABLED", "").split(",")
            if name.strip()
        )
        paid_provider_concurrency_limits = {
            "gemini": source.get("CLEARCUT_GEMINI_CONCURRENCY_LIMIT", "1"),
            "parallel": source.get("CLEARCUT_PARALLEL_CONCURRENCY_LIMIT", "1"),
            "bedrock": source.get("CLEARCUT_BEDROCK_CONCURRENCY_LIMIT", "1"),
        }
        payload: dict[str, Any] = {
            "profile": profile,
            "database": {"url": database_url},
            "storage": storage,
            "dispatch": dispatch,
            "authentication": authentication,
            "secrets": secrets,
            "static_delivery": static_delivery,
            "paid_providers_enabled": paid_providers,
            "paid_provider_cost_acknowledged": source.get(
                "CLEARCUT_PAID_PROVIDER_COST_ACKNOWLEDGED", "false"
            ),
            "paid_provider_concurrency_limits": paid_provider_concurrency_limits,
        }
        if model_backend:
            payload["model_backend"] = model_backend
        if aws_region:
            payload["aws_region"] = aws_region
        if bedrock_detection_model:
            payload["bedrock_detection_model"] = bedrock_detection_model
        if bedrock_research_model:
            payload["bedrock_research_model"] = bedrock_research_model
        if bedrock_synthesis_model:
            payload["bedrock_synthesis_model"] = bedrock_synthesis_model
        if bedrock_judge_model:
            payload["bedrock_judge_model"] = bedrock_judge_model
        if gcp_project:
            payload["gcp_project"] = gcp_project

        return cls.model_validate(payload)


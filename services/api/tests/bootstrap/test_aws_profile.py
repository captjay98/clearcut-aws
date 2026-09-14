"""Tests for AWS deployment profile defaults, environment loading, and fail-closed validation."""

from __future__ import annotations

import pytest
from clearcut.bootstrap.settings import (
    AuthenticationAdapter,
    ClearcutSettings,
    DeploymentProfile,
    DispatchAdapter,
    ModelBackend,
    SecretBackend,
    StorageAdapter,
)
from pydantic import ValidationError

VALID_AWS_ENV: dict[str, str] = {
    "CLEARCUT_DEPLOYMENT_PROFILE": "aws",
    "DATABASE_URL": "postgresql+asyncpg://clearcut:pass@aurora.internal:5432/clearcut",
    "AWS_REGION": "us-east-1",
    "CLEARCUT_STORAGE_BUCKET": "clearcut-prod-artifacts",
    "CLEARCUT_SQS_QUEUE_URL": "https://sqs.us-east-1.amazonaws.com/123456789012/clearcut-jobs",
    "CLEARCUT_PARALLEL_SECRET_ARN": "arn:aws:secretsmanager:us-east-1:123456789012:secret:clearcut/parallel",
    "CLEARCUT_BEDROCK_DETECTION_MODEL": "anthropic.claude-3-haiku-20240307-v1:0",
    "CLEARCUT_BEDROCK_RESEARCH_MODEL": "anthropic.claude-3-5-sonnet-20240620-v1:0",
    "CLEARCUT_BEDROCK_JUDGE_MODEL": "anthropic.claude-3-5-sonnet-20240620-v1:0",
}


def test_aws_profile_defaults() -> None:
    """profile='aws' defaults to s3, sqs, builtin, aws_secrets_manager, and bedrock."""
    settings = ClearcutSettings.from_environment(VALID_AWS_ENV)

    assert settings.profile == DeploymentProfile.AWS
    assert settings.storage.adapter == StorageAdapter.S3
    assert settings.dispatch.adapter == DispatchAdapter.SQS
    assert settings.dispatch.enabled is True
    assert settings.authentication.adapter == AuthenticationAdapter.BUILTIN
    assert settings.secrets.backend == SecretBackend.AWS_SECRETS_MANAGER
    assert settings.model_backend == ModelBackend.BEDROCK
    assert settings.aws_region == "us-east-1"
    assert settings.storage.bucket == "clearcut-prod-artifacts"
    assert settings.dispatch.queue_url == "https://sqs.us-east-1.amazonaws.com/123456789012/clearcut-jobs"
    assert settings.secrets.parallel_secret_arn == "arn:aws:secretsmanager:us-east-1:123456789012:secret:clearcut/parallel"
    assert settings.bedrock_detection_model == "anthropic.claude-3-haiku-20240307-v1:0"
    assert settings.bedrock_research_model == "anthropic.claude-3-5-sonnet-20240620-v1:0"
    assert settings.bedrock_judge_model == "anthropic.claude-3-5-sonnet-20240620-v1:0"


def test_aws_profile_rejects_sqlite() -> None:
    """AWS profile rejects SQLite database URL."""
    env = {
        **VALID_AWS_ENV,
        "DATABASE_URL": "sqlite+aiosqlite:////tmp/clearcut.db",
    }
    with pytest.raises(ValidationError, match="require a valid PostgreSQL SQLAlchemy URL"):
        ClearcutSettings.from_environment(env)


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://localhost:4566",
        "http://127.0.0.1:4566",
        "http://localstack:4566",
    ],
)
def test_aws_profile_rejects_storage_emulator_endpoint(endpoint: str) -> None:
    """AWS profile fails closed if emulator/custom endpoint URL is specified."""
    env = {
        **VALID_AWS_ENV,
        "CLEARCUT_STORAGE_ENDPOINT_URL": endpoint,
    }
    with pytest.raises(ValidationError, match="rejects custom storage emulator endpoints"):
        ClearcutSettings.from_environment(env)


@pytest.mark.parametrize(
    ("key", "val"),
    [
        ("AWS_ACCESS_KEY_ID", "AKIAIOSFODNN7EXAMPLE"),
        ("AWS_SECRET_ACCESS_KEY", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"),
        ("CLEARCUT_STORAGE_ACCESS_KEY_ID", "AKIAIOSFODNN7EXAMPLE"),
        ("CLEARCUT_STORAGE_SECRET_ACCESS_KEY", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"),
    ],
)
def test_aws_profile_rejects_static_aws_credentials(key: str, val: str) -> None:
    """AWS profile rejects static credentials in favor of IAM Task/Instance Roles."""
    env = {
        **VALID_AWS_ENV,
        key: val,
    }
    with pytest.raises(ValidationError, match="rejects static AWS credentials"):
        ClearcutSettings.from_environment(env)


@pytest.mark.parametrize(
    ("key", "val"),
    [
        ("GOOGLE_CLOUD_PROJECT", "my-gcp-project"),
        ("GCP_PROJECT", "my-gcp-project"),
        ("GCS_BUCKET", "my-gcs-bucket"),
        ("CLOUD_TASKS_QUEUE", "clearcut-tasks"),
    ],
)
def test_aws_profile_rejects_gcp_contradictions(key: str, val: str) -> None:
    """AWS profile rejects contradictory Google Cloud configuration."""
    env = {
        **VALID_AWS_ENV,
        key: val,
    }
    with pytest.raises(ValidationError, match="rejects contradictory GCP configuration"):
        ClearcutSettings.from_environment(env)


@pytest.mark.parametrize("adapter", ["local", "postgres", "cloud_tasks"])
def test_aws_profile_rejects_invalid_dispatch_adapter(adapter: str) -> None:
    """AWS profile requires SQS dispatch adapter."""
    env = {
        **VALID_AWS_ENV,
        "CLEARCUT_DISPATCH_ADAPTER": adapter,
    }
    with pytest.raises(ValidationError, match="Dispatch adapter contradicts the selected profile"):
        ClearcutSettings.from_environment(env)


def test_aws_profile_rejects_disabled_dispatch() -> None:
    """AWS profile requires dispatch to remain enabled."""
    env = {
        **VALID_AWS_ENV,
        "CLEARCUT_DISPATCH_ENABLED": "false",
    }
    with pytest.raises(ValidationError, match="require dispatch to remain enabled"):
        ClearcutSettings.from_environment(env)


def test_aws_profile_requires_aws_region() -> None:
    """AWS profile fails closed if AWS region is missing."""
    env = {k: v for k, v in VALID_AWS_ENV.items() if k != "AWS_REGION"}
    with pytest.raises(ValidationError, match="requires AWS region"):
        ClearcutSettings.from_environment(env)


def test_aws_profile_requires_sqs_queue_url() -> None:
    """AWS profile fails closed if SQS queue URL is missing."""
    env = {k: v for k, v in VALID_AWS_ENV.items() if k != "CLEARCUT_SQS_QUEUE_URL"}
    with pytest.raises(ValidationError, match="SQS dispatch requires queue_url"):
        ClearcutSettings.from_environment(env)


def test_aws_profile_requires_parallel_secret_arn() -> None:
    """AWS profile requires parallel_secret_arn for secrets manager."""
    env = {k: v for k, v in VALID_AWS_ENV.items() if k != "CLEARCUT_PARALLEL_SECRET_ARN"}
    with pytest.raises(ValidationError, match="requires parallel_secret_arn"):
        ClearcutSettings.from_environment(env)


def test_aws_profile_requires_bedrock_model() -> None:
    """AWS profile requires Bedrock detection model when model backend is bedrock."""
    env = {k: v for k, v in VALID_AWS_ENV.items() if k != "CLEARCUT_BEDROCK_DETECTION_MODEL"}
    with pytest.raises(ValidationError, match="requires bedrock_detection_model"):
        ClearcutSettings.from_environment(env)


def test_aws_profile_requires_cost_acknowledgement_when_bedrock_enabled() -> None:
    """Bedrock paid provider fails closed if cost is not acknowledged."""
    env = {
        **VALID_AWS_ENV,
        "CLEARCUT_PAID_PROVIDERS_ENABLED": "bedrock",
        "CLEARCUT_PAID_PROVIDER_COST_ACKNOWLEDGED": "false",
    }
    with pytest.raises(ValidationError, match="explicit cost acknowledgement"):
        ClearcutSettings.from_environment(env)


@pytest.mark.parametrize("limit", ["0", "-1", "-5"])
def test_aws_profile_requires_positive_concurrency_limit(limit: str) -> None:
    """Provider concurrency limits must be strictly positive."""
    env = {
        **VALID_AWS_ENV,
        "CLEARCUT_BEDROCK_CONCURRENCY_LIMIT": limit,
    }
    with pytest.raises(ValidationError, match="concurrency limits must be positive"):
        ClearcutSettings.from_environment(env)

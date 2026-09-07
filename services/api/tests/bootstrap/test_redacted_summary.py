from dataclasses import FrozenInstanceError

import pytest
from clearcut.bootstrap.container import (
    ApplicationContainer,
    RedactedDeploymentSummary,
    build_application,
)
from clearcut.bootstrap.settings import ClearcutSettings


def test_redacted_summary_contains_only_safe_deployment_fields() -> None:
    database_url = "postgresql+asyncpg://clearcut:super-secret@database/clearcut"
    settings = ClearcutSettings.model_validate(
        {
            "profile": "portable",
            "database": {"url": database_url},
            "storage": {
                "bucket": "clearcut-artifacts",
                "access_key_id": "secret-access-key-id",
                "secret_access_key": "secret-access-key",
            },
            "paid_providers_enabled": ["parallel", "gemini"],
            "paid_provider_cost_acknowledged": True,
        }
    )

    container = build_application(settings)

    assert isinstance(container, ApplicationContainer)
    assert container.settings is settings
    assert container.summary == RedactedDeploymentSummary(
        profile="portable",
        database_configured=True,
        storage_adapter="s3",
        dispatch_adapter="postgres",
        dispatch_enabled=True,
        authentication_adapter="builtin",
        secret_backend="host",
        paid_providers_enabled=("gemini", "parallel"),
    )
    assert "super-secret" not in repr(container.summary)
    assert "secret-access" not in repr(container.summary)
    assert set(container.summary.__dict__) == {
        "profile",
        "database_configured",
        "storage_adapter",
        "dispatch_adapter",
        "dispatch_enabled",
        "authentication_adapter",
        "secret_backend",
        "paid_providers_enabled",
    }


def test_redacted_summary_is_frozen() -> None:
    settings = ClearcutSettings.model_validate(
        {
            "profile": "local",
            "database": {"url": "sqlite+aiosqlite:////tmp/clearcut-test.db"},
            "storage": {"path": "/tmp/clearcut-storage"},
        }
    )

    summary = build_application(settings).summary

    with pytest.raises(FrozenInstanceError):
        summary.profile = "gcp"


def test_container_module_does_not_import_main() -> None:
    import clearcut.bootstrap.container as container_module

    assert "clearcut.main" not in container_module.__dict__



def test_application_container_repr_does_not_expose_settings_secrets() -> None:
    settings = ClearcutSettings.model_validate(
        {
            "profile": "portable",
            "database": {
                "url": "postgresql+asyncpg://clearcut:super-secret@database/clearcut"
            },
            "storage": {
                "bucket": "clearcut-artifacts",
                "secret_access_key": "secret-access-key",
            },
        }
    )

    container = build_application(settings)

    assert "super-secret" not in repr(container)
    assert "secret-access-key" not in repr(container)

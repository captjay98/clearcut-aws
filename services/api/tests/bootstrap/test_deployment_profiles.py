import os
import subprocess
import sys
from pathlib import Path

import pytest
from clearcut.bootstrap.settings import (
    LOCAL_SQLITE_URL,
    ClearcutSettings,
    StorageSettings,
)
from pydantic import ValidationError

LOCAL_DATABASE_URL = "sqlite+aiosqlite:////tmp/clearcut-test.db"
POSTGRES_DATABASE_URL = "postgresql+asyncpg://clearcut@database/clearcut"


def valid_settings(profile: str) -> dict[str, object]:
    if profile == "local":
        return {
            "profile": profile,
            "database": {"url": LOCAL_DATABASE_URL},
            "storage": {"path": "/tmp/clearcut-storage"},
        }
    if profile == "portable":
        return {
            "profile": profile,
            "database": {"url": POSTGRES_DATABASE_URL},
            "storage": {"bucket": "clearcut-artifacts"},
        }
    return {
        "profile": profile,
        "database": {"url": POSTGRES_DATABASE_URL},
        "storage": {
            "project_id": "clearcut-project",
            "bucket": "clearcut-artifacts",
        },
        "dispatch": {
            "project_id": "clearcut-project",
            "location": "us-central1",
            "queue": "clearcut-jobs",
            "target_url": "https://clearcut.example/api/v1/jobs/execute",
            "audience": "https://clearcut.example",
            "service_account_email": "tasks@clearcut-project.iam.gserviceaccount.com",
        },
    }


@pytest.mark.parametrize(
    ("profile", "storage", "dispatch", "auth", "secrets", "ephemeral"),
    [
        ("local", "filesystem", "local", "builtin", "environment", True),
        ("portable", "s3", "postgres", "builtin", "host", False),
        ("gcp", "gcs", "cloud_tasks", "builtin", "secret_manager", False),
    ],
)
def test_profile_defaults(
    profile: str,
    storage: str,
    dispatch: str,
    auth: str,
    secrets: str,
    ephemeral: bool,
) -> None:
    settings = ClearcutSettings.model_validate(valid_settings(profile))

    assert settings.storage.adapter == storage
    assert settings.storage.path is None or storage == "filesystem"
    assert settings.storage.ephemeral is ephemeral
    assert settings.dispatch.adapter == dispatch
    assert settings.authentication.adapter == auth
    assert settings.secrets.backend == secrets


@pytest.mark.parametrize("profile", ["portable", "gcp"])
def test_hosted_profiles_require_postgresql(profile: str) -> None:
    config = valid_settings(profile)
    config["database"] = {"url": LOCAL_DATABASE_URL}

    with pytest.raises(ValidationError, match="PostgreSQL"):
        ClearcutSettings.model_validate(config)


@pytest.mark.parametrize("profile", ["portable", "gcp"])
@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql+not-a-url",
        "postgresql+asyncpg:///clearcut",
        "postgresql+asyncpg://database",
        "postgresql+asyncpg://database:not-a-port/clearcut",
    ],
)
def test_hosted_profiles_reject_malformed_postgresql_urls(
    profile: str,
    database_url: str,
) -> None:
    config = valid_settings(profile)
    config["database"] = {"url": database_url}

    with pytest.raises(ValidationError, match="valid PostgreSQL SQLAlchemy URL"):
        ClearcutSettings.model_validate(config)


@pytest.mark.parametrize("profile", ["portable", "gcp"])
def test_hosted_profiles_reject_unsupported_postgresql_driver(profile: str) -> None:
    database_url = "postgresql+psycopg://clearcut:super-secret@database/clearcut"
    config = valid_settings(profile)
    config["database"] = {"url": database_url}

    with pytest.raises(ValidationError, match="supported PostgreSQL async driver") as exc_info:
        ClearcutSettings.model_validate(config)

    assert "super-secret" not in str(exc_info.value)


@pytest.mark.parametrize("profile", ["local", "portable", "gcp"])
def test_database_selection_is_explicit(profile: str) -> None:
    config = valid_settings(profile)
    config.pop("database")

    with pytest.raises(ValidationError, match="database"):
        ClearcutSettings.model_validate(config)


def test_hosted_profiles_reject_ephemeral_filesystem_storage() -> None:
    config = valid_settings("portable")
    config["storage"] = {
        "adapter": "filesystem",
        "path": "/tmp/ephemeral-storage",
    }

    with pytest.raises(ValidationError, match="filesystem"):
        ClearcutSettings.model_validate(config)


@pytest.mark.parametrize(
    ("profile", "storage"),
    [
        (
            "portable",
            {"adapter": "s3", "bucket": "clearcut-artifacts", "ephemeral": True},
        ),
        (
            "portable",
            {"adapter": "s3", "bucket": "clearcut-artifacts", "ephemeral": False},
        ),
        (
            "gcp",
            {
                "adapter": "gcs",
                "project_id": "clearcut-project",
                "bucket": "clearcut-artifacts",
                "ephemeral": True,
            },
        ),
        (
            "gcp",
            {
                "adapter": "gcs",
                "project_id": "clearcut-project",
                "bucket": "clearcut-artifacts",
                "ephemeral": False,
            },
        ),
    ],
)
def test_hosted_storage_rejects_explicit_filesystem_ephemeral_setting(
    profile: str,
    storage: dict[str, object],
) -> None:
    config = valid_settings(profile)
    config["storage"] = storage

    with pytest.raises(ValidationError, match="ephemeral"):
        ClearcutSettings.model_validate(config)


@pytest.mark.parametrize("adapter", ["s3", "gcs"])
@pytest.mark.parametrize("path", [None, "/tmp/contradictory"])
def test_hosted_storage_rejects_explicit_filesystem_path_at_adapter_boundary(
    adapter: str,
    path: str | None,
) -> None:
    storage: dict[str, object] = {"adapter": adapter, "path": path}
    if adapter == "s3":
        storage["bucket"] = "clearcut-artifacts"
    else:
        storage.update({
            "project_id": "clearcut-project",
            "bucket": "clearcut-artifacts",
        })

    with pytest.raises(ValidationError, match="filesystem.*path"):
        StorageSettings.model_validate(storage)


@pytest.mark.parametrize(
    ("section", "override"),
    [
        ("storage", {"adapter": "gcs", "project_id": "only-project"}),
        ("dispatch", {"adapter": "cloud_tasks", "project_id": "only-project"}),
        ("authentication", {"adapter": "firebase", "project_id": "only-project"}),
    ],
)
def test_incomplete_managed_adapter_settings_are_rejected(
    section: str,
    override: dict[str, str],
) -> None:
    config = valid_settings("gcp")
    config[section] = override

    with pytest.raises(ValidationError, match="requires"):
        ClearcutSettings.model_validate(config)


@pytest.mark.parametrize(
    ("section", "adapter"),
    [
        ("storage", "unknown-storage"),
        ("dispatch", "unknown-dispatch"),
        ("authentication", "unknown-authentication"),
        ("secrets", "unknown-secrets"),
    ],
)
def test_unknown_adapters_are_rejected(section: str, adapter: str) -> None:
    config = valid_settings("local")
    key = "backend" if section == "secrets" else "adapter"
    config[section] = {key: adapter}

    with pytest.raises(ValidationError):
        ClearcutSettings.model_validate(config)


@pytest.mark.parametrize(
    ("profile", "section", "override"),
    [
        ("local", "dispatch", {"adapter": "postgres"}),
        ("portable", "secrets", {"backend": "environment"}),
        ("gcp", "dispatch", {"adapter": "postgres"}),
    ],
)
def test_contradictory_profile_overrides_are_rejected(
    profile: str,
    section: str,
    override: dict[str, str],
) -> None:
    config = valid_settings(profile)
    config[section] = override

    with pytest.raises(ValidationError, match="profile"):
        ClearcutSettings.model_validate(config)


def test_settings_validation_is_frozen_and_does_not_create_storage_directory(
    tmp_path: Path,
) -> None:
    storage_path = tmp_path / "not-created"
    config = valid_settings("local")
    config["storage"] = {"path": storage_path}

    settings = ClearcutSettings.model_validate(config)

    assert not storage_path.exists()
    with pytest.raises(ValidationError, match="frozen"):
        settings.storage.path = tmp_path / "other"



def test_local_environment_constructor_selects_sqlite_explicitly_without_side_effects(
    tmp_path: Path,
) -> None:
    settings = ClearcutSettings.from_environment({})

    assert settings.database.url == LOCAL_SQLITE_URL
    assert settings.profile == "local"
    assert not (tmp_path / "clearcut-storage").exists()


def test_hosted_environment_does_not_inherit_local_sqlite_fallback() -> None:
    with pytest.raises(ValidationError, match="database"):
        ClearcutSettings.from_environment({"CLEARCUT_DEPLOYMENT_PROFILE": "portable"})


def test_database_module_rejects_missing_hosted_database_url(tmp_path: Path) -> None:
    environment = os.environ.copy()
    environment.pop("DATABASE_URL", None)
    environment["CLEARCUT_DEPLOYMENT_PROFILE"] = "portable"

    result = subprocess.run(
        [sys.executable, "-c", "import clearcut.database"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "DATABASE_URL" in result.stderr


def test_main_exposes_app_factory_and_preserves_global_app(tmp_path: Path) -> None:
    storage_path = tmp_path / "storage"
    environment = os.environ.copy()
    environment["CLEARCUT_DEPLOYMENT_PROFILE"] = "local"
    environment["CLEARCUT_STORAGE_PATH"] = str(storage_path)
    environment["DATABASE_URL"] = LOCAL_DATABASE_URL
    script = """
from clearcut.bootstrap.settings import ClearcutSettings
from clearcut.main import app, create_app

settings = ClearcutSettings.from_environment()
created = create_app(settings)
assert created is not app
assert created.state.settings is settings
assert app.state.settings.profile == 'local'
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr



def test_database_url_cannot_be_blank() -> None:
    config = valid_settings("local")
    config["database"] = {"url": "   "}

    with pytest.raises(ValidationError, match="url"):
        ClearcutSettings.model_validate(config)


@pytest.mark.parametrize(
    ("profile", "section", "override"),
    [
        (
            "portable",
            "storage",
            {
                "adapter": "s3",
                "bucket": "clearcut-artifacts",
                "path": "/tmp/contradictory",
            },
        ),
        (
            "gcp",
            "storage",
            {
                "adapter": "gcs",
                "project_id": "clearcut-project",
                "bucket": "clearcut-artifacts",
                "path": "/tmp/contradictory",
            },
        ),
        (
            "portable",
            "dispatch",
            {"adapter": "postgres", "queue": "contradictory-cloud-queue"},
        ),
        (
            "local",
            "authentication",
            {"adapter": "builtin", "project_id": "contradictory-firebase-project"},
        ),
    ],
)
def test_adapter_specific_fields_reject_contradictory_overrides(
    profile: str,
    section: str,
    override: dict[str, str],
) -> None:
    config = valid_settings(profile)
    config[section] = override

    with pytest.raises(ValidationError, match="does not accept"):
        ClearcutSettings.model_validate(config)



@pytest.mark.parametrize("profile", ["portable", "gcp"])
def test_database_module_rejects_hosted_sqlite_url(
    profile: str,
    tmp_path: Path,
) -> None:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = LOCAL_DATABASE_URL
    environment["CLEARCUT_DEPLOYMENT_PROFILE"] = profile

    result = subprocess.run(
        [sys.executable, "-c", "import clearcut.database"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "PostgreSQL" in result.stderr


def test_database_module_rejects_invalid_hosted_url_before_engine_construction(
    tmp_path: Path,
) -> None:
    database_url = "postgresql+not-a-url"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    environment["CLEARCUT_DEPLOYMENT_PROFILE"] = "portable"
    script = """
import sqlalchemy.ext.asyncio as sqlalchemy_asyncio


def fail_if_called(*args, **kwargs):
    raise AssertionError("engine construction attempted")


sqlalchemy_asyncio.create_async_engine = fail_if_called
import clearcut.database
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "valid PostgreSQL SQLAlchemy URL" in result.stderr
    assert "engine construction attempted" not in result.stderr
    assert database_url not in result.stderr


def test_create_app_rejects_database_settings_that_differ_from_bound_engine(
    tmp_path: Path,
) -> None:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = LOCAL_DATABASE_URL
    environment["CLEARCUT_DEPLOYMENT_PROFILE"] = "local"
    environment["CLEARCUT_STORAGE_PATH"] = str(tmp_path / "storage")
    script = """
from clearcut.bootstrap.settings import ClearcutSettings
from clearcut.main import create_app

settings = ClearcutSettings.model_validate({
    'profile': 'local',
    'database': {'url': 'sqlite+aiosqlite:////tmp/different-clearcut.db'},
    'storage': {'path': '/tmp/different-clearcut-storage'},
})
create_app(settings)
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "does not match" in result.stderr


def test_local_dispatch_rejects_multiple_api_workers(tmp_path: Path) -> None:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = LOCAL_DATABASE_URL
    environment["CLEARCUT_DEPLOYMENT_PROFILE"] = "local"
    environment["CLEARCUT_STORAGE_PATH"] = str(tmp_path / "storage")
    environment["CLEARCUT_API_WORKERS"] = "2"

    result = subprocess.run(
        [sys.executable, "-c", "import clearcut.main"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "exactly one worker" in result.stderr


def test_portable_profile_accepts_explicit_durable_filesystem_storage() -> None:
    config = valid_settings("portable")
    config["storage"] = {
        "adapter": "filesystem",
        "path": "/srv/clearcut/storage",
        "ephemeral": False,
    }

    settings = ClearcutSettings.model_validate(config)

    assert settings.storage.adapter == "filesystem"
    assert settings.storage.ephemeral is False



def test_unknown_paid_provider_name_is_rejected() -> None:
    config = valid_settings("local")
    config["paid_providers_enabled"] = ["unknown-provider"]

    with pytest.raises(ValidationError, match="paid_providers_enabled"):
        ClearcutSettings.model_validate(config)

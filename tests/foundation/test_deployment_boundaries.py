from __future__ import annotations

from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_application_startup_never_runs_database_migrations() -> None:
    dockerfile = (REPOSITORY_ROOT / "Dockerfile").read_text(encoding="utf-8")
    compose = yaml.safe_load((REPOSITORY_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]

    app_command = str(services["app"].get("command", ""))
    runtime_command = dockerfile.split("FROM python:3.12-slim AS runtime", maxsplit=1)[1]

    assert "alembic" not in app_command.lower()
    assert "alembic" not in runtime_command.lower()
    assert services["migrate"]["command"] == ["alembic", "upgrade", "head"]
    assert services["migrate"]["restart"] == "no"
    assert services["app"]["depends_on"]["migrate"]["condition"] == "service_completed_successfully"


def test_demo_seed_is_an_explicit_one_shot_service() -> None:
    compose = yaml.safe_load((REPOSITORY_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]

    assert services["seed"]["command"] == ["python", "scripts/seed_db.py"]
    assert services["seed"]["restart"] == "no"
    assert (
        services["seed"]["depends_on"]["migrate"]["condition"] == "service_completed_successfully"
    )
    assert services["app"]["depends_on"]["seed"]["condition"] == "service_completed_successfully"


def test_deploy_workflow_is_keyless_digest_pinned_and_smoke_gated() -> None:
    workflow = (REPOSITORY_ROOT / ".github/workflows/deploy.yml").read_text(encoding="utf-8")

    assert "GCP_SA_KEY" not in workflow
    assert "id-token: write" in workflow
    assert "workload_identity_provider:" in workflow
    assert "service_account:" in workflow
    assert "site_image_digest:" in workflow
    assert "web_image_digest:" in workflow
    assert "api_image_digest:" in workflow
    assert "environment: ${{ inputs.environment }}" in workflow
    assert "@sha256:" in workflow
    assert "--no-traffic" in workflow
    assert workflow.index("Candidate smoke gate") < workflow.index("Promote verified candidates")


def test_migration_workflow_executes_protected_digest_pinned_job() -> None:
    workflow = (REPOSITORY_ROOT / ".github/workflows/migrate.yml").read_text(encoding="utf-8")

    assert "GCP_SA_KEY" not in workflow
    assert "id-token: write" in workflow
    assert "workload_identity_provider:" in workflow
    assert "service_account:" in workflow
    assert "api_image_digest:" in workflow
    assert "environment: ${{ inputs.environment }}" in workflow
    assert "gcloud run jobs update" in workflow
    assert "gcloud run jobs execute" in workflow
    assert "--wait" in workflow
    assert 'run: echo "Running alembic' not in workflow


def test_cloudbuild_cannot_deploy_or_promote_the_combined_validation_image() -> None:
    config = (REPOSITORY_ROOT / "cloudbuild.yaml").read_text(encoding="utf-8")

    assert "clearcut-validation" in config
    assert "gcloud run deploy" not in config
    assert "gcloud run services update-traffic" not in config
    assert "--allow-unauthenticated" not in config
    assert "org.opencontainers.image.revision=$COMMIT_SHA" in config



def test_terraform_scaffold_requires_explicit_project_and_disclaims_apply() -> None:
    terraform = read_text("infra/gcp/environments/production/main.tf")
    infrastructure_readme = read_text("infra/gcp/README.md")

    project_variable = terraform.split('variable "project_id"', maxsplit=1)[1].split(
        "}", maxsplit=1
    )[0]
    assert "default" not in project_variable
    assert "No GCP resources are provisioned by the current scaffold" in infrastructure_readme
    assert "NO-GO" in infrastructure_readme


def read_text(relative_path: str) -> str:
    return (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")

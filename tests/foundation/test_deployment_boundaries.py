from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
GCP_INFRASTRUCTURE_ROOT = REPOSITORY_ROOT / "infra/gcp"
PRODUCTION_ROOT = GCP_INFRASTRUCTURE_ROOT / "environments/production"
MODULES_ROOT = GCP_INFRASTRUCTURE_ROOT / "modules"

REQUIRED_FOUNDATION_MODULES = (
    "state-bootstrap",
    "project-services",
    "artifact-registry",
    "network-foundation",
)
PRODUCTION_MANAGEMENT_FLAGS = (
    "manage_project_services",
    "manage_artifact_registry",
    "manage_network_foundation",
)
FORBIDDEN_TERRAFORM_PATTERNS = {
    "explicit service-account resources": r'\bresource\s+"google_service_account"',
    "service-account keys": r"\b(?:google_)?service_account_key\b",
    "explicit IAM policy, binding, or member resources": (
        r'\bresource\s+"google_[^"]*_iam_(?:policy|binding|member)"'
    ),
    "owner or editor basic roles": r"\broles/(?:owner|editor)\b",
    "public allUsers principals": r"\ballusers\b",
    "force-destroyed resources": r"\bforce_destroy\s*=\s*true\b",
    "firewall resources": r'\bresource\s+"google_[^"]*firewall[^"]*"',
    "Cloud NAT resources": r'\bresource\s+"google_compute_router_nat"',
    "load balancer forwarding rules": r'\bresource\s+"google_compute_(?:global_)?forwarding_rule"',
    "serverless VPC connectors": r'\bresource\s+"google_vpc_access_connector"',
    "explicit public routes": r'\bresource\s+"google_compute_route"',
    "import blocks": r"\bimport\s*\{",
}


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


def test_terraform_foundation_requires_explicit_project_and_disclaims_apply() -> None:
    terraform = terraform_source_under(PRODUCTION_ROOT)
    infrastructure_readme = read_text("infra/gcp/README.md")

    project_variable = terraform.split('variable "project_id"', maxsplit=1)[1].split(
        "}", maxsplit=1
    )[0]
    assert "default" not in project_variable
    assert "Four capability modules are implemented" in infrastructure_readme
    assert "manages zero resources by default" in infrastructure_readme
    assert "Existing cloud resources remain unmanaged" in infrastructure_readme
    assert "no ClearCut-authored explicit Terraform IAM resources" in infrastructure_readme
    assert "may create Google-managed service agents/default identities" in infrastructure_readme
    assert "NO-GO" in infrastructure_readme


@pytest.mark.parametrize("module_name", REQUIRED_FOUNDATION_MODULES)
def test_required_foundation_module_directory_exists(module_name: str) -> None:
    module_directory = MODULES_ROOT / module_name

    assert module_directory.is_dir(), f"Missing Terraform module directory: {module_directory}"


@pytest.mark.parametrize("variable_name", PRODUCTION_MANAGEMENT_FLAGS)
def test_production_resource_management_is_opt_in(variable_name: str) -> None:
    production_source = terraform_source_under(PRODUCTION_ROOT)
    false_default_variable = re.compile(
        rf'\bvariable\s+"{re.escape(variable_name)}"\s*\{{[^}}]*\bdefault\s*=\s*false\b',
        re.DOTALL,
    )

    assert false_default_variable.search(production_source), (
        f'Production variable "{variable_name}" must default to false'
    )


def test_authored_terraform_files_exclude_terraform_working_data(tmp_path: Path) -> None:
    authored_file = tmp_path / "main.tf"
    downloaded_file = tmp_path / "nested/.terraform/modules/vendor/main.tf"
    authored_file.write_text("# authored\n", encoding="utf-8")
    downloaded_file.parent.mkdir(parents=True)
    downloaded_file.write_text("# downloaded\n", encoding="utf-8")

    assert authored_terraform_files(tmp_path) == [authored_file]


def test_clearcut_authored_terraform_excludes_explicit_high_risk_constructs() -> None:
    terraform_files = authored_terraform_files(GCP_INFRASTRUCTURE_ROOT)

    assert terraform_files, "Expected Terraform source files under infra/gcp"
    for terraform_file in terraform_files:
        source = terraform_file.read_text(encoding="utf-8")
        for behavior, pattern in FORBIDDEN_TERRAFORM_PATTERNS.items():
            assert re.search(pattern, source, re.IGNORECASE) is None, (
                f"{terraform_file.relative_to(REPOSITORY_ROOT)} contains forbidden {behavior}"
            )


def test_state_bucket_is_protected_against_public_access_and_destroy() -> None:
    source = terraform_source_under(MODULES_ROOT / "state-bootstrap")

    assert re.search(r"\buniform_bucket_level_access\s*=\s*true\b", source)
    assert re.search(r'\bpublic_access_prevention\s*=\s*"enforced"', source)
    assert re.search(r"\bversioning\s*\{[^}]*\benabled\s*=\s*true\b", source, re.DOTALL)
    assert re.search(r"\blifecycle\s*\{[^}]*\bprevent_destroy\s*=\s*true\b", source, re.DOTALL)


def test_artifact_repositories_have_destroy_and_cleanup_guards() -> None:
    source = terraform_source_under(MODULES_ROOT / "artifact-registry")

    assert re.search(r"\blifecycle\s*\{[^}]*\bprevent_destroy\s*=\s*true\b", source, re.DOTALL)
    assert re.search(r"\bcleanup_policy_dry_run\s*=\s*true\b", source)
    assert re.search(r'\bcleanup_policies\s*\{[^}]*\baction\s*=\s*"KEEP"', source, re.DOTALL)
    assert (
        re.search(r'\bcleanup_policies\s*\{[^}]*\baction\s*=\s*"DELETE"', source, re.DOTALL) is None
    )


def test_artifact_repository_contract_requires_nonempty_descriptions() -> None:
    root_repository = terraform_variable_block(
        PRODUCTION_ROOT / "variables.tf", "artifact_repository"
    )
    module_repository = terraform_variable_block(
        MODULES_ROOT / "artifact-registry/variables.tf", "repository"
    )
    resource = (MODULES_ROOT / "artifact-registry/main.tf").read_text(encoding="utf-8")

    for repository in (root_repository, module_repository):
        assert re.search(r"\bdescription\s*=\s*string\b", repository)
        assert re.search(
            r"length\(trimspace\(var\.(?:artifact_)?repository\.description\)\)\s*>\s*0",
            repository,
        )
    assert re.search(r"\bdescription\s*=\s*var\.repository\.description\b", resource)


def test_artifact_repository_contract_is_singular() -> None:
    module_source = terraform_source_under(MODULES_ROOT / "artifact-registry")
    root_source = terraform_source_under(PRODUCTION_ROOT)

    for source, prefix in ((module_source, ""), (root_source, "artifact_")):
        assert f'output "{prefix}repository_id"' in source
        assert f'output "{prefix}repository_name"' in source
        assert f'output "{prefix}repository_ids"' not in source
        assert f'output "{prefix}repository_names"' not in source
        assert re.search(r'\brepository_id\s*==\s*"clearcut"', source)
        assert re.search(r'\b(?:moved|import)\s*\{', source) is None
    assert "var.artifact_repository" in root_source
    assert "var.artifact_repositories" not in root_source
    assert "var.repositories" not in module_source


def test_disabling_managed_state_bucket_is_blocked_by_prevent_destroy(
    tmp_path: Path,
) -> None:
    state_bootstrap_root = GCP_INFRASTRUCTURE_ROOT / "bootstrap/state"
    terraform_environment = os.environ.copy()
    terraform_environment["TF_DATA_DIR"] = str(tmp_path / "terraform-data")

    init_result = subprocess.run(
        [
            "terraform",
            "init",
            "-backend=false",
            "-input=false",
            "-no-color",
        ],
        cwd=state_bootstrap_root,
        env=terraform_environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert init_result.returncode == 0, init_result.stdout + init_result.stderr

    result = subprocess.run(
        [
            "terraform",
            "test",
            "-test-directory=lifecycle-tests",
            "-json",
            "-no-color",
        ],
        cwd=state_bootstrap_root,
        env=terraform_environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0, (
        "Disabling state-bucket management must not silently plan destruction."
    )

    events = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    diagnostics = [event["diagnostic"] for event in events if "diagnostic" in event]
    expected_resource = "module.state_bucket.google_storage_bucket.state[0]"
    assert any(
        diagnostic.get("summary") == "Instance cannot be destroyed"
        and expected_resource in diagnostic.get("detail", "")
        for diagnostic in diagnostics
    ), result.stdout + result.stderr


def test_project_services_remain_enabled_when_terraform_resources_are_removed() -> None:
    source = terraform_source_under(MODULES_ROOT / "project-services")

    assert re.search(r'\bresource\s+"google_project_service"', source)
    assert re.search(r"\bdisable_on_destroy\s*=\s*false\b", source)


def test_production_capability_modules_wait_for_project_services() -> None:
    source = (PRODUCTION_ROOT / "main.tf").read_text(encoding="utf-8")

    for module_name in ("artifact_registry", "network_foundation"):
        module_body = source.split(f'module "{module_name}"', maxsplit=1)[1].split(
            "\n}", maxsplit=1
        )[0]
        assert re.search(
            r"\bdepends_on\s*=\s*\[\s*module\.project_services\s*\]",
            module_body,
        ), f"module.{module_name} must explicitly wait for module.project_services"


def test_network_foundation_resources_all_prevent_destroy() -> None:
    source = (MODULES_ROOT / "network-foundation/main.tf").read_text(encoding="utf-8")
    resource_names = (
        "google_compute_network.network",
        "google_compute_subnetwork.subnet",
        "google_compute_global_address.private_service_range",
        "google_service_networking_connection.private_service_connection",
    )

    for index, resource_name in enumerate(resource_names):
        resource_type, local_name = resource_name.split(".", maxsplit=1)
        start = source.index(f'resource "{resource_type}" "{local_name}"')
        end = len(source)
        if index + 1 < len(resource_names):
            next_type, next_name = resource_names[index + 1].split(".", maxsplit=1)
            end = source.index(f'resource "{next_type}" "{next_name}"', start)
        resource_body = source[start:end]
        assert re.search(
            r"\blifecycle\s*\{[^}]*\bprevent_destroy\s*=\s*true\b",
            resource_body,
            re.DOTALL,
        ), f"{resource_name} must prevent destroy"


def test_disabling_managed_network_foundation_is_blocked_by_prevent_destroy(
    tmp_path: Path,
) -> None:
    terraform_environment = os.environ.copy()
    terraform_environment["TF_DATA_DIR"] = str(tmp_path / "terraform-data")

    init_result = subprocess.run(
        ["terraform", "init", "-backend=false", "-input=false", "-no-color"],
        cwd=PRODUCTION_ROOT,
        env=terraform_environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert init_result.returncode == 0, init_result.stdout + init_result.stderr

    result = subprocess.run(
        [
            "terraform",
            "test",
            "-test-directory=lifecycle-tests",
            "-json",
            "-no-color",
        ],
        cwd=PRODUCTION_ROOT,
        env=terraform_environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0, (
        "Disabling network-foundation management must not silently plan destruction."
    )
    events = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    diagnostics = [
        event["diagnostic"]
        for event in events
        if event.get("diagnostic", {}).get("summary") == "Instance cannot be destroyed"
    ]
    expected_resource = "module.network_foundation.google_compute_network.network[0]"
    assert len(diagnostics) == 1, result.stdout + result.stderr
    assert expected_resource in diagnostics[0].get("detail", ""), result.stdout + result.stderr


def test_network_foundation_preserves_default_routing_and_uses_bounded_flow_logs() -> None:
    source = terraform_source_under(MODULES_ROOT / "network-foundation")

    assert re.search(r'\bresource\s+"google_compute_network"', source)
    assert re.search(r"\bauto_create_subnetworks\s*=\s*false\b", source)
    assert "delete_default_routes_on_create" not in source
    assert re.search(r'\baggregation_interval\s*=\s*"INTERVAL_10_MIN"', source)


def test_api_routing_mode_contract_is_exact_in_root_and_module() -> None:
    expected_modes = {
        "authenticated-web-proxy",
        "deferred",
        "external-load-balancer",
    }
    variable_files = (
        PRODUCTION_ROOT / "variables.tf",
        MODULES_ROOT / "network-foundation/variables.tf",
    )

    for variable_file in variable_files:
        variable = terraform_variable_block(variable_file, "api_routing_mode")
        validation = re.search(
            r"contains\(\[(?P<modes>.*?)\],\s*var\.api_routing_mode\)",
            variable,
            re.DOTALL,
        )

        assert re.search(r'\bdefault\s*=\s*"deferred"', variable)
        assert validation is not None
        assert set(re.findall(r'"([^"]+)"', validation.group("modes"))) == expected_modes


def test_production_configuration_does_not_define_a_backend() -> None:
    production_source = terraform_source_under(PRODUCTION_ROOT)

    assert re.search(r'\bbackend\s+"', production_source) is None


def authored_terraform_files(directory: Path) -> list[Path]:
    return sorted(path for path in directory.rglob("*.tf") if ".terraform" not in path.parts)


def terraform_source_under(directory: Path) -> str:
    terraform_files = authored_terraform_files(directory)
    assert terraform_files, (
        f"Expected Terraform source files under {directory.relative_to(REPOSITORY_ROOT)}"
    )
    return "\n".join(path.read_text(encoding="utf-8") for path in terraform_files)


def terraform_variable_block(variable_file: Path, variable_name: str) -> str:
    source = variable_file.read_text(encoding="utf-8")
    variable = re.search(
        rf'^variable\s+"{re.escape(variable_name)}"\s*\{{.*?^\}}',
        source,
        re.DOTALL | re.MULTILINE,
    )
    assert variable is not None, f'Missing variable "{variable_name}" in {variable_file}'
    return variable.group(0)


def read_text(relative_path: str) -> str:
    return (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")

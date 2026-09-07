"""Offline source contracts: never execute deployment, providers, or Terraform."""

from __future__ import annotations

import copy
import json
import os
import re
import runpy
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github/workflows"
IMAGE = "europe-west1-docker.pkg.dev/test-project/releases/clearcut@sha256:" + "a" * 64


def workflow(name):
    return yaml.safe_load((WORKFLOWS / f"{name}.yml").read_text())


def job(name):
    return workflow(name)["jobs"]["publish" if name == "build" else name]


def step(name, step_id):
    matches = [s for s in job(name)["steps"] if s.get("id") == step_id]
    assert len(matches) == 1, f"Expected one {step_id} step in {name}"
    return matches[0]


def python_source(name, step_id):
    source = step(name, step_id)["run"]
    match = re.search(r"python3 - <<'PY'\n(.*?)\nPY", source, re.DOTALL)
    assert match, "Evidence validation must be an offline-testable Python block"
    return match[1]


@pytest.mark.parametrize("name", ["build", "migrate", "deploy"])
def test_release_is_main_only_protected_keyless_and_single_image(name):
    config = workflow(name)
    source = (WORKFLOWS / f"{name}.yml").read_text()
    release = job(name)
    assert "github.ref == 'refs/heads/main'" in release["if"]
    assert "github.event_name == 'workflow_dispatch'" in release["if"]
    assert release["environment"] == "${{ inputs.environment }}"
    assert release["permissions"]["id-token"] == "write"
    assert config["permissions"] == {"contents": "read"}
    assert "secrets." not in source
    assert "credentials_json" not in source
    assert "service_account_key" not in source
    assert "clearcut-api@" not in source
    assert "clearcut-site@" not in source
    assert "clearcut-web@" not in source
    auth = [s for s in release["steps"] if "google-github-actions/auth@" in s.get("uses", "")]
    assert len(auth) == 1
    assert auth[0]["with"]["create_credentials_file"] is False
    assert "workload_identity_provider" in auth[0]["with"]
    ids = [s.get("id") for s in release["steps"]]
    assert ids.index("validate_inputs") < ids.index("auth")
    for s in release["steps"]:
        assert "${{ inputs." not in s.get("run", ""), "Pass untrusted inputs via env"


def test_build_publishes_one_image_and_immutable_receipt_after_checks():
    release = job("build")
    assert release["needs"] == "verify"
    builds = [s for s in release["steps"] if "docker/build-push-action@" in s.get("uses", "")]
    assert len(builds) == 1
    assert builds[0]["with"]["push"] is True
    assert builds[0]["with"]["tags"] == "${{ steps.validate_inputs.outputs.image_tag }}"
    # Default Git context avoids adding runner credentials or untracked local data.
    assert "context" not in builds[0]["with"]
    assert "steps.image.outputs.digest" in step("build", "record_evidence")["env"]["DIGEST"]
    upload = step("build", "upload_evidence")
    assert upload["with"]["name"] == "clearcut-build-${{ github.run_id }}-${{ github.run_attempt }}"
    assert upload["with"]["if-no-files-found"] == "error"


def test_build_publication_requires_complete_provider_free_verification() -> None:
    verify = workflow("build")["jobs"]["verify"]
    source = "\n".join(step.get("run", "") for step in verify["steps"])
    actions = {step.get("uses", "") for step in verify["steps"]}

    assert any(action.startswith("astral-sh/setup-uv@") for action in actions)
    assert any(action.startswith("pnpm/action-setup@") for action in actions)
    assert any(action.startswith("oven-sh/setup-bun@") for action in actions)
    for command in (
        "pnpm install --frozen-lockfile",
        "pnpm verify",
        "uv run ruff check",
        "uv run pyright",
        "uv run pytest services/api/tests -q",
        "pnpm --filter clearcut-web test",
        "pnpm build",
    ):
        assert command in source


@pytest.mark.parametrize("name,upstream", [("migrate", "build"), ("deploy", "migrate")])
def test_evidence_is_verified_before_cloud_auth_and_bound_to_exact_run_attempt(name, upstream):
    release = job(name)
    assert release["permissions"]["actions"] == "read"
    ids = [s.get("id") for s in release["steps"]]
    assert ids.index("verify_run") < ids.index("download_evidence")
    assert ids.index("download_evidence") < ids.index("verify_evidence") < ids.index("auth")
    download = step(name, "download_evidence")["with"]
    assert download["run-id"] == "${{ env.EVIDENCE_RUN_ID }}"
    assert "steps.verify_run.outputs.attempt" in download["name"]
    assert download["github-token"] == "${{ github.token }}"
    assert upstream in step(name, "verify_run")["env"]["EXPECTED_WORKFLOW"]
    assert "always()" not in step(name, "verify_evidence").get("if", "")


def test_migration_and_deploy_share_non_cancelling_environment_lock():
    for name in ("migrate", "deploy"):
        assert workflow(name)["concurrency"] == {
            "group": "clearcut-release-${{ inputs.environment }}",
            "cancel-in-progress": False,
        }


def test_migration_records_success_only_after_waited_execution_of_same_digest():
    release = job("migrate")
    execution = step("migrate", "execute")["run"]
    assert execution.count("gcloud run jobs update") == 1
    assert execution.count("gcloud run jobs execute") == 1
    assert '--image "$IMAGE"' in execution
    assert "--wait" in execution
    assert "--command sh" in execution
    assert "python -m clearcut.bootstrap.preflight --expected-profile gcp" in execution
    assert "&& alembic upgrade head" in execution
    ids = [s.get("id") for s in release["steps"]]
    assert ids.index("execute") < ids.index("record_evidence") < ids.index("upload_evidence")
    assert step("migrate", "upload_evidence")["with"]["if-no-files-found"] == "error"
    assert "NO-GO" in (WORKFLOWS / "migrate.yml").read_text()


def test_migration_and_candidate_require_gcp_profile_preflight() -> None:
    migration = step("migrate", "execute")["run"]
    smoke = step("deploy", "smoke")["run"]

    assert "python -m clearcut.bootstrap.preflight --expected-profile gcp" in migration
    assert (
        'python3 scripts/deployment_smoke.py --url "$CANDIDATE_URL" '
        "--expected-profile gcp"
    ) in smoke


def test_smoke_requires_exact_redacted_gcp_runtime_attestation() -> None:
    smoke_module = runpy.run_path(str(ROOT / "scripts/deployment_smoke.py"))
    validate_deployment_health = smoke_module.get("validate_deployment_health")
    assert callable(validate_deployment_health), "Deployment smoke must validate runtime profile"

    local_health = {
        "status": "ok",
        "deployment": {
            "profile": "local",
            "databaseConfigured": True,
            "storageAdapter": "filesystem",
            "dispatchAdapter": "local",
            "dispatchEnabled": True,
            "authenticationAdapter": "builtin",
            "secretBackend": "environment",
        },
        "jobDispatch": {"mode": "local", "durable": False},
    }
    with pytest.raises(AssertionError, match="GCP deployment profile"):
        validate_deployment_health(local_health, expected_profile="gcp")

    gcp_health = {
        "status": "ok",
        "deployment": {
            "profile": "gcp",
            "databaseConfigured": True,
            "storageAdapter": "gcs",
            "dispatchAdapter": "cloud_tasks",
            "dispatchEnabled": True,
            "authenticationAdapter": "builtin",
            "secretBackend": "secret_manager",
        },
        "jobDispatch": {"mode": "cloud_tasks", "durable": True},
    }
    validate_deployment_health(gcp_health, expected_profile="gcp")


def test_one_candidate_smoked_at_unified_origin_before_exact_revision_promotion():
    release = job("deploy")
    source = "\n".join(s.get("run", "") for s in release["steps"])
    assert source.count("gcloud run deploy") == 1
    assert source.count("gcloud run services update-traffic") == 1
    assert 'gcloud run deploy "$SERVICE"' in source
    assert release["env"]["SERVICE"] == "clearcut"
    assert "--no-traffic" in step("deploy", "candidate")["run"]
    assert "--revision-suffix" in step("deploy", "candidate")["run"]
    assert '--image "$IMAGE"' in step("deploy", "candidate")["run"]
    smoke = step("deploy", "smoke")["run"]
    assert (
        'python3 scripts/deployment_smoke.py --url "$CANDIDATE_URL" '
        "--expected-profile gcp"
    ) in smoke
    assert "--to-revisions" in step("deploy", "promote")["run"]
    assert "--to-latest" not in source and "--to-tags" not in source
    ids = [s.get("id") for s in release["steps"]]
    assert ids.index("verify_evidence") < ids.index("candidate") < ids.index("smoke") < ids.index("promote")
    assert "always()" not in step("deploy", "promote").get("if", "")
    smoke_source = (ROOT / "scripts/deployment_smoke.py").read_text()
    assert 'method="GET"' in smoke_source
    for route in ("/app/", "/api/v1/healthz", "/api/openapi.json"):
        assert route in smoke_source
    assert not re.search(r'\b(?:POST|PUT|PATCH|DELETE)\b', smoke_source)


def evidence_environment(name, tmp_path):
    kind = "build" if name == "migrate" else "migration"
    receipt = {
        "schema_version": 1, "kind": kind, "image": IMAGE,
        "environment": "staging", "project": "test-project", "region": "europe-west1",
        "source_sha": "b" * 40, "repository": "owner/clearcut",
        "run_id": "123", "run_attempt": "2", "result": "success",
    }
    if name == "deploy":
        receipt.update(execution="clearcut-migrate-abc", build_run_id="122", build_run_attempt="1")
    env = {
        **os.environ, "IMAGE": IMAGE, "RELEASE_ENVIRONMENT": "staging",
        "GCP_PROJECT_ID": "test-project", "GCP_REGION": "europe-west1",
        "GITHUB_SHA": "b" * 40, "GITHUB_REPOSITORY": "owner/clearcut",
        "EVIDENCE_RUN_ID": "123", "EVIDENCE_RUN_ATTEMPT": "2",
        "EVIDENCE_KIND": kind, "EVIDENCE_FILE": str(tmp_path / "evidence.json"),
    }
    return receipt, env


@pytest.mark.parametrize("name", ["migrate", "deploy"])
@pytest.mark.parametrize("field", [None, "image", "environment", "project", "region", "source_sha",
                                  "repository", "run_id", "run_attempt", "result", "kind", "schema_version"])
def test_receipt_validation_accepts_exact_binding_and_rejects_substitution(name, field, tmp_path):
    receipt, env = evidence_environment(name, tmp_path)
    if field:
        receipt[field] = "wrong"
    Path(env["EVIDENCE_FILE"]).write_text(json.dumps(receipt))
    result = subprocess.run([sys.executable, "-c", python_source(name, "verify_evidence")],
                            env=env, capture_output=True, text=True, check=False)
    assert (result.returncode == 0) is (field is None), result.stderr


@pytest.mark.parametrize("field", ["execution", "build_run_id", "build_run_attempt"])
def test_deploy_rejects_missing_migration_proof(field, tmp_path):
    receipt, env = evidence_environment("deploy", tmp_path)
    receipt.pop(field)
    Path(env["EVIDENCE_FILE"]).write_text(json.dumps(receipt))
    result = subprocess.run([sys.executable, "-c", python_source("deploy", "verify_evidence")],
                            env=env, capture_output=True, text=True, check=False)
    assert result.returncode != 0


@pytest.mark.parametrize("name,upstream", [("migrate", "build"), ("deploy", "migrate")])
@pytest.mark.parametrize("mutation", [None, "conclusion", "status", "path", "head_sha", "head_branch", "event", "repository"])
def test_upstream_workflow_run_verifier_fails_closed_offline(name, upstream, mutation):
    run = {
        "id": 123, "run_attempt": 2, "status": "completed", "conclusion": "success",
        "path": f".github/workflows/{upstream}.yml", "head_sha": "b" * 40,
        "head_branch": "main", "event": "workflow_dispatch", "repository": {"full_name": "owner/clearcut"},
    }
    if mutation:
        run = copy.deepcopy(run)
        run[mutation] = {"full_name": "attacker/fork"} if mutation == "repository" else "wrong"
    # Execute only the embedded provenance verifier with a fixed local GitHub fixture.
    script = f"""
      const github = {{rest: {{actions: {{getWorkflowRun: async () => ({{data: {json.dumps(run)}}})}}}}}};
      const context = {{repo: {{owner: 'owner', repo: 'clearcut'}}, sha: '{'b' * 40}'}};
      const core = {{setOutput: () => {{}}, setFailed: () => {{process.exitCode = 1;}}}};
      (async () => {{ {step(name, 'verify_run')['with']['script']} }})().catch(() => {{process.exitCode = 1;}});
    """
    env = {**os.environ, "EVIDENCE_RUN_ID": "123", "GITHUB_SHA": "b" * 40,
           "GITHUB_REPOSITORY": "owner/clearcut", "EXPECTED_WORKFLOW": f".github/workflows/{upstream}.yml"}
    result = subprocess.run(["node", "-e", script], env=env, capture_output=True, text=True, check=False)
    assert (result.returncode == 0) is (mutation is None), result.stderr


def test_terraform_remains_explicitly_no_go_without_saved_plan_approval():
    sources = "\n".join((WORKFLOWS / f"{name}.yml").read_text() for name in ("build", "migrate", "deploy"))
    assert "Terraform plan/apply: NO-GO" in sources
    assert not re.search(r"terraform\s+(?:plan|apply)\b", sources)



def test_health_contract_requires_redacted_deployment_attestation() -> None:
    contract = yaml.safe_load((ROOT / "packages/contracts/openapi.yaml").read_text())
    schemas = contract["components"]["schemas"]
    health = schemas["HealthResponse"]
    deployment = schemas["DeploymentMetadata"]

    assert "deployment" in health["required"]
    assert health["properties"]["deployment"] == {
        "$ref": "#/components/schemas/DeploymentMetadata"
    }
    assert set(deployment["required"]) == {
        "profile",
        "databaseConfigured",
        "storageAdapter",
        "dispatchAdapter",
        "dispatchEnabled",
        "authenticationAdapter",
        "secretBackend",
        "paidProvidersEnabled",
    }

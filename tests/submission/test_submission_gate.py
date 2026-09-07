from __future__ import annotations

import json
import subprocess

import pytest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
VERIFY_SCRIPT = REPOSITORY_ROOT / "scripts" / "verify-submission.mjs"


def run_verifier(
    manifest: Path, *, readme: Path | None = None
) -> subprocess.CompletedProcess[str]:
    command = ["bun", str(VERIFY_SCRIPT), "--manifest", str(manifest)]
    if readme is not None:
        command.extend(["--readme", str(readme)])
    return subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_rejects_placeholder_revision_unsupported_monitor_and_fabricated_go(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        """
submission:
  project_name: ClearCut
  track: Parallel Track - Agentic Cinema
  license: MIT
  repository_url: https://github.com/captjay98/clearcut
  verdict: GO
  legal_boundary: ClearCut does not provide legal advice or final legal clearance.
  revision:
    git_sha: HEAD
    clean_tree: true
    remote_parity: verified
  image_digests:
    site: clearcut-site@sha256:placeholder
    web: clearcut-web@sha256:placeholder
    api: clearcut-api@sha256:placeholder
  hosted_services:
    site: https://clearcut.app
    web: https://app.clearcut.app
    api: https://api.clearcut.app
  runtime_proof:
    gemini_trace_id: placeholder
    parallel_search_id: placeholder
    parallel_extract_id: placeholder
    parallel_monitor_id: placeholder
  production_adapters:
    model_runtime: GeminiAdkRuntime
    search_adapter: ParallelSearchAdapter
    extract_adapter: ParallelExtractAdapter
    monitor_adapter: ParallelMonitorAdapter
    monitor_decision: GO
  video:
    url: https://example.com/video
    duration_seconds: 180
    visibility: public
  compliance_correspondence:
    status: verified
    reference: placeholder
  external_blockers: []
""".strip()
        + "\n",
        encoding="utf-8",
    )

    result = run_verifier(manifest)

    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "revision.git_sha must be an exact 40-character commit SHA" in output
    assert "manifest contains forbidden placeholder values" in output
    assert "Parallel Monitor must remain not-enabled" in output
    assert "GO requires independently verifiable evidence" in output


def test_accepts_truthful_no_go_with_explicit_external_blockers(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        """
submission:
  project_name: ClearCut
  track: Parallel Track - Agentic Cinema
  license: MIT
  repository_url: https://github.com/captjay98/clearcut
  verdict: NO-GO
  legal_boundary: ClearCut does not provide legal advice or final legal clearance.
  revision:
    git_sha: not-recorded-dirty-worktree
    clean_tree: false
    remote_parity: not-verified
  release:
    image_digest: not-built
    deployment_profile: gcp-starter
    migration_run_id: not-available
    cloud_run_revision: not-deployed
    service_url: null
  runtime_proof:
    gemini_trace_id: not-available
    parallel_search_id: not-available
    parallel_extract_id: not-available
    parallel_monitor_id: not-enabled
  production_adapters:
    model_runtime: not-verified
    search_adapter: not-verified
    extract_adapter: not-verified
    monitor_adapter: not-enabled
    monitor_decision: NO-GO
  video:
    status: not-recorded
    url: null
    duration_seconds: null
    visibility: not-verified
  compliance_correspondence:
    status: pending
    reference: not-available
  external_blockers:
    - id: revision-provenance
      status: blocked
      evidence_required: clean commit SHA and remote parity
""".strip()
        + "\n",
        encoding="utf-8",
    )

    result = run_verifier(manifest)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Submission manifest is truthful and internally consistent" in result.stdout



def test_rejects_readme_license_drift(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        """
submission:
  project_name: ClearCut
  track: Parallel Track - Agentic Cinema
  license: MIT
  repository_url: https://github.com/captjay98/clearcut
  verdict: NO-GO
  legal_boundary: ClearCut does not provide legal advice or final legal clearance.
  revision:
    git_sha: not-recorded-dirty-worktree
    clean_tree: false
    remote_parity: not-verified
  production_adapters:
    monitor_adapter: not-enabled
    monitor_decision: NO-GO
  runtime_proof:
    parallel_monitor_id: not-enabled
  external_blockers:
    - id: revision-provenance
      status: blocked
      evidence_required: clean commit SHA and remote parity
""".strip()
        + "\n",
        encoding="utf-8",
    )
    readme = tmp_path / "README.md"
    readme.write_text("# ClearCut\n\nLicense: Apache-2.0\n", encoding="utf-8")

    result = run_verifier(manifest, readme=readme)

    assert result.returncode != 0
    assert "README license must match the repository MIT LICENSE" in (
        result.stdout + result.stderr
    )



def test_root_verify_includes_submission_readiness_gate() -> None:
    import json

    package = json.loads((REPOSITORY_ROOT / "package.json").read_text(encoding="utf-8"))
    scripts = package["scripts"]

    assert scripts["verify:submission"] == (
        "bun scripts/verify-submission.mjs && uv run pytest tests/submission -q"
    )
    assert "pnpm verify:submission" in scripts["verify"]


def release_document(*, verdict: str = "NO-GO") -> dict:
    """Synthetic contract fixture; never deployment or provider evidence."""
    return {"submission": {
        "license": "MIT",
        "verdict": verdict,
        "legal_boundary": "ClearCut does not provide legal advice or final legal clearance.",
        "revision": {"git_sha": "a" * 40, "clean_tree": True, "remote_parity": "verified"},
        "release": {
            "image_digest": "clearcut@sha256:" + "b" * 64,
            "deployment_profile": "gcp-starter",
            "migration_run_id": "migration-run-123",
            "cloud_run_revision": "clearcut-00001-abc",
            "service_url": "https://clearcut.test",
        },
        "production_adapters": {"monitor_adapter": "not-enabled", "monitor_decision": "NO-GO"},
        "runtime_proof": {
            "gemini_trace_id": "test-gemini-run",
            "parallel_search_id": "test-search-run",
            "parallel_extract_id": "test-extract-run",
        },
        "video": {"url": "https://video.test/watch", "duration_seconds": 120, "visibility": "public"},
        "compliance_correspondence": {"status": "verified", "reference": "test-correspondence"},
        "external_blockers": [] if verdict == "GO" else [{"id": "runtime", "status": "blocked"}],
    }}


def verify_document(tmp_path: Path, document: dict) -> subprocess.CompletedProcess[str]:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(document), encoding="utf-8")
    return run_verifier(manifest)


def test_accepts_complete_single_release_contract_shape(tmp_path: Path) -> None:
    result = verify_document(tmp_path, release_document(verdict="GO"))
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("verdict", ["GO", "NO-GO"])
@pytest.mark.parametrize("legacy_key", ["image_digests", "hosted_services"])
def test_rejects_legacy_keys_even_alongside_single_release(
    tmp_path: Path, verdict: str, legacy_key: str,
) -> None:
    document = release_document(verdict=verdict)
    document["submission"][legacy_key] = {}
    result = verify_document(tmp_path, document)
    assert result.returncode != 0
    assert f"submission.{legacy_key} is a legacy key" in result.stderr


@pytest.mark.parametrize("field,value", [
    ("image_digest", "clearcut:latest"),
    ("image_digest", "clearcut-site@sha256:" + "b" * 64),
    ("image_digest", "clearcut-web@sha256:" + "b" * 64),
    ("image_digest", "clearcut-api@sha256:" + "b" * 64),
    ("image_digest", "registry.test/clearcut@sha256:" + "b" * 64),
    ("image_digest", "clearcut@sha256:" + "B" * 64),
    ("deployment_profile", "production"),
    ("migration_run_id", True),
    ("cloud_run_revision", "clearcut-api-00001-abc"),
    ("cloud_run_revision", "other-00001-abc"),
    ("service_url", "http://clearcut.test"),
    ("service_url", "https://"),
    ("service_url", "https://clearcut.test https://other.test"),
    ("service_url", ["https://clearcut.test", "https://other.test"]),
    ("service_url", "https://user:secret@clearcut.test"),
])
def test_rejects_invalid_release_values_even_for_no_go(
    tmp_path: Path, field: str, value: object,
) -> None:
    document = release_document()
    document["submission"]["release"][field] = value
    result = verify_document(tmp_path, document)
    assert result.returncode != 0
    assert f"release.{field}" in result.stderr


@pytest.mark.parametrize("field", [
    "image_digest", "deployment_profile", "migration_run_id", "cloud_run_revision", "service_url",
])
def test_requires_every_release_field(tmp_path: Path, field: str) -> None:
    document = release_document()
    del document["submission"]["release"][field]
    result = verify_document(tmp_path, document)
    assert result.returncode != 0
    assert f"release.{field}" in result.stderr


def test_rejects_additional_release_service_fields(tmp_path: Path) -> None:
    document = release_document()
    document["submission"]["release"]["api"] = "https://api.test"
    result = verify_document(tmp_path, document)
    assert result.returncode != 0
    assert "release contains unsupported keys" in result.stderr


@pytest.mark.parametrize("field,value", [
    ("image_digest", "not-built"),
    ("migration_run_id", "not-available"),
    ("cloud_run_revision", "not-deployed"),
    ("service_url", None),
])
def test_go_requires_available_release_evidence(tmp_path: Path, field: str, value: object) -> None:
    document = release_document(verdict="GO")
    document["submission"]["release"][field] = value
    result = verify_document(tmp_path, document)
    assert result.returncode != 0
    assert "GO requires independently verifiable evidence" in result.stderr


def test_real_manifest_uses_unavailable_single_release_and_cannot_be_flipped_to_go(tmp_path: Path) -> None:
    manifest = REPOSITORY_ROOT / "docs/submission/manifest.yaml"
    source = manifest.read_text(encoding="utf-8")
    assert 'verdict: "NO-GO"' in source
    assert "image_digests:" not in source
    assert "hosted_services:" not in source
    assert 'image_digest: "not-built"' in source
    assert 'deployment_profile: "gcp-starter"' in source
    assert 'migration_run_id: "not-available"' in source
    assert 'cloud_run_revision: "not-deployed"' in source
    assert "service_url: null" in source
    assert run_verifier(manifest).returncode == 0
    fabricated = tmp_path / "fabricated.yaml"
    fabricated.write_text(source.replace('verdict: "NO-GO"', 'verdict: "GO"'), encoding="utf-8")
    result = run_verifier(fabricated)
    assert result.returncode != 0
    assert "GO requires independently verifiable evidence" in result.stderr

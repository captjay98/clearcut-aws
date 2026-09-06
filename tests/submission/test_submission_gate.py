from __future__ import annotations

import subprocess
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
  image_digests:
    site: not-built
    web: not-built
    api: not-built
  hosted_services:
    site: null
    web: null
    api: null
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

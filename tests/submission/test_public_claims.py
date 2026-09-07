from __future__ import annotations

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def read(relative_path: str) -> str:
    return (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")


def test_readme_reports_truthful_local_and_release_status() -> None:
    readme = read("README.md")

    assert "Current readiness: **NO-GO**" in readme
    assert "No hosted deployment is currently verified" in readme
    assert "MIT License" in readme
    assert "a.run.app" not in readme
    assert "Apache-2.0" not in readme
    assert "$0.00 / Month" not in readme
    assert "final legal clearance" in readme


def test_submission_and_demo_copy_are_conditional_and_non_claiming() -> None:
    devpost = read("docs/submission/devpost-copy.md")
    demo_script = read("docs/submission/demo-script.md")
    runbook = read("demo/runbook.md")
    combined = "\n".join((devpost, demo_script, runbook)).lower()

    assert "submission status: draft / no-go" in devpost.lower()
    assert "live provider proof is not currently available" in runbook.lower()
    assert "do not record this scene" in runbook.lower()
    assert "dossier" not in combined
    assert "signed pdf" not in combined
    assert "90%+" not in combined
    assert "autonomous screenplay" not in combined


def test_local_launcher_does_not_claim_fallback_evidence_or_unseeded_demo() -> None:
    launcher = read("scripts/start_local.sh")

    assert "demo registry mode" not in launcher
    assert "10 items seeded" not in launcher
    assert "Missing provider credentials leave research unresolved" in launcher


def test_root_cli_fails_closed_for_unverified_cloud_deployment() -> None:
    control_script = read("clearcut")

    assert 'exec "$DIR/scripts/deploy_gcp.sh"' not in control_script
    assert "Deployment is blocked while submission readiness is NO-GO" in control_script
    assert "demo mode active" not in control_script
    assert "$0.00 / month" not in control_script
    assert "Cloud usage can incur charges" in control_script


def test_legacy_direct_deploy_script_is_disabled() -> None:
    deploy_script = read("scripts/deploy_gcp.sh")

    assert "gcloud " not in deploy_script
    assert "Deployment is blocked while submission readiness is NO-GO" in deploy_script
    assert "docs/submission/manifest.yaml" in deploy_script


def test_submission_copy_describes_one_unverified_deadline_release() -> None:
    for relative_path in ("docs/submission/devpost-copy.md", "docs/submission/limitations.md"):
        copy = read(relative_path).lower()
        assert "gcp-starter" in copy
        assert "one" in copy and "clearcut" in copy
        assert "migration" in copy
        assert "three-image" not in copy
        assert "immutable production image digests" not in copy
        assert "not" in copy and "verified" in copy


AUTHORITATIVE_DEPLOYMENT_DOCS = (
    "README.md",
    "docs/ARCHITECTURE.md",
    "docs/EXTENSIONS.md",
    "docs/SESSION_HANDOFF.md",
    "docs/plans/active/12-infrastructure-submission.md",
    "infra/gcp/README.md",
    ".agents/guide-header.md",
    ".agents/steering/agents.md",
    ".agents/steering/product-map.md",
    ".agents/steering/product.md",
    ".agents/steering/structure.md",
    ".agents/steering/tech.md",
    ".agents/steering/testing-guidelines.md",
    ".agents/memory/project-memory.md",
    ".agents/personas/devops-engineer.md",
    ".agents/includes/shared/delegation-pattern.md",
    "AGENTS.md",
)


def test_authoritative_docs_describe_one_portable_service_without_overclaiming() -> None:
    stale_claims = (
        "currently pre-implementation",
        "three separately deployable services",
        "three service images",
        "three-image",
    )

    for relative_path in AUTHORITATIVE_DEPLOYMENT_DOCS:
        copy = read(relative_path).lower()
        for stale_claim in stale_claims:
            assert stale_claim not in copy, f"{relative_path} still contains {stale_claim!r}"

    architecture = read("docs/ARCHITECTURE.md")
    assert "FastAPI is the sole public entry point" in architecture
    assert "Local, Portable Server, and GCP Starter" in architecture
    assert "Portable PostgreSQL dispatch is not yet wired" in architecture
    assert "Firebase runtime composition is not yet wired" in architecture
    assert "No hosted deployment is currently verified" in architecture

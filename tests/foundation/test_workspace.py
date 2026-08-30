from pathlib import Path
import tomllib
import json

ROOT = Path(__file__).resolve().parent.parent.parent

PROHIBITED_AI_DEPENDENCIES = {
    "langchain",
    "llama-index",
    "llamaindex",
    "openai",
    "anthropic",
    "cohere",
    "autogen",
    "crewai",
    "haystack-ai",
}

def test_required_public_governance_files_exist():
    required_files = [
        "LICENSE",
        "README.md",
        "CONTRIBUTING.md",
        "CODE_OF_CONDUCT.md",
        "SECURITY.md",
    ]
    for filename in required_files:
        path = ROOT / filename
        assert path.exists(), f"Required governance file missing: {filename}"
        assert path.stat().st_size > 0, f"Governance file is empty: {filename}"

def test_toolchain_pinning_and_manifests_exist():
    manifests = [
        ".tool-versions",
        "pyproject.toml",
        "package.json",
        "pnpm-workspace.yaml",
        "docs/adr/0001-workspace-toolchain.md",
    ]
    for manifest in manifests:
        path = ROOT / manifest
        assert path.exists(), f"Required toolchain manifest missing: {manifest}"

def test_single_lockfile_per_ecosystem():
    # Python ecosystem
    assert (ROOT / "uv.lock").exists(), "Python lockfile uv.lock is missing"
    assert not (ROOT / "poetry.lock").exists(), "Extraneous poetry.lock found"
    assert not (ROOT / "Pipfile.lock").exists(), "Extraneous Pipfile.lock found"

    # Node.js ecosystem
    assert (ROOT / "pnpm-lock.yaml").exists(), "TypeScript lockfile pnpm-lock.yaml is missing"
    assert not (ROOT / "package-lock.json").exists(), "Extraneous package-lock.json found"
    assert not (ROOT / "yarn.lock").exists(), "Extraneous yarn.lock found"

def test_no_prohibited_ai_dependencies():
    pyproject_path = ROOT / "pyproject.toml"
    if pyproject_path.exists():
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
        deps = set(data.get("project", {}).get("dependencies", []))
        optional_deps = data.get("project", {}).get("optional-dependencies", {})
        for group in optional_deps.values():
            deps.update(group)
        dep_names = {d.split()[0].split("=")[0].split(">")[0].split("<")[0].lower() for d in deps}
        prohibited_found = dep_names.intersection(PROHIBITED_AI_DEPENDENCIES)
        assert not prohibited_found, f"Prohibited AI dependencies found in pyproject.toml: {prohibited_found}"

    package_json_path = ROOT / "package.json"
    if package_json_path.exists():
        with open(package_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        js_deps = set(data.get("dependencies", {}).keys()).union(data.get("devDependencies", {}).keys())
        prohibited_found_js = js_deps.intersection(PROHIBITED_AI_DEPENDENCIES)
        assert not prohibited_found_js, f"Prohibited AI dependencies found in package.json: {prohibited_found_js}"

def test_workspace_roots_and_definitions():
    pnpm_ws_path = ROOT / "pnpm-workspace.yaml"
    assert pnpm_ws_path.exists(), "pnpm-workspace.yaml missing"
    content = pnpm_ws_path.read_text()
    assert "apps/*" in content, "pnpm-workspace.yaml must include apps/*"
    assert "packages/*" in content, "pnpm-workspace.yaml must include packages/*"

    pyproject_path = ROOT / "pyproject.toml"
    assert pyproject_path.exists(), "pyproject.toml missing"
    with open(pyproject_path, "rb") as f:
        py_data = tomllib.load(f)
    members = py_data.get("tool", {}).get("uv", {}).get("workspace", {}).get("members", [])
    assert "services/api" in members or "services/*" in members, "pyproject.toml must include services in uv workspace members"

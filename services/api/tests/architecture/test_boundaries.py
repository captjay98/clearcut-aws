import ast
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
API_SRC = ROOT / "services" / "api" / "src" / "clearcut"

FORBIDDEN_DOMAIN_IMPORTS = {
    "fastapi",
    "sqlalchemy",
    "google",
    "parallel",
    "requests",
    "httpx",
}


def scan_module_imports(directory: Path) -> set[str]:
    imports = set()
    if not directory.exists():
        return imports
    for path in directory.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.add(alias.name.split(".")[0])
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module.split(".")[0])
        except Exception:
            pass
    return imports


def test_domain_has_no_framework_or_provider_imports():
    assert API_SRC.exists(), f"API source root missing: {API_SRC}"
    # Only scan domain subpackages
    domain_dirs = list(API_SRC.glob("*/domain"))
    for d_dir in domain_dirs:
        found_imports = scan_module_imports(d_dir)
        forbidden_found = found_imports.intersection(FORBIDDEN_DOMAIN_IMPORTS)
        assert not forbidden_found, (
            f"Forbidden framework/provider imports in {d_dir}: {forbidden_found}"
        )


def test_adapter_registry_exists_and_uses_explicit_registration():
    from clearcut.bootstrap.adapter_registry import AdapterRegistry

    registry = AdapterRegistry()
    assert hasattr(registry, "register_storage"), "AdapterRegistry missing register_storage"
    assert hasattr(registry, "register_identity"), "AdapterRegistry missing register_identity"
    assert hasattr(registry, "register_search"), "AdapterRegistry missing register_search"
    assert hasattr(registry, "register_ai"), "AdapterRegistry missing register_ai"
    assert hasattr(registry, "is_frozen"), "AdapterRegistry missing is_frozen method"


def test_feature_coverage_script_passes():
    script_path = ROOT / "scripts" / "check-feature-coverage.mjs"
    assert script_path.exists(), f"Missing {script_path}"
    res = subprocess.run(["node", str(script_path)], capture_output=True, text=True)
    assert res.returncode == 0, f"Feature coverage check failed:\n{res.stdout}\n{res.stderr}"


def test_rescan_application_and_ports_have_no_sqlalchemy_or_adapter_imports():
    """The rescan orchestration layer coordinates carry-forward through typed
    module ports only. Its ports/ and application/ packages must not import
    SQLAlchemy (persistence belongs to owning-module adapters) nor any other
    module's adapters package (modules never read each other's storage).
    """
    rescan_dirs = [
        API_SRC / "rescan" / "ports",
        API_SRC / "rescan" / "application",
    ]
    for rescan_dir in rescan_dirs:
        assert rescan_dir.exists(), f"Missing rescan package: {rescan_dir}"

    forbidden_top_level = {"sqlalchemy"}
    for rescan_dir in rescan_dirs:
        found = scan_module_imports(rescan_dir)
        assert not found.intersection(forbidden_top_level), (
            f"rescan orchestration layer must not import SQLAlchemy: "
            f"{found.intersection(forbidden_top_level)} in {rescan_dir}"
        )

    # No import of any other module's adapters package.
    for rescan_dir in rescan_dirs:
        if not rescan_dir.exists():
            continue
        for path in rescan_dir.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                module_name = None
                if isinstance(node, ast.ImportFrom) and node.module:
                    module_name = node.module
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if ".adapters" in alias.name:
                            module_name = alias.name
                if module_name and module_name.startswith("clearcut."):
                    assert ".adapters" not in module_name, (
                        f"rescan orchestration must not import module adapters: "
                        f"{module_name} in {path}"
                    )

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
WEB_SRC = ROOT / "apps" / "web" / "src"

PROHIBITED = {
    "runtime import": 'import "./runtime.js"',
    "hash routing": "window.location.hash",
    "test fixture import": "tests/fixtures",
    "domain local storage": "clearcut-flow-state",
}


def test_no_legacy_runtime_file():
    runtime_js = WEB_SRC / "runtime.js"
    assert not runtime_js.exists(), "apps/web/src/runtime.js must not exist in production tree"


def test_no_prohibited_runtime_patterns_in_web_source():
    assert WEB_SRC.exists(), "apps/web/src directory must exist"
    
    source_files = list(WEB_SRC.rglob("*.ts")) + list(WEB_SRC.rglob("*.tsx")) + list(WEB_SRC.rglob("*.js"))
    assert len(source_files) > 0, "Expected web source files to scan"

    violations = []
    for file_path in source_files:
        content = file_path.read_text(encoding="utf-8")
        rel_path = file_path.relative_to(ROOT)
        
        if "runtime.js" in content:
            violations.append(f"{rel_path}: references runtime.js")
            
        for name, pattern in PROHIBITED.items():
            if pattern in content:
                violations.append(f"{rel_path}: prohibited pattern '{name}' ({pattern})")

    assert not violations, "Found prohibited legacy runtime patterns in web source:\n" + "\n".join(violations)

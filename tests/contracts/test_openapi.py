from pathlib import Path
import yaml
import json

ROOT = Path(__file__).resolve().parent.parent.parent
OPENAPI_PATH = ROOT / "packages" / "contracts" / "openapi.yaml"

def test_openapi_file_exists_and_is_valid_yaml():
    assert OPENAPI_PATH.exists(), f"Missing openapi.yaml at {OPENAPI_PATH}"
    with open(OPENAPI_PATH, "r", encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    assert isinstance(spec, dict), "OpenAPI spec must be a dictionary"
    assert spec.get("openapi", "").startswith("3."), f"Expected OpenAPI 3.x, got {spec.get('openapi')}"
    assert "info" in spec, "OpenAPI spec missing info section"
    assert spec["info"].get("title") == "ClearCut API"

def test_openapi_contains_canonical_run_status():
    with open(OPENAPI_PATH, "r", encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    schemas = spec.get("components", {}).get("schemas", {})
    assert "RunStatus" in schemas, "components.schemas.RunStatus is required"
    run_status_enum = schemas["RunStatus"].get("enum", [])
    expected_statuses = [
        "queued",
        "claimed",
        "running",
        "retry_wait",
        "succeeded",
        "failed",
        "manual_retry",
        "cancelled",
    ]
    assert run_status_enum == expected_statuses, f"RunStatus enum mismatch: {run_status_enum}"
    assert "completed" not in run_status_enum, "'completed' must not be in API RunStatus (use 'succeeded')"

def test_openapi_error_envelope_schema():
    with open(OPENAPI_PATH, "r", encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    schemas = spec.get("components", {}).get("schemas", {})
    assert "ErrorEnvelope" in schemas, "ErrorEnvelope schema is required"
    err_props = schemas["ErrorEnvelope"].get("properties", {})
    assert "error" in err_props, "ErrorEnvelope must have 'error' property"

def test_openapi_uuidv7_definition():
    with open(OPENAPI_PATH, "r", encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    schemas = spec.get("components", {}).get("schemas", {})
    assert "UUIDv7" in schemas, "UUIDv7 schema is required"
    assert schemas["UUIDv7"].get("type") == "string"
    assert "pattern" in schemas["UUIDv7"]

def test_standalone_schemas_exist_and_are_valid():
    error_json = ROOT / "packages" / "contracts" / "schemas" / "error.json"
    event_json = ROOT / "packages" / "contracts" / "schemas" / "events" / "envelope.v1.json"
    
    assert error_json.exists(), f"Missing {error_json}"
    with open(error_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("$schema"), "error.json missing $schema"
    
    assert event_json.exists(), f"Missing {event_json}"
    with open(event_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("$schema"), "envelope.v1.json missing $schema"

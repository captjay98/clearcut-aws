from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
OPENAPI_PATH = ROOT / "packages" / "contracts" / "openapi.yaml"

def test_operations_have_valid_operation_ids():
    assert OPENAPI_PATH.exists(), f"Missing openapi.yaml at {OPENAPI_PATH}"
    with open(OPENAPI_PATH, "r", encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    
    paths = spec.get("paths", {})
    assert paths, "OpenAPI spec must define paths"
    
    operation_ids = set()
    for path_key, path_item in paths.items():
        for method in ["get", "post", "put", "delete", "patch"]:
            if method in path_item:
                op = path_item[method]
                op_id = op.get("operationId")
                assert op_id, f"Missing operationId for {method.upper()} {path_key}"
                assert op_id not in operation_ids, f"Duplicate operationId: {op_id}"
                operation_ids.add(op_id)
                
                # Check response defined
                assert "responses" in op, f"Missing responses for {op_id}"
                assert "200" in op["responses"] or "201" in op["responses"] or "202" in op["responses"] or "204" in op["responses"], f"Missing success status for {op_id}"

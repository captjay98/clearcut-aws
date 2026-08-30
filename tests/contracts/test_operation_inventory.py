from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
OPENAPI_PATH = ROOT / "packages" / "contracts" / "openapi.yaml"


def test_operations_have_valid_operation_ids():
    assert OPENAPI_PATH.exists(), f"Missing openapi.yaml at {OPENAPI_PATH}"
    with open(OPENAPI_PATH, encoding="utf-8") as f:
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

                assert "responses" in op, f"Missing responses for {op_id}"
                valid_statuses = {"200", "201", "202", "204"}
                has_valid_success = any(status in op["responses"] for status in valid_statuses)
                assert has_valid_success, f"Missing success status for {op_id}"

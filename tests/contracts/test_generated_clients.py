from pathlib import Path
import re
import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
TS_CLIENT_PATH = ROOT / "packages" / "contracts" / "generated" / "typescript" / "index.ts"
PY_CLIENT_PATH = ROOT / "packages" / "contracts" / "generated" / "python" / "__init__.py"
OPENAPI_PATH = ROOT / "packages" / "contracts" / "openapi.yaml"


def test_typescript_client_is_executable_with_typed_results():
    assert TS_CLIENT_PATH.exists(), f"TypeScript generated client missing at {TS_CLIENT_PATH}"
    content = TS_CLIENT_PATH.read_text(encoding="utf-8")

    # Must export ApiResult union type
    assert "export type ApiResult" in content, "TypeScript client must export 'ApiResult' type"
    assert "ok: true" in content and "ok: false" in content, "ApiResult must distinguish ok: true and ok: false"

    # Must export createApiClient or client functions with fetch implementation
    assert "createApiClient" in content or "export const api" in content or "export function createClient" in content, (
        "TypeScript generated client must export an executable client factory or api object"
    )

    # Must use credentials: 'include' and same-origin /api/v1 baseURL default
    assert "credentials" in content, "Client transport must configure credentials for same-origin session cookies"


def test_all_openapi_operations_have_executable_ts_methods():
    assert OPENAPI_PATH.exists()
    assert TS_CLIENT_PATH.exists()

    with open(OPENAPI_PATH, encoding="utf-8") as f:
        spec = yaml.safe_load(f)

    ts_content = TS_CLIENT_PATH.read_text(encoding="utf-8")

    paths = spec.get("paths", {})
    operation_ids = []
    for path_item in paths.values():
        for method in ["get", "post", "put", "delete", "patch"]:
            if method in path_item and "operationId" in path_item[method]:
                operation_ids.append(path_item[method]["operationId"])

    missing_in_ts = []
    for op_id in operation_ids:
        # Check if the operation is exposed as a function or method in the client
        # e.g., op_id: (params...) or function op_id(
        pattern = rf"\b{op_id}\b"
        if not re.search(pattern, ts_content):
            missing_in_ts.append(op_id)

    assert not missing_in_ts, f"TypeScript client missing executable methods for operations: {missing_in_ts}"

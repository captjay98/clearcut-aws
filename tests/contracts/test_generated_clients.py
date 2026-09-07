import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
import yaml
from pydantic import BaseModel, TypeAdapter, ValidationError

ROOT = Path(__file__).resolve().parent.parent.parent
TS_CLIENT_PATH = ROOT / "packages" / "contracts" / "generated" / "typescript" / "index.ts"
PY_CLIENT_PATH = ROOT / "packages" / "contracts" / "generated" / "python" / "__init__.py"
OPENAPI_PATH = ROOT / "packages" / "contracts" / "openapi.yaml"

GENERATED_PYTHON_SPEC = importlib.util.spec_from_file_location(
    "clearcut_generated_contracts",
    PY_CLIENT_PATH,
)
assert GENERATED_PYTHON_SPEC is not None
assert GENERATED_PYTHON_SPEC.loader is not None
GENERATED_PYTHON = importlib.util.module_from_spec(GENERATED_PYTHON_SPEC)
sys.modules[GENERATED_PYTHON_SPEC.name] = GENERATED_PYTHON
GENERATED_PYTHON_SPEC.loader.exec_module(GENERATED_PYTHON)
ParseRun = GENERATED_PYTHON.ParseRun
ParseWarning = GENERATED_PYTHON.ParseWarning
ProjectScriptScene = GENERATED_PYTHON.ProjectScriptScene
ScriptVersion = GENERATED_PYTHON.ScriptVersion


def test_typescript_client_is_executable_with_typed_results():
    assert TS_CLIENT_PATH.exists(), f"TypeScript generated client missing at {TS_CLIENT_PATH}"
    content = TS_CLIENT_PATH.read_text(encoding="utf-8")

    # Must export ApiResult union type
    assert "export type ApiResult" in content, "TypeScript client must export 'ApiResult' type"
    assert "ok: true" in content and "ok: false" in content, (
        "ApiResult must distinguish ok: true and ok: false"
    )

    # Must export createApiClient or client functions with fetch implementation
    assert (
        "createApiClient" in content
        or "export const api" in content
        or "export function createClient" in content
    ), "TypeScript generated client must export an executable client factory or api object"

    # Must use credentials: 'include' and same-origin /api/v1 baseURL default
    assert "credentials" in content, (
        "Client transport must configure credentials for same-origin session cookies"
    )


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

    assert not missing_in_ts, (
        f"TypeScript client missing executable methods for operations: {missing_in_ts}"
    )


def test_generated_clients_expose_authoritative_clearance_item_detail() -> None:
    typescript = TS_CLIENT_PATH.read_text(encoding="utf-8")
    assert "export interface ClearanceItemDetail" in typescript
    assert "evidenceState: ItemEvidenceState;" in typescript
    assert "comments: Array<ItemDetailComment>;" in typescript

    assert hasattr(GENERATED_PYTHON, "ClearanceItemDetail")
    detail_model = GENERATED_PYTHON.ClearanceItemDetail
    assert {
        "itemId",
        "version",
        "evidenceState",
        "comments",
        "capabilities",
    } <= set(detail_model.model_fields)


def test_generated_typescript_client_usage_compiles():
    result = subprocess.run(
        [
            "pnpm",
            "--filter",
            "clearcut-web",
            "exec",
            "tsc",
            "--project",
            "../../tests/contracts/tsconfig.json",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_generated_typescript_request_runtime() -> None:
    result = subprocess.run(
        [
            "pnpm",
            "--filter",
            "clearcut-web",
            "exec",
            "vitest",
            "run",
            "--root",
            "../..",
            "tests/contracts/fixtures/generated-client-runtime.test.ts",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_request_helper_template_has_no_trailing_whitespace() -> None:
    paths = [ROOT / "scripts" / "generate-clients.mjs", TS_CLIENT_PATH]
    violations = [
        f"{path.relative_to(ROOT)}:{line_number}"
        for path in paths
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        )
        if line.rstrip() != line
    ]

    assert not violations, "Trailing whitespace:\n" + "\n".join(violations)


def test_contract_drift_check_does_not_modify_generated_files(tmp_path: Path) -> None:
    temporary_contracts = tmp_path / "packages" / "contracts"
    temporary_ts_path = temporary_contracts / "generated" / "typescript" / "index.ts"
    temporary_py_path = temporary_contracts / "generated" / "python" / "__init__.py"
    temporary_ts_path.parent.mkdir(parents=True)
    temporary_py_path.parent.mkdir(parents=True)
    (temporary_contracts / "openapi.yaml").write_bytes(OPENAPI_PATH.read_bytes())
    temporary_ts_path.write_bytes(TS_CLIENT_PATH.read_bytes())
    temporary_py_path.write_bytes(PY_CLIENT_PATH.read_bytes())

    tracked_before = (TS_CLIENT_PATH.read_bytes(), PY_CLIENT_PATH.read_bytes())
    drifted = temporary_ts_path.read_text(encoding="utf-8") + (
        "\n// intentional contract drift fixture\n"
    )
    temporary_ts_path.write_text(drifted, encoding="utf-8")

    result = subprocess.run(
        ["bun", str(ROOT / "scripts" / "check-contract-drift.mjs")],
        cwd=ROOT,
        capture_output=True,
        check=False,
        env={**os.environ, "CLEARCUT_CONTRACT_ROOT": str(tmp_path)},
        text=True,
    )

    assert result.returncode != 0, result.stdout + result.stderr
    assert temporary_ts_path.read_text(encoding="utf-8") == drifted
    assert (TS_CLIENT_PATH.read_bytes(), PY_CLIENT_PATH.read_bytes()) == tracked_before


def test_web_generated_client_calls_use_params_and_unwrapped_values():
    source_root = ROOT / "apps" / "web" / "src"
    violations: list[str] = []
    for source_path in source_root.rglob("*.tsx"):
        content = source_path.read_text(encoding="utf-8")
        if "api." not in content:
            continue
        for line_number, line in enumerate(content.splitlines(), start=1):
            if re.search(r"\bpath\s*:", line) or ".value.data" in line:
                violations.append(f"{source_path.relative_to(ROOT)}:{line_number}: {line.strip()}")

    assert not violations, "Generated client convention drift:\n" + "\n".join(violations)


def test_report_route_has_no_synthetic_release_success():
    report_route = (
        ROOT
        / "apps"
        / "web"
        / "src"
        / "routes"
        / "o"
        / "$orgSlug"
        / "projects"
        / "$projectId"
        / "report.tsx"
    ).read_text(encoding="utf-8")

    assert "snap-001" not in report_route
    assert "8f49a88cd72b9a714e8248c871587391" not in report_route
    assert 'status: "released", isReleased: true' not in report_route
    assert "keep default fallback" not in report_route
    assert "Immutable Clearance Release Receipt" not in report_route


def test_report_contract_exposes_frozen_bindings_release_and_artifact_metadata():
    spec = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    schemas = spec["components"]["schemas"]

    assert set(schemas["ReportSnapshot"]["required"]) >= {
        "snapshotId",
        "projectId",
        "versionId",
        "generatedAt",
        "status",
        "contentHash",
        "bindingManifest",
        "artifactId",
    }
    assert set(schemas["ReportRelease"]["required"]) >= {
        "releaseId",
        "snapshotId",
        "releasedBy",
        "releasedAt",
        "attestation",
        "contentHash",
        "artifactId",
        "downloadUrl",
    }
    assert "ReportHistoryEntry" in schemas
    assert "ReportArtifactMetadata" in schemas

    paths = spec["paths"]
    history_schema = paths[
        "/api/v1/organizations/{orgId}/projects/{projectId}/report-history"
    ]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert history_schema["properties"]["data"]["items"] == {
        "$ref": "#/components/schemas/ReportHistoryEntry"
    }
    metadata_schema = paths[
        "/api/v1/organizations/{orgId}/projects/{projectId}/report-releases/"
        "{releaseId}/artifact-metadata"
    ]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert metadata_schema["properties"]["data"] == {
        "$ref": "#/components/schemas/ReportArtifactMetadata"
    }

    release_operation = paths[
        "/api/v1/organizations/{orgId}/projects/{projectId}/report-snapshots/"
        "{snapshotId}:release"
    ]["post"]
    attestation = release_operation["requestBody"]["content"]["application/json"][
        "schema"
    ]["properties"]["attestation"]
    assert attestation["minLength"] == 40
    assert attestation["maxLength"] == 2000

    implemented_operations = (
        paths["/api/v1/organizations/{orgId}/projects/{projectId}/report-preview"]["get"],
        paths["/api/v1/organizations/{orgId}/projects/{projectId}/report-snapshots"]["post"],
        release_operation,
        paths["/api/v1/organizations/{orgId}/projects/{projectId}/report-history"]["get"],
        paths[
            "/api/v1/organizations/{orgId}/projects/{projectId}/report-releases/"
            "{releaseId}/artifact-metadata"
        ]["get"],
    )
    assert all("503" not in operation["responses"] for operation in implemented_operations)

    typescript = TS_CLIENT_PATH.read_text(encoding="utf-8")
    assert "export interface ReportHistoryEntry" in typescript
    assert "export interface ReportArtifactMetadata" in typescript
    snapshot_declaration = re.search(
        r"export interface ReportSnapshot \{(?P<body>.*?)\n\}",
        typescript,
        re.DOTALL,
    )
    release_declaration = re.search(
        r"export interface ReportRelease \{(?P<body>.*?)\n\}",
        typescript,
        re.DOTALL,
    )
    assert snapshot_declaration is not None
    assert release_declaration is not None
    assert "contentHash: string;" in snapshot_declaration.group("body")
    assert "bindingManifest: Record<string, unknown>;" in snapshot_declaration.group("body")
    assert "artifactId: UUIDv7;" in snapshot_declaration.group("body")
    assert "attestation: string;" in release_declaration.group("body")
    assert "contentHash: string;" in release_declaration.group("body")
    assert "artifactId: UUIDv7;" in release_declaration.group("body")
    assert "downloadUrl: string;" in release_declaration.group("body")


def test_canonical_script_reads_have_no_seeded_ui_fallbacks():
    source_paths = [
        ROOT
        / "apps"
        / "web"
        / "src"
        / "routes"
        / "o"
        / "$orgSlug"
        / "projects"
        / "$projectId"
        / "versions.tsx",
        ROOT
        / "apps"
        / "web"
        / "src"
        / "routes"
        / "o"
        / "$orgSlug"
        / "projects"
        / "$projectId"
        / "workspace.tsx",
        ROOT / "apps" / "web" / "src" / "features" / "scripts" / "ScreenplayViewer.tsx",
    ]
    forbidden = (
        "Borrowed Light",
        "Vega Camera",
        "Blue Monday",
        "ver-001",
        "keep default",
        "provide default canonical screenplay scenes",
    )

    violations = [
        f"{source_path.relative_to(ROOT)} contains {value!r}"
        for source_path in source_paths
        for value in forbidden
        if value in source_path.read_text(encoding="utf-8")
    ]
    assert not violations, "Seeded canonical-read fallbacks:\n" + "\n".join(violations)


def test_trust_and_records_preserve_unavailable_states():
    trust_route = (
        ROOT / "apps" / "web" / "src" / "routes" / "o" / "$orgSlug" / "trust.tsx"
    ).read_text(encoding="utf-8")
    records_route = (
        ROOT / "apps" / "web" / "src" / "routes" / "o" / "$orgSlug" / "records.tsx"
    ).read_text(encoding="utf-8")

    for seeded_component in (
        "RubricVisualizer",
        "ProtectedConfigCard",
        "LearningCandidateTable",
    ):
        assert seeded_component not in trust_route
    assert "capability is not available" in trust_route
    assert "result.error.message" in records_route
    assert "setError" in records_route


def test_finalize_import_contract_and_client_use_typed_multipart():
    spec = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    operation = spec["paths"][
        "/api/v1/organizations/{orgId}/projects/{projectId}/import-artifacts/{artifactId}:finalize"
    ]["post"]

    multipart = operation["requestBody"]["content"]["multipart/form-data"]["schema"]
    assert multipart["required"] == ["file"]
    assert multipart["properties"]["file"] == {"type": "string", "format": "binary"}
    assert any(
        parameter.get("name") == "X-Upload-Nonce"
        and parameter.get("in") == "header"
        and parameter.get("required") is True
        for parameter in operation["parameters"]
    )

    generated = TS_CLIENT_PATH.read_text(encoding="utf-8")
    assert "body: { file: Blob }" in generated
    assert 'headers: { "X-Upload-Nonce": string } & Record<string, string>' in generated
    assert "new FormData()" in generated
    assert "bodyMediaType: 'multipart/form-data'" in generated


@pytest.mark.parametrize(
    ("schema_name", "model", "field_name", "payload"),
    [
        (
            "ParseWarning",
            ParseWarning,
            "line",
            {"code": "malformed_heading", "message": "Heading needs review."},
        ),
        (
            "ParseRun",
            ParseRun,
            "acceptedAt",
            {
                "runId": "01900000-0000-7000-8000-000000000001",
                "artifactId": "01900000-0000-7000-8000-000000000002",
                "status": "succeeded",
                "parserName": "fountain",
                "parserVersion": "1.0.0",
                "warnings": [],
                "sceneCount": 1,
                "elementCount": 2,
                "warningsAccepted": False,
                "createdAt": "2026-09-02T00:00:00Z",
                "completedAt": "2026-09-02T00:00:01Z",
            },
        ),
        (
            "ScriptVersion",
            ScriptVersion,
            "sourceArtifactId",
            {
                "versionId": "01900000-0000-7000-8000-000000000003",
                "scriptId": "01900000-0000-7000-8000-000000000004",
                "projectId": "01900000-0000-7000-8000-000000000005",
                "versionNumber": 1,
                "revisionLabel": "v1",
                "title": "Signal Fires",
                "ordinal": 1,
                "parseRunId": None,
                "sourceHash": "abc123",
                "parserVersion": "1.0.0",
                "sceneCount": 1,
                "elementCount": 2,
                "createdAt": "2026-09-02T00:00:00Z",
            },
        ),
        (
            "ScriptVersion",
            ScriptVersion,
            "parseRunId",
            {
                "versionId": "01900000-0000-7000-8000-000000000003",
                "scriptId": "01900000-0000-7000-8000-000000000004",
                "projectId": "01900000-0000-7000-8000-000000000005",
                "versionNumber": 1,
                "revisionLabel": "v1",
                "title": "Signal Fires",
                "ordinal": 1,
                "sourceArtifactId": None,
                "sourceHash": "abc123",
                "parserVersion": "1.0.0",
                "sceneCount": 1,
                "elementCount": 2,
                "createdAt": "2026-09-02T00:00:00Z",
            },
        ),
        (
            "ProjectScriptScene",
            ProjectScriptScene,
            "page",
            {"number": 1, "slug": "EXT. ROOFTOP - DAWN", "lines": []},
        ),
    ],
)
def test_python_required_nullable_fields_require_explicit_null(
    schema_name: str,
    model: type[BaseModel],
    field_name: str,
    payload: dict[str, object],
) -> None:
    spec = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    assert field_name in spec["components"]["schemas"][schema_name]["required"]
    assert model.model_fields[field_name].is_required()

    with pytest.raises(ValidationError):
        model.model_validate(payload)

    validated = model.model_validate({**payload, field_name: None})
    assert getattr(validated, field_name) is None


def test_observable_job_contract_exposes_safe_lifecycle_and_attempt_history() -> None:
    spec = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    schemas = spec["components"]["schemas"]
    job = schemas["Job"]
    assert set(job["required"]) == {
        "jobId",
        "status",
        "jobType",
        "target",
        "canRetry",
        "progress",
        "stage",
        "resultSummary",
        "error",
        "attemptCount",
        "attempts",
        "history",
        "availableAt",
        "createdAt",
        "updatedAt",
    }
    assert job["properties"]["target"] == {"$ref": "#/components/schemas/JobTarget"}
    assert schemas["JobTarget"]["properties"]["type"]["enum"] == [
        "project",
        "script_version",
        "clearance_item",
        "legacy_unknown",
    ]
    assert job["properties"]["canRetry"] == {"type": "boolean"}
    assert job["properties"]["error"]["anyOf"] == [
        {"$ref": "#/components/schemas/SafeJobError"},
        {"type": "null"},
    ]
    assert job["properties"]["attempts"]["items"] == {"$ref": "#/components/schemas/JobAttempt"}
    assert job["properties"]["history"]["items"] == {
        "$ref": "#/components/schemas/JobLifecycleEvent"
    }
    health = schemas["HealthResponse"]
    assert "jobDispatch" in health["required"]
    assert health["properties"]["jobDispatch"] == {
        "$ref": "#/components/schemas/JobDispatchMetadata"
    }

    typescript = TS_CLIENT_PATH.read_text(encoding="utf-8")
    assert "export interface JobTarget" in typescript
    assert "target: JobTarget" in typescript
    assert "canRetry: boolean" in typescript
    assert "export interface SafeJobError" in typescript
    assert "export interface JobAttempt" in typescript
    assert "export interface JobLifecycleEvent" in typescript
    assert "export interface DeploymentMetadata" in typescript
    assert "deployment: DeploymentMetadata" in typescript
    assert "resultSummary: Record<string, unknown> | null" in typescript
    assert "attempts: JobAttempt[]" in typescript
    assert "history: JobLifecycleEvent[]" in typescript

    python = PY_CLIENT_PATH.read_text(encoding="utf-8")
    assert "class JobTarget(BaseModel):" in python
    assert "target: JobTarget" in python
    assert "canRetry: bool" in python
    assert "class SafeJobError(BaseModel):" in python
    assert "class JobAttempt(BaseModel):" in python
    assert "class JobLifecycleEvent(BaseModel):" in python
    assert "class DeploymentMetadata(BaseModel):" in python
    assert "deployment: DeploymentMetadata" in python
    assert "resultSummary: Optional[Dict[str, Any]]" in python
    assert "attempts: List[JobAttempt]" in python
    assert "history: List[JobLifecycleEvent]" in python


def test_project_contract_exposes_canonical_production_details() -> None:
    spec = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    schemas = spec["components"]["schemas"]
    fields = {
        "productionType",
        "productionStage",
        "jurisdiction",
        "targetLockDate",
        "reviewBrief",
    }
    assert fields <= set(schemas["Project"]["required"])
    assert fields <= set(schemas["Project"]["properties"])
    assert fields <= set(schemas["CreateProjectRequest"]["properties"])
    assert schemas["Project"]["properties"]["targetLockDate"]["anyOf"][0] == {
        "type": "string",
        "format": "date",
    }

    typescript = TS_CLIENT_PATH.read_text(encoding="utf-8")
    for declaration in (
        "productionType: string | null",
        "productionStage: string | null",
        "jurisdiction: string | null",
        "targetLockDate: string | null",
        "reviewBrief: string | null",
    ):
        assert declaration in typescript

    python = PY_CLIENT_PATH.read_text(encoding="utf-8")
    for field in (
        "productionType",
        "productionStage",
        "jurisdiction",
        "targetLockDate",
        "reviewBrief",
    ):
        assert f"{field}: Optional[" in python


def test_job_list_contract_exposes_bounded_cursor_pagination() -> None:
    spec = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    operation = spec["paths"]["/api/v1/organizations/{orgId}/projects/{projectId}/jobs"]["get"]
    parameters = {
        parameter["name"]: parameter for parameter in operation["parameters"] if "name" in parameter
    }

    assert parameters["limit"] == {
        "name": "limit",
        "in": "query",
        "required": False,
        "schema": {
            "type": "integer",
            "minimum": 1,
            "maximum": 100,
            "default": 50,
        },
    }
    assert parameters["cursor"] == {
        "name": "cursor",
        "in": "query",
        "required": False,
        "schema": {"$ref": "#/components/schemas/UUIDv7"},
    }

    generated = TS_CLIENT_PATH.read_text(encoding="utf-8")
    list_jobs = generated.split("listJobs: async", maxsplit=1)[1].split(
        "/** Get job status", maxsplit=1
    )[0]
    assert "query?: { limit?: number; cursor?: UUIDv7 }" in list_jobs
    assert "query: args?.query" in list_jobs

    uuid7_adapter = TypeAdapter(GENERATED_PYTHON.UUIDv7)
    canonical = "0190abcd-abcd-7abc-8abc-abcdefabcdef"
    assert uuid7_adapter.validate_python(canonical) == canonical
    for invalid in (str(uuid4()), canonical.upper()):
        with pytest.raises(ValidationError):
            uuid7_adapter.validate_python(invalid)



TASK_10_COMMAND_PATHS = {
    "recordEvidenceDecision": "/api/v1/organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}:recordEvidenceDecision",
    "setDisposition": "/api/v1/organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}:setDisposition",
    "referClearanceItem": "/api/v1/organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}:refer",
    "acknowledgeReferral": "/api/v1/organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}/referrals/{referralId}:acknowledge",
    "assignClearanceItem": "/api/v1/organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}:assign",
    "addComment": "/api/v1/organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}/comments",
    "replyToComment": "/api/v1/organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}/comments/{commentId}:reply",
    "reviseComment": "/api/v1/organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}/comments/{commentId}:revise",
}
TASK_10_GOVERNED_OPERATIONS = {
    "recordEvidenceDecision",
    "setDisposition",
    "referClearanceItem",
    "acknowledgeReferral",
}


def _resolve_contract_ref(document: dict, node: dict) -> dict:
    if "$ref" not in node:
        return node
    resolved: object = document
    for part in node["$ref"].removeprefix("#/").split("/"):
        assert isinstance(resolved, dict)
        resolved = resolved[part]
    assert isinstance(resolved, dict)
    return resolved


def _task_10_operations(document: dict) -> dict[str, dict]:
    operations: dict[str, dict] = {}
    for path, path_item in document["paths"].items():
        for method in ("get", "post", "put", "delete", "patch"):
            operation = path_item.get(method)
            if operation and operation.get("operationId") in TASK_10_COMMAND_PATHS:
                operation_id = operation["operationId"]
                assert operation_id not in operations
                operations[operation_id] = {"path": path, "operation": operation}
    return operations


def _generate_mutated_contracts(
    document: dict, tmp_path: Path
) -> tuple[subprocess.CompletedProcess[str], Path]:
    temporary_contracts = tmp_path / "packages" / "contracts"
    temporary_contracts.mkdir(parents=True)
    (temporary_contracts / "openapi.yaml").write_text(
        yaml.safe_dump(document, sort_keys=False),
        encoding="utf-8",
    )
    generated_root = tmp_path / "generated"
    result = subprocess.run(
        ["node", str(ROOT / "scripts" / "generate-clients.mjs")],
        cwd=tmp_path,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "CLEARCUT_CONTRACT_ROOT": str(tmp_path),
            "CLEARCUT_GENERATED_ROOT": str(generated_root),
        },
        text=True,
    )
    return result, generated_root


def test_task_10_commands_use_canonical_item_scoped_paths() -> None:
    document = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    operations = _task_10_operations(document)

    assert set(operations) == set(TASK_10_COMMAND_PATHS)
    assert {
        operation_id: entry["path"] for operation_id, entry in operations.items()
    } == TASK_10_COMMAND_PATHS


def test_task_10_commands_require_version_intent_and_idempotency() -> None:
    document = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    operations = _task_10_operations(document)

    for operation_id, entry in operations.items():
        operation = entry["operation"]
        idempotency_parameter = next(
            (
                resolved
                for parameter in operation.get("parameters", [])
                if (resolved := _resolve_contract_ref(document, parameter)).get("name")
                == "Idempotency-Key"
            ),
            None,
        )
        assert idempotency_parameter is not None, (
            f"{operation_id} must declare Idempotency-Key"
        )
        assert idempotency_parameter["required"] is True

        request_schema = _resolve_contract_ref(
            document,
            operation["requestBody"]["content"]["application/json"]["schema"],
        )
        required = set(request_schema.get("required", []))
        assert {"expectedVersion", "intentHash"} <= required, operation_id
        if operation_id in TASK_10_GOVERNED_OPERATIONS:
            assert "rationale" in required, operation_id


def test_task_10_vocabularies_preserve_the_legal_boundary() -> None:
    document = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    schemas = document["components"]["schemas"]

    assert schemas["EvidenceDecision"]["enum"] == [
        "accepted",
        "rejected",
        "further_review_required",
    ]
    assert "not a legal-clearance conclusion" in schemas["EvidenceDecision"][
        "description"
    ].lower()
    assert schemas["ClearanceDisposition"]["enum"] == [
        "pending",
        "verified",
        "ruled_out",
        "fixed_in_rewrite",
        "deferred",
    ]


def test_task_10_commands_define_typed_errors_and_resulting_item_versions() -> None:
    document = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    operations = _task_10_operations(document)

    for operation_id, entry in operations.items():
        responses = entry["operation"]["responses"]
        assert {"403", "404", "409", "422"} <= set(responses), operation_id
        for status in ("403", "404", "409", "422"):
            schema = responses[status]["content"]["application/json"]["schema"]
            assert schema == {"$ref": "#/components/schemas/ErrorEnvelope"}, (
                operation_id,
                status,
            )
        assert "stale" in responses["409"]["description"].lower()
        assert "idempotency" in responses["409"]["description"].lower()

        success_status = next(
            status for status in responses if status.startswith("2")
        )
        envelope = responses[success_status]["content"]["application/json"]["schema"]
        data_schema = _resolve_contract_ref(
            document,
            envelope["properties"]["data"],
        )
        required = set(data_schema.get("required", []))
        version_field = "version" if operation_id in {
            "recordEvidenceDecision",
            "setDisposition",
            "assignClearanceItem",
        } else "itemVersion"
        assert version_field in required, operation_id

    error_codes = document["components"]["schemas"]["ErrorEnvelope"]["properties"][
        "error"
    ]["properties"]["code"]["enum"]
    assert "conflict_stale_version" in error_codes
    assert "conflict_idempotency_mismatch" in error_codes


def test_task_10_generation_classifies_changed_enum_by_shape(tmp_path: Path) -> None:
    document = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    document["components"]["schemas"]["AssignClearanceItemRequest"] = {
        "type": "string",
        "enum": ["human", "unassigned"],
    }

    result, generated_root = _generate_mutated_contracts(document, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    typescript = (generated_root / "typescript" / "index.ts").read_text(
        encoding="utf-8"
    )
    python = (generated_root / "python" / "__init__.py").read_text(encoding="utf-8")
    assert "export type AssignClearanceItemRequest = 'human' | 'unassigned';" in typescript
    assert 'AssignClearanceItemRequest = Literal["human", "unassigned"]' in python
    assert "class AssignClearanceItemRequest(BaseModel):" not in python


def test_task_10_generation_includes_newly_referenced_component(tmp_path: Path) -> None:
    document = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    schemas = document["components"]["schemas"]
    schemas["Task10CommandContext"] = {
        "type": "object",
        "additionalProperties": False,
        "required": ["label"],
        "properties": {"label": {"type": "string", "minLength": 1}},
    }
    assign = schemas["AssignClearanceItemRequest"]
    assign["required"].append("commandContext")
    assign["properties"]["commandContext"] = {
        "$ref": "#/components/schemas/Task10CommandContext"
    }

    result, generated_root = _generate_mutated_contracts(document, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    typescript = (generated_root / "typescript" / "index.ts").read_text(
        encoding="utf-8"
    )
    python = (generated_root / "python" / "__init__.py").read_text(encoding="utf-8")
    assert "export interface Task10CommandContext" in typescript
    assert "commandContext: Task10CommandContext;" in typescript
    assert "class Task10CommandContext(BaseModel):" in python
    assert "commandContext: Task10CommandContext" in python


def test_task_10_generation_has_deduplicated_dependency_order(tmp_path: Path) -> None:
    document = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    schemas = document["components"]["schemas"]
    schemas["Task10SharedContext"] = {
        "type": "object",
        "properties": {"note": {"type": "string"}},
    }
    shared_ref = {"$ref": "#/components/schemas/Task10SharedContext"}
    schemas["AssignClearanceItemRequest"]["properties"]["sharedContext"] = shared_ref
    schemas["RecordEvidenceDecisionRequest"]["properties"]["sharedContext"] = shared_ref

    result, generated_root = _generate_mutated_contracts(document, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    typescript = (generated_root / "typescript" / "index.ts").read_text(
        encoding="utf-8"
    )
    python = (generated_root / "python" / "__init__.py").read_text(encoding="utf-8")
    expected_order = [
        "Task10SharedContext",
        "AssignClearanceItemRequest",
        "EvidenceDecision",
        "RecordEvidenceDecisionRequest",
        "ClearanceDisposition",
        "SetDispositionRequest",
        "ReferClearanceItemRequest",
        "AcknowledgeReferralRequest",
        "AddCommentRequest",
        "ReplyToCommentRequest",
        "ReviseCommentRequest",
    ]
    for content, declaration_patterns in (
        (typescript, ("export interface {name}", "export type {name} =")),
        (python, ("class {name}(BaseModel):", "{name} =")),
    ):
        declaration_positions: list[int] = []
        for name in expected_order:
            matches = [
                content.count(pattern.format(name=name))
                for pattern in declaration_patterns
            ]
            assert sum(matches) == 1, (name, matches)
            declaration_positions.append(
                min(
                    position
                    for pattern in declaration_patterns
                    if (position := content.find(pattern.format(name=name))) >= 0
                )
            )
        assert declaration_positions == sorted(declaration_positions)


def test_generation_failure_preserves_all_existing_outputs(tmp_path: Path) -> None:
    document = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    document["components"]["schemas"]["EvidenceDecision"]["enum"].append(
        "escalated_for_review"
    )
    del document["components"]["schemas"]["UUIDv7"]["pattern"]
    temporary_contracts = tmp_path / "packages" / "contracts"
    temporary_contracts.mkdir(parents=True)
    (temporary_contracts / "openapi.yaml").write_text(
        yaml.safe_dump(document, sort_keys=False),
        encoding="utf-8",
    )
    generated_root = tmp_path / "generated"
    temporary_ts_path = generated_root / "typescript" / "index.ts"
    temporary_py_path = generated_root / "python" / "__init__.py"
    temporary_ts_path.parent.mkdir(parents=True)
    temporary_py_path.parent.mkdir(parents=True)
    temporary_ts_path.write_text("existing TypeScript output\n", encoding="utf-8")
    temporary_py_path.write_text("existing Python output\n", encoding="utf-8")
    temporary_before = (
        temporary_ts_path.read_bytes(),
        temporary_py_path.read_bytes(),
    )
    tracked_before = (TS_CLIENT_PATH.read_bytes(), PY_CLIENT_PATH.read_bytes())

    result = subprocess.run(
        ["node", str(ROOT / "scripts" / "generate-clients.mjs")],
        cwd=tmp_path,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "CLEARCUT_CONTRACT_ROOT": str(tmp_path),
            "CLEARCUT_GENERATED_ROOT": str(generated_root),
        },
        text=True,
    )

    assert result.returncode != 0, result.stdout + result.stderr
    assert "UUIDv7 schema pattern is required" in result.stderr
    assert (temporary_ts_path.read_bytes(), temporary_py_path.read_bytes()) == (
        temporary_before
    )
    assert (TS_CLIENT_PATH.read_bytes(), PY_CLIENT_PATH.read_bytes()) == tracked_before


def test_task_10_generation_rejects_predeclared_name_collision(tmp_path: Path) -> None:
    document = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    document["components"]["schemas"]["AssignClearanceItemRequest"]["properties"][
        "project"
    ] = {"$ref": "#/components/schemas/Project"}

    result, generated_root = _generate_mutated_contracts(document, tmp_path)

    assert result.returncode != 0, result.stdout + result.stderr
    assert "Task 10 schema Project collides with predeclared name" in result.stderr
    assert not (generated_root / "typescript" / "index.ts").exists()
    assert not (generated_root / "python" / "__init__.py").exists()


def test_task_10_generation_derives_models_from_openapi(tmp_path: Path) -> None:
    document = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    schemas = document["components"]["schemas"]
    request_schema = schemas["AssignClearanceItemRequest"]
    request_schema["required"].remove("intentHash")
    request_schema["properties"]["expectedVersion"]["minimum"] = 7
    request_schema["properties"]["intentHash"]["minLength"] = 5
    request_schema["properties"]["externalReference"] = {
        "type": "string",
        "minLength": 7,
        "maxLength": 31,
    }
    idempotency_parameter = document["components"]["parameters"][
        "RequiredIdempotencyKey"
    ]
    idempotency_parameter["required"] = False
    idempotency_schema = idempotency_parameter["schema"]
    idempotency_schema["minLength"] = 23
    idempotency_schema["maxLength"] = 29

    temporary_contracts = tmp_path / "packages" / "contracts"
    temporary_contracts.mkdir(parents=True)
    (temporary_contracts / "openapi.yaml").write_text(
        yaml.safe_dump(document, sort_keys=False),
        encoding="utf-8",
    )
    generated_root = tmp_path / "generated"
    result = subprocess.run(
        ["node", str(ROOT / "scripts" / "generate-clients.mjs")],
        cwd=tmp_path,
        capture_output=True,
        check=False,
        env={**os.environ, "CLEARCUT_GENERATED_ROOT": str(generated_root)},
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    typescript = (generated_root / "typescript" / "index.ts").read_text(
        encoding="utf-8"
    )
    request_declaration = typescript.split(
        "export interface AssignClearanceItemRequest", maxsplit=1
    )[1].split("}\n", maxsplit=1)[0]
    assert "externalReference?: string;" in request_declaration
    assert "intentHash?: string;" in request_declaration
    assert "expectedVersion: number;" in request_declaration
    assign_operation = typescript.split("assignClearanceItem: async", maxsplit=1)[1].split(
        "/** Record an evidence decision", maxsplit=1
    )[0]
    assert 'headers?: { "Idempotency-Key"?: string }' in assign_operation

    generated_python_path = generated_root / "python" / "__init__.py"
    module_spec = importlib.util.spec_from_file_location(
        "clearcut_generated_mutated_task_10_contracts",
        generated_python_path,
    )
    assert module_spec is not None
    assert module_spec.loader is not None
    generated_python = importlib.util.module_from_spec(module_spec)
    sys.modules[module_spec.name] = generated_python
    module_spec.loader.exec_module(generated_python)

    request_model = generated_python.AssignClearanceItemRequest
    assert request_model.model_fields["externalReference"].is_required() is False
    assert request_model.model_fields["intentHash"].is_required() is False
    valid_payload = {
        "assigneeId": "01900000-0000-7000-8000-000000000001",
        "expectedVersion": 7,
    }
    request_model.model_validate(valid_payload)
    with pytest.raises(ValidationError):
        request_model.model_validate({**valid_payload, "expectedVersion": 6})
    with pytest.raises(ValidationError):
        request_model.model_validate({**valid_payload, "intentHash": "four"})
    with pytest.raises(ValidationError):
        request_model.model_validate({**valid_payload, "externalReference": "short"})
    with pytest.raises(ValidationError):
        request_model.model_validate({**valid_payload, "unexpected": True})

    comment_model = generated_python.AddCommentRequest
    mention = "01900000-0000-7000-8000-000000000002"
    with pytest.raises(ValidationError):
        comment_model.model_validate(
            {
                "body": "Review this source.",
                "mentions": [mention, mention],
                "expectedVersion": 7,
                "intentHash": "intent",
            }
        )

    header_model = generated_python.IdempotentCommandHeaders
    assert header_model.model_fields["idempotencyKey"].is_required() is False
    header_model.model_validate({})
    header_model.model_validate({"Idempotency-Key": "x" * 23})
    with pytest.raises(ValidationError):
        header_model.model_validate({"Idempotency-Key": "x" * 22})
    with pytest.raises(ValidationError):
        header_model.model_validate({"Idempotency-Key": "x" * 30})


def test_task_10_generation_derives_selected_success_and_error_models(
    tmp_path: Path,
) -> None:
    document = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    schemas = document["components"]["schemas"]
    schemas["Task10AssignmentResult"] = {
        "type": "object",
        "additionalProperties": False,
        "required": ["item", "responseRevision"],
        "properties": {
            "item": {"$ref": "#/components/schemas/ClearanceItem"},
            "responseRevision": {"type": "string", "minLength": 8},
        },
    }
    schemas["ClearanceItem"]["properties"]["version"]["minimum"] = 9

    operations = _task_10_operations(document)
    assign_responses = operations["assignClearanceItem"]["operation"]["responses"]
    assign_success = assign_responses["200"]["content"]["application/json"]["schema"]
    assign_success["properties"]["data"] = {
        "$ref": "#/components/schemas/Task10AssignmentResult"
    }

    error_schema = schemas["ErrorEnvelope"]["properties"]["error"]
    error_schema["required"].append("supportReference")
    error_schema["properties"]["supportReference"] = {
        "type": "string",
        "minLength": 5,
    }
    error_schema["properties"]["code"]["enum"].append("policy_review_required")

    result, generated_root = _generate_mutated_contracts(document, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    typescript = (generated_root / "typescript" / "index.ts").read_text(
        encoding="utf-8"
    )
    assert "export interface Task10AssignmentResult" in typescript
    assert "responseRevision: string;" in typescript
    assign_operation = typescript.split("assignClearanceItem: async", maxsplit=1)[
        1
    ].split("/** Record an evidence decision", maxsplit=1)[0]
    assert "Promise<ApiResult<Task10AssignmentResult>>" in assign_operation
    api_error = typescript.split("export interface ApiError", maxsplit=1)[1].split(
        "}\n", maxsplit=1
    )[0]
    assert "'policy_review_required'" in api_error
    assert "supportReference: string;" in api_error
    assert typescript.count("export interface ClearanceItem {") == 1
    assert typescript.count("export interface ErrorEnvelope") == 1

    generated_python_path = generated_root / "python" / "__init__.py"
    module_spec = importlib.util.spec_from_file_location(
        "clearcut_generated_mutated_task_10_response_contracts",
        generated_python_path,
    )
    assert module_spec is not None
    assert module_spec.loader is not None
    generated_python = importlib.util.module_from_spec(module_spec)
    sys.modules[module_spec.name] = generated_python
    module_spec.loader.exec_module(generated_python)

    assignment_model = generated_python.Task10AssignmentResult
    with pytest.raises(ValidationError):
        assignment_model.model_validate(
            {
                "item": {
                    "itemId": "01900000-0000-7000-8000-000000000001",
                    "projectId": "01900000-0000-7000-8000-000000000002",
                    "version": 8,
                    "category": "names",
                    "entityName": "Example",
                    "status": "review",
                },
                "responseRevision": "revision-1",
            }
        )
    assignment_model.model_validate(
        {
            "item": {
                "itemId": "01900000-0000-7000-8000-000000000001",
                "projectId": "01900000-0000-7000-8000-000000000002",
                "version": 9,
                "category": "names",
                "entityName": "Example",
                "status": "review",
            },
            "responseRevision": "revision-1",
        }
    )

    error_model = generated_python.ErrorPayload
    error_model.model_validate(
        {
            "code": "policy_review_required",
            "message": "Human policy review is required.",
            "requestId": "request-1",
            "retryable": False,
            "supportReference": "ref-1",
        }
    )
    with pytest.raises(ValidationError):
        error_model.model_validate(
            {
                "code": "policy_review_required",
                "message": "Human policy review is required.",
                "requestId": "request-1",
                "retryable": False,
                "supportReference": "tiny",
            }
        )


def test_task_10_generated_python_models_expose_command_headers_and_bodies() -> None:
    header_model = GENERATED_PYTHON.IdempotentCommandHeaders
    headers = header_model.model_validate(
        {"Idempotency-Key": "task-10-key-0001"}
    )
    assert headers.idempotencyKey == "task-10-key-0001"

    for model_name in (
        "AssignClearanceItemRequest",
        "RecordEvidenceDecisionRequest",
        "SetDispositionRequest",
        "ReferClearanceItemRequest",
        "AcknowledgeReferralRequest",
        "AddCommentRequest",
        "ReplyToCommentRequest",
        "ReviseCommentRequest",
    ):
        model = getattr(GENERATED_PYTHON, model_name)
        assert model.model_fields["expectedVersion"].is_required(), model_name
        assert model.model_fields["intentHash"].is_required(), model_name


def test_task_10_generated_typescript_usage_compiles() -> None:
    result = subprocess.run(
        [
            "pnpm",
            "--filter",
            "clearcut-web",
            "exec",
            "tsc",
            "--noEmit",
            "--strict",
            "--target",
            "ES2022",
            "--module",
            "ESNext",
            "--moduleResolution",
            "Bundler",
            "--lib",
            "ES2022,DOM",
            "../../tests/contracts/fixtures/task-10-generated-client-usage.ts",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr

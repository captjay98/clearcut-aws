"""Canonical OpenAPI and mounted FastAPI operation parity for the local vertical slice."""

from pathlib import Path
from uuid import uuid4

import pytest
import uuid6
import yaml
from clearcut.collaboration.delivery.http import (
    AddCommentBody,
    ReplyToCommentBody,
    ReviseCommentBody,
)
from clearcut.init_db import init_and_seed_db
from clearcut.main import app
from httpx import ASGITransport, AsyncClient

ROOT = Path(__file__).resolve().parents[2]
OPENAPI_PATH = ROOT / "packages" / "contracts" / "openapi.yaml"
HTTP_METHODS = ("get", "post", "put", "delete", "patch")

REQUIRED_OPERATIONS = {
    # Identity and organization entry.
    "registerUser": ("post", "/api/v1/users"),
    "createSession": ("post", "/api/v1/sessions"),
    "getSessionContext": ("get", "/api/v1/session-context"),
    "deleteCurrentSession": ("delete", "/api/v1/sessions/current"),
    "listOrganizations": ("get", "/api/v1/organizations"),
    "createOrganization": ("post", "/api/v1/organizations"),
    "resolveOrganizationEntry": ("get", "/api/v1/organization-entry"),
    "listProjects": ("get", "/api/v1/organizations/{orgId}/projects"),
    "createProject": ("post", "/api/v1/organizations/{orgId}/projects"),
    "getProject": ("get", "/api/v1/organizations/{orgId}/projects/{projectId}"),
    # Script import, versioning, detection, and research.
    "getProjectScript": (
        "get",
        "/api/v1/organizations/{orgId}/projects/{projectId}/script",
    ),
    "createUploadCapability": (
        "post",
        "/api/v1/organizations/{orgId}/projects/{projectId}/upload-capabilities",
    ),
    "finalizeImportArtifact": (
        "post",
        "/api/v1/organizations/{orgId}/projects/{projectId}/import-artifacts/{artifactId}:finalize",
    ),
    "createPasteImport": (
        "post",
        "/api/v1/organizations/{orgId}/projects/{projectId}/paste-imports",
    ),
    "parseImportArtifact": (
        "post",
        "/api/v1/organizations/{orgId}/projects/{projectId}/import-artifacts/{artifactId}:parse",
    ),
    "acceptParseWarnings": (
        "post",
        "/api/v1/organizations/{orgId}/projects/{projectId}/parse-runs/{runId}:acceptWarnings",
    ),
    "commitScriptVersion": (
        "post",
        "/api/v1/organizations/{orgId}/projects/{projectId}/parse-runs/{runId}:commitVersion",
    ),
    "listProjectVersions": (
        "get",
        "/api/v1/organizations/{orgId}/projects/{projectId}/script-versions",
    ),
    "getProjectVersion": (
        "get",
        "/api/v1/organizations/{orgId}/projects/{projectId}/script-versions/{versionId}",
    ),
    "getScriptVersionDiff": (
        "get",
        "/api/v1/organizations/{orgId}/projects/{projectId}/script-versions/{versionId}/diff",
    ),
    "startSelectiveRescan": (
        "post",
        "/api/v1/organizations/{orgId}/projects/{projectId}/script-versions/{versionId}:startSelectiveRescan",
    ),
    "startDetection": (
        "post",
        "/api/v1/organizations/{orgId}/projects/{projectId}/script-versions/{versionId}:detect",
    ),
    "listClearanceItems": (
        "get",
        "/api/v1/organizations/{orgId}/projects/{projectId}/clearance-items",
    ),
    "getClearanceItem": (
        "get",
        "/api/v1/organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}",
    ),
    "startResearch": (
        "post",
        "/api/v1/organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}:research",
    ),
    # Governed collaboration commands.
    "addComment": (
        "post",
        "/api/v1/organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}/comments",
    ),
    "replyToComment": (
        "post",
        "/api/v1/organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}/comments/{commentId}:reply",
    ),
    "reviseComment": (
        "post",
        "/api/v1/organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}/comments/{commentId}:revise",
    ),
    # Observable jobs.
    "listJobs": ("get", "/api/v1/organizations/{orgId}/projects/{projectId}/jobs"),
    "getJob": (
        "get",
        "/api/v1/organizations/{orgId}/projects/{projectId}/jobs/{jobId}",
    ),
    "retryJob": (
        "post",
        "/api/v1/organizations/{orgId}/projects/{projectId}/jobs/{jobId}:retry",
    ),
    "cancelJob": (
        "post",
        "/api/v1/organizations/{orgId}/projects/{projectId}/jobs/{jobId}:cancel",
    ),
    # Persisted Trust evaluations.
    "listTrustEvaluations": (
        "get",
        "/api/v1/organizations/{orgId}/projects/{projectId}/evaluations",
    ),
    "getTrustEvaluation": (
        "get",
        "/api/v1/organizations/{orgId}/projects/{projectId}/evaluations/{evaluationId}",
    ),
    # Authoritative Records ledger.
    "listRecords": ("get", "/api/v1/organizations/{orgId}/records"),
    "getRecord": ("get", "/api/v1/organizations/{orgId}/records/{recordId}"),
    "getProviderAttempt": (
        "get",
        "/api/v1/organizations/{orgId}/provider-attempts/{attemptId}",
    ),
    # Governed reports and receipt history.
    "previewReport": (
        "get",
        "/api/v1/organizations/{orgId}/projects/{projectId}/report-preview",
    ),
    "generateReportSnapshot": (
        "post",
        "/api/v1/organizations/{orgId}/projects/{projectId}/report-snapshots",
    ),
    "releaseReport": (
        "post",
        "/api/v1/organizations/{orgId}/projects/{projectId}/report-snapshots/{snapshotId}:release",
    ),
    "listReportHistory": (
        "get",
        "/api/v1/organizations/{orgId}/projects/{projectId}/report-history",
    ),
    "getReportDownloadMetadata": (
        "get",
        "/api/v1/organizations/{orgId}/projects/{projectId}/report-releases/{releaseId}/artifact-metadata",
    ),
}

# The selective rescan route (startSelectiveRescan) is now mounted in the running
# FastAPI app, so it is held to strict mounted parity below. The revision-diff
# route (getScriptVersionDiff) is canonical in packages/contracts/openapi.yaml
# (asserted by the OpenAPI inventory test above) but is implemented and mounted by
# a separate revision-diff task, not this selective-rescan task. Its mount is
# tolerated here only; every other operation — including startSelectiveRescan —
# stays strict. Remove this entry once the diff route is mounted.
PENDING_MOUNT_OPERATIONS = {
    "getScriptVersionDiff",
}


def _load_spec() -> dict:
    with OPENAPI_PATH.open(encoding="utf-8") as source:
        return yaml.safe_load(source)


def _openapi_inventory(spec: dict) -> dict[str, tuple[str, str]]:
    inventory: dict[str, tuple[str, str]] = {}
    for path, path_item in spec["paths"].items():
        for method in HTTP_METHODS:
            operation = path_item.get(method)
            if operation is None:
                continue
            operation_id = operation.get("operationId")
            assert operation_id, f"Missing operationId for {method.upper()} {path}"
            assert operation_id not in inventory, f"Duplicate OpenAPI operationId: {operation_id}"
            inventory[operation_id] = (method, path)
    return inventory


def _mounted_inventory() -> dict[str, tuple[str, str]]:
    inventory: dict[str, tuple[str, str]] = {}
    for path, path_item in app.openapi()["paths"].items():
        if not path.startswith("/api/v1/"):
            continue
        for method in HTTP_METHODS:
            operation = path_item.get(method)
            if operation is None:
                continue
            operation_id = operation["operationId"]
            assert operation_id not in inventory, f"Duplicate mounted operation_id: {operation_id}"
            inventory[operation_id] = (method, path)
    return inventory


def test_canonical_openapi_contains_exact_vertical_slice_inventory() -> None:
    inventory = _openapi_inventory(_load_spec())

    missing = set(REQUIRED_OPERATIONS) - set(inventory)
    mismatched = {
        operation_id: {"expected": expected, "actual": inventory.get(operation_id)}
        for operation_id, expected in REQUIRED_OPERATIONS.items()
        if inventory.get(operation_id) != expected
    }

    assert not missing, f"Canonical OpenAPI is missing operations: {sorted(missing)}"
    assert not mismatched, f"Canonical OpenAPI method/path drift: {mismatched}"


def test_get_clearance_item_uses_authoritative_detail_schema() -> None:
    path = "/api/v1/organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}"
    source = _load_spec()
    source_data = source["paths"][path]["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ]["properties"]["data"]
    assert source_data == {"$ref": "#/components/schemas/ClearanceItemDetail"}

    detail = source["components"]["schemas"]["ClearanceItemDetail"]
    assert set(detail["required"]) >= {
        "itemId",
        "projectId",
        "versionId",
        "version",
        "evidenceState",
        "claims",
        "snapshots",
        "conflicts",
        "decisions",
        "referrals",
        "comments",
        "capabilities",
    }
    assert detail["properties"]["comments"]["items"] == {
        "$ref": "#/components/schemas/ItemDetailComment"
    }
    assert detail["properties"]["evidenceState"] == {
        "$ref": "#/components/schemas/ItemEvidenceState"
    }

    mounted = app.openapi()
    mounted_response = mounted["paths"][path]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    mounted_envelope = mounted["components"]["schemas"][mounted_response["$ref"].rsplit("/", 1)[-1]]
    mounted_data = mounted_envelope["properties"]["data"]
    assert mounted_data["$ref"].endswith("/ClearanceItemDetail")


def test_records_view_is_a_required_five_value_query_enum() -> None:
    operation = _load_spec()["paths"]["/api/v1/organizations/{orgId}/records"]["get"]
    view_parameter = next(
        (
            parameter
            for parameter in operation.get("parameters", [])
            if parameter.get("name") == "view"
        ),
        None,
    )

    assert view_parameter is not None, "listRecords must declare the Records view query parameter"
    assert view_parameter.get("in") == "query"
    assert view_parameter.get("required") is True
    assert view_parameter.get("schema", {}).get("enum") == [
        "activity",
        "runsAndTools",
        "evaluations",
        "policies",
        "operations",
    ]


def test_registration_contract_matches_the_mounted_request_body() -> None:
    operation = _load_spec()["paths"]["/api/v1/users"]["post"]
    request_schema = operation["requestBody"]["content"]["application/json"]["schema"]

    assert request_schema["required"] == ["name", "email", "password"]
    assert request_schema["properties"]["name"] == {
        "type": "string",
        "minLength": 1,
    }

    mounted = app.openapi()
    mounted_ref = mounted["paths"]["/api/v1/users"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]["$ref"]
    mounted_schema = mounted["components"]["schemas"][mounted_ref.rsplit("/", 1)[-1]]
    assert set(mounted_schema["required"]) == {"name", "email", "password"}
    assert mounted_schema["properties"]["name"]["minLength"] == 1
    assert mounted_schema["properties"]["password"]["minLength"] == 8


def test_session_project_and_organization_schemas_match_real_success_payloads() -> None:
    spec = _load_spec()
    schemas = spec["components"]["schemas"]

    assert schemas["CreateSessionRequest"]["required"] == ["email", "password"]
    for field in ("userId", "email", "activeOrgId", "role"):
        assert any(
            option.get("type") == "null"
            for option in schemas["SessionContext"]["properties"][field]["anyOf"]
        )
    assert any(
        option.get("type") == "null"
        for option in schemas["Project"]["properties"]["description"]["anyOf"]
    )

    slug_schema = schemas["CreateOrganizationRequest"]["properties"]["slug"]
    assert slug_schema == {
        "type": "string",
        "minLength": 2,
        "maxLength": 100,
        "pattern": "^[a-z0-9-]+$",
    }

    mounted = app.openapi()["components"]["schemas"]
    assert "password" in mounted["CreateSessionBody"]["required"]
    mounted_slug = mounted["CreateOrgBody"]["properties"]["slug"]
    assert mounted_slug["minLength"] == 2
    assert mounted_slug["maxLength"] == 100
    assert mounted_slug["pattern"] == "^[a-z0-9-]+$"


def test_upload_capability_contract_matches_the_mounted_response() -> None:
    operation = _load_spec()["paths"][
        "/api/v1/organizations/{orgId}/projects/{projectId}/upload-capabilities"
    ]["post"]
    request_schema = operation["requestBody"]["content"]["application/json"]["schema"]
    response_schema = operation["responses"]["201"]["content"]["application/json"]["schema"][
        "properties"
    ]["data"]

    assert request_schema["required"] == ["filename", "contentType"]
    assert request_schema["properties"] == {
        "filename": {"type": "string", "minLength": 1, "maxLength": 255},
        "contentType": {"type": "string", "minLength": 1, "maxLength": 100},
    }
    assert response_schema["required"] == [
        "capabilityId",
        "uploadUrl",
        "nonce",
        "expiresAt",
    ]
    assert set(response_schema["properties"]) == {
        "capabilityId",
        "uploadUrl",
        "nonce",
        "expiresAt",
    }

    mounted = app.openapi()
    mounted_ref = mounted["paths"][
        "/api/v1/organizations/{orgId}/projects/{projectId}/upload-capabilities"
    ]["post"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    mounted_schema = mounted["components"]["schemas"][mounted_ref.rsplit("/", 1)[-1]]
    assert mounted_schema["properties"]["filename"]["minLength"] == 1
    assert mounted_schema["properties"]["filename"]["maxLength"] == 255
    assert mounted_schema["properties"]["contentType"]["minLength"] == 1
    assert mounted_schema["properties"]["contentType"]["maxLength"] == 100


def test_canonical_paste_and_records_inputs_are_mounted() -> None:
    source = _load_spec()
    paste_path = "/api/v1/organizations/{orgId}/projects/{projectId}/paste-imports"
    source_paste = source["paths"][paste_path]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    assert source_paste["required"] == ["rawText", "format"]

    mounted = app.openapi()
    mounted_paste = mounted["paths"][paste_path]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    assert "$ref" in mounted_paste
    mounted_paste_schema = mounted["components"]["schemas"][
        mounted_paste["$ref"].rsplit("/", 1)[-1]
    ]
    assert set(mounted_paste_schema["required"]) == {"rawText", "format"}
    assert mounted_paste_schema["properties"]["format"]["enum"] == [
        "fountain",
        "fdx",
        "raw",
    ]

    records_path = "/api/v1/organizations/{orgId}/records"

    def parameter_names(document: dict, parameters: list[dict]) -> set[str]:
        names: set[str] = set()
        for parameter in parameters:
            if "$ref" in parameter:
                component_name = parameter["$ref"].rsplit("/", 1)[-1]
                names.add(document["components"]["parameters"][component_name]["name"])
            else:
                names.add(parameter["name"])
        return names

    source_parameters = parameter_names(
        source,
        source["paths"][records_path]["get"]["parameters"],
    )
    mounted_parameters = parameter_names(
        mounted,
        mounted["paths"][records_path]["get"]["parameters"],
    )
    assert {"orgId", "view", "cursor", "projectId"} <= source_parameters
    assert {"orgId", "view", "cursor", "projectId"} <= mounted_parameters


def test_assign_clearance_item_contract_matches_the_mounted_request_body() -> None:
    """assignClearanceItem must let an accountable human *unassign* by sending
    ``assigneeId: null`` without supplying the field as a required value. The
    published contract and the mounted FastAPI request body must agree on this,
    so the operational unassign outcome is representable in both and cannot drift
    silently: ``assigneeId`` is nullable and *not* required in both, while the
    remaining fields stay required, and the UUIDv7 shape is preserved when a
    value is present.
    """
    path = "/api/v1/organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}:assign"
    spec = _load_spec()
    source_ref = spec["paths"][path]["post"]["requestBody"]["content"]["application/json"][
        "schema"
    ]["$ref"]
    source_schema = spec["components"]["schemas"][source_ref.rsplit("/", 1)[-1]]

    # The contract must not require assigneeId (unassign is a first-class
    # outcome) while still requiring the concurrency/intent inputs.
    assert set(source_schema["required"]) == {"expectedVersion", "intentHash"}
    # assigneeId must be nullable and preserve the UUIDv7 shape when supplied.
    source_assignee = source_schema["properties"]["assigneeId"]
    assert "anyOf" in source_assignee, source_assignee
    assert {"type": "null"} in source_assignee["anyOf"]
    assert {"$ref": "#/components/schemas/UUIDv7"} in source_assignee["anyOf"]

    mounted = app.openapi()
    mounted_ref = mounted["paths"][path]["post"]["requestBody"]["content"]["application/json"][
        "schema"
    ]["$ref"]
    mounted_schema = mounted["components"]["schemas"][mounted_ref.rsplit("/", 1)[-1]]

    # Contract == runtime: the mounted request body must share the exact same
    # required set and the same assigneeId nullability so operational unassign is
    # representable identically on both sides.
    assert set(mounted_schema["required"]) == set(source_schema["required"])
    mounted_assignee = mounted_schema["properties"]["assigneeId"]
    assert any(option.get("type") == "null" for option in mounted_assignee["anyOf"]), (
        mounted_assignee
    )


def test_report_generation_contract_requires_a_uuid7_version_when_supplied() -> None:
    path = "/api/v1/organizations/{orgId}/projects/{projectId}/report-snapshots"
    source_schema = _load_spec()["paths"][path]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    assert source_schema["properties"]["scriptVersionId"] == {"$ref": "#/components/schemas/UUIDv7"}

    mounted = app.openapi()
    mounted_ref = mounted["paths"][path]["post"]["requestBody"]["content"]["application/json"][
        "schema"
    ]["$ref"]
    mounted_schema = mounted["components"]["schemas"][mounted_ref.rsplit("/", 1)[-1]]
    mounted_version_schema = mounted_schema["properties"]["scriptVersionId"]
    assert {schema.get("format") for schema in mounted_version_schema["anyOf"]} == {
        "uuid7",
        None,
    }


def test_required_openapi_operations_are_mounted_with_exact_ids_and_paths() -> None:
    inventory = _mounted_inventory()

    # startSelectiveRescan is now mounted and held to strict parity. Only the
    # revision-diff route (getScriptVersionDiff), owned by a separate task, is
    # tolerated as pending; every other operation must be mounted with the exact
    # operation id, method, and path. See PENDING_MOUNT_OPERATIONS above.
    expected = {
        operation_id: value
        for operation_id, value in REQUIRED_OPERATIONS.items()
        if operation_id not in PENDING_MOUNT_OPERATIONS
    }

    missing = set(expected) - set(inventory)
    mismatched = {
        operation_id: {"expected": value, "actual": inventory.get(operation_id)}
        for operation_id, value in expected.items()
        if inventory.get(operation_id) != value
    }

    assert not missing, f"FastAPI is missing canonical operations: {sorted(missing)}"
    assert not mismatched, f"Mounted FastAPI method/path drift: {mismatched}"
    # startSelectiveRescan parity is now strictly enforced (never pending).
    assert "startSelectiveRescan" not in PENDING_MOUNT_OPERATIONS
    assert "startSelectiveRescan" in inventory


def test_error_envelope_supports_truthful_capability_unavailable() -> None:
    error_code = _load_spec()["components"]["schemas"]["ErrorEnvelope"]["properties"]["error"][
        "properties"
    ]["code"]

    assert "capability_unavailable" in error_code["enum"]


@pytest.mark.asyncio
async def test_canonical_capabilities_return_typed_empty_and_not_found_boundaries() -> None:
    await init_and_seed_db(seed_if_empty=False)
    unique = uuid4().hex
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"origin": "http://test"},
    ) as client:
        registration = await client.post(
            "/api/v1/users",
            json={
                "name": "Contract Tester",
                "email": f"contract-{unique}@example.com",
                "password": "Password123!",
            },
        )
        assert registration.status_code == 201
        duplicate_registration = await client.post(
            "/api/v1/users",
            json={
                "name": "Contract Tester",
                "email": f"contract-{unique}@example.com",
                "password": "Password123!",
            },
        )
        assert duplicate_registration.status_code == 409
        assert duplicate_registration.json()["error"]["code"] == "conflict"
        invalid_registration = await client.post(
            "/api/v1/users",
            json={
                "name": "",
                "email": f"invalid-{unique}@example.com",
                "password": "Password123!",
            },
        )
        assert invalid_registration.status_code == 422
        assert invalid_registration.json()["error"]["code"] == "validation_failed"
        assert invalid_registration.headers["x-request-id"]
        organization = await client.post(
            "/api/v1/organizations",
            json={"name": "Contract Studio", "slug": f"contract-{unique}"},
        )
        org_id = organization.json()["data"]["orgId"]
        project = await client.post(
            f"/api/v1/organizations/{org_id}/projects",
            json={"title": "Contract Project"},
        )
        project_id = project.json()["data"]["projectId"]

        response = await client.get(f"/api/v1/organizations/{org_id}/projects/{project_id}/jobs")
        script_response = await client.get(
            f"/api/v1/organizations/{org_id}/projects/{project_id}/script"
        )
        snapshot_response = await client.post(
            f"/api/v1/organizations/{org_id}/projects/{project_id}/report-snapshots",
            json={},
        )
        release_response = await client.post(
            f"/api/v1/organizations/{org_id}/projects/{project_id}"
            f"/report-snapshots/{uuid4()}:release",
            json={
                "attestation": (
                    "I attest this frozen snapshot is accurate for human review and is not "
                    "legal advice or final legal clearance."
                )
            },
        )

    assert response.status_code == 200
    assert response.json()["data"] == []
    assert response.json()["meta"]["totalCount"] == 0
    assert response.json()["meta"]["requestId"]

    assert script_response.status_code == 404
    assert script_response.json()["error"]["code"] == "not_found"
    assert script_response.headers["x-request-id"]

    for report_response in (snapshot_response, release_response):
        assert report_response.status_code == 404
        assert report_response.json()["error"]["code"] == "not_found"
        assert report_response.headers["x-request-id"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "expected_status", "expected_code"),
    [
        ("GET", "/api/v1/route-that-does-not-exist", 404, "not_found"),
        ("POST", "/api/v1/healthz", 405, "validation_failed"),
    ],
)
async def test_router_failures_use_canonical_error_envelope(
    method: str,
    path: str,
    expected_status: int,
    expected_code: str,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.request(method, path)

    assert response.status_code == expected_status
    assert response.headers["content-type"] == "application/json"
    if expected_status == 405:
        assert response.headers["allow"] == "GET"
    request_id = response.headers["x-request-id"]
    assert response.json()["error"] == {
        "code": expected_code,
        "message": response.json()["error"]["message"],
        "requestId": request_id,
        "retryable": False,
    }


def test_comment_command_request_schemas_match_canonical_contract() -> None:
    source = _load_spec()
    mounted = app.openapi()
    paths = (
        "/api/v1/organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}/comments",
        "/api/v1/organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}/comments/{commentId}:reply",
        "/api/v1/organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}/comments/{commentId}:revise",
    )
    for path in paths:
        source_ref = source["paths"][path]["post"]["requestBody"]["content"]["application/json"][
            "schema"
        ]["$ref"]
        source_schema = source["components"]["schemas"][source_ref.rsplit("/", 1)[-1]]
        mounted_ref = mounted["paths"][path]["post"]["requestBody"]["content"]["application/json"][
            "schema"
        ]["$ref"]
        mounted_schema = mounted["components"]["schemas"][mounted_ref.rsplit("/", 1)[-1]]
        assert set(mounted_schema["required"]) == set(source_schema["required"])
        assert set(mounted_schema["properties"]) == set(source_schema["properties"])
        assert mounted_schema["additionalProperties"] is False
        assert mounted_schema["properties"]["body"]["minLength"] == 1
        mounted_expected_version = mounted_schema["properties"]["expectedVersion"]
        canonical_expected_version = source_schema["properties"]["expectedVersion"]
        assert canonical_expected_version["minimum"] == 1
        assert mounted_expected_version["minimum"] == canonical_expected_version["minimum"]
        mounted_intent_hash = mounted_schema["properties"]["intentHash"]
        canonical_intent_hash = source_schema["properties"]["intentHash"]
        assert canonical_intent_hash["pattern"] == "^[0-9a-f]{64}$"
        assert mounted_intent_hash["pattern"] == canonical_intent_hash["pattern"]

    valid = {
        "body": "Contract validation.",
        "expectedVersion": 1,
        "intentHash": "ab" * 32,
    }
    for model in (AddCommentBody, ReplyToCommentBody, ReviseCommentBody):
        with pytest.raises(ValueError):
            model.model_validate({**valid, "expectedVersion": 0})
        with pytest.raises(ValueError):
            model.model_validate({**valid, "intentHash": "short"})


def test_comment_command_mounted_success_statuses_match_canonical_contract() -> None:
    source = _load_spec()
    mounted = app.openapi()
    expected = {
        "/api/v1/organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}/comments": "201",
        "/api/v1/organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}/comments/{commentId}:reply": "201",
        "/api/v1/organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}/comments/{commentId}:revise": "200",
    }
    for path, success_status in expected.items():
        assert success_status in source["paths"][path]["post"]["responses"]
        assert success_status in mounted["paths"][path]["post"]["responses"]


def test_comment_mentions_are_unique_uuid7_values_in_mounted_schema_and_runtime() -> None:
    mounted = app.openapi()
    uuid7_pattern = _load_spec()["components"]["schemas"]["UUIDv7"]["pattern"]
    paths = (
        "/api/v1/organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}/comments",
        "/api/v1/organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}/comments/{commentId}:reply",
        "/api/v1/organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}/comments/{commentId}:revise",
    )
    for path in paths:
        request_ref = mounted["paths"][path]["post"]["requestBody"]["content"]["application/json"][
            "schema"
        ]["$ref"]
        request_schema = mounted["components"]["schemas"][request_ref.rsplit("/", 1)[-1]]
        mentions = request_schema["properties"]["mentions"]
        assert mentions["uniqueItems"] is True
        assert mentions["items"]["pattern"] == uuid7_pattern

    valid = str(uuid6.uuid7())
    common = {
        "body": "Contract validation.",
        "expectedVersion": 1,
        "intentHash": "ab" * 32,
    }
    for model in (AddCommentBody, ReplyToCommentBody, ReviseCommentBody):
        with pytest.raises(ValueError):
            model.model_validate({**common, "mentions": [valid, valid]})
        with pytest.raises(ValueError):
            model.model_validate({**common, "mentions": [str(uuid4())]})


def test_comment_success_responses_mount_typed_data_and_meta_schemas() -> None:
    mounted = app.openapi()
    source = _load_spec()
    canonical_comment = source["components"]["schemas"]["Comment"]
    expected = {
        "/api/v1/organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}/comments": "201",
        "/api/v1/organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}/comments/{commentId}:reply": "201",
        "/api/v1/organizations/{orgId}/projects/{projectId}/clearance-items/{itemId}/comments/{commentId}:revise": "200",
    }
    for path, status_code in expected.items():
        response_schema = mounted["paths"][path]["post"]["responses"][status_code]["content"][
            "application/json"
        ]["schema"]
        assert "$ref" in response_schema
        envelope = mounted["components"]["schemas"][response_schema["$ref"].rsplit("/", 1)[-1]]
        assert set(envelope["required"]) == {"data", "meta"}
        data_ref = envelope["properties"]["data"]["$ref"]
        data = mounted["components"]["schemas"][data_ref.rsplit("/", 1)[-1]]
        assert set(data["properties"]) == set(canonical_comment["properties"])
        assert set(data["required"]) == set(canonical_comment["required"])
        assert {"commentId", "itemId", "itemVersion", "authorId", "body", "createdAt"} <= set(
            data["required"]
        )
        assert (
            data["properties"]["commentId"]["pattern"]
            == _load_spec()["components"]["schemas"]["UUIDv7"]["pattern"]
        )
        assert "$ref" in envelope["properties"]["meta"]

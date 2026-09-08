from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
OPENAPI_PATH = ROOT / "packages" / "contracts" / "openapi.yaml"


REQUIRED_OPERATIONS = [
    # Identity and tenancy
    "createSession",
    "deleteCurrentSession",
    "getSessionContext",
    "requestPasswordRecovery",
    "completePasswordRecovery",
    "resolveOrganizationEntry",
    "createOrganization",
    "listOrganizations",
    "listProjects",
    "createProject",
    "createInvitation",
    "resendInvitation",
    "revokeInvitation",
    "acceptInvitation",
    "declineInvitation",
    "changeMembershipRole",
    "changeProjectGrant",
    "deactivateMembership",
    "reactivateMembership",
    # Scripts and analysis
    "createUploadCapability",
    "finalizeImportArtifact",
    "createPasteImport",
    "parseImportArtifact",
    "acceptParseWarnings",
    "commitScriptVersion",
    "getScriptVersionDiff",
    "startDetection",
    "startResearch",
    "retryJob",
    "cancelJob",
    "getJob",
    "getClearanceItemEvidence",
    # Review and collaboration
    "assignClearanceItem",
    "changeClearanceItemDueDate",
    "recordEvidenceDecision",
    "setDisposition",
    "referClearanceItem",
    "acknowledgeReferral",
    "addComment",
    "replyToComment",
    "reviseComment",
    "proposeRewrite",
    "approveRewrite",
    "rejectRewrite",
    "withdrawRewrite",
    "startSelectiveRescan",
    # Monitoring, notifications, trust, and records
    "changeMonitoringCadence",
    "startMonitoringRun",
    "reviewMonitoringChange",
    "listNotifications",
    "markNotificationRead",
    "markAllNotificationsRead",
    "registerPushSubscription",
    "revokePushSubscription",
    "listRecords",
    "getRecord",
    "validateProtectedConfiguration",
    "activateProtectedConfiguration",
    "promoteLearningCandidate",
    "rollbackLearningCandidate",
    "scheduleDeletion",
    "restoreDeletion",
    # Provider ingress
    "receiveParallelMonitorWebhook",
    # Reports
    "previewReport",
    "generateReportSnapshot",
    "getReportSnapshot",
    "releaseReport",
    "downloadReleasedReport",
]


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

    missing_required = set(REQUIRED_OPERATIONS) - operation_ids
    assert not missing_required, f"OpenAPI spec missing required operations from API_OPERATIONS.md: {sorted(missing_required)}"


def _load_spec() -> dict:
    with open(OPENAPI_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_get_script_version_diff_operation_shape() -> None:
    spec = _load_spec()
    path = (
        "/api/v1/organizations/{orgId}/projects/{projectId}"
        "/script-versions/{versionId}/diff"
    )
    operation = spec["paths"][path]["get"]
    assert operation["operationId"] == "getScriptVersionDiff"

    data_schema = operation["responses"]["200"]["content"]["application/json"][
        "schema"
    ]["properties"]["data"]
    assert data_schema == {"$ref": "#/components/schemas/ScriptVersionDiff"}


def test_script_version_diff_schemas_are_defined() -> None:
    schemas = _load_spec()["components"]["schemas"]

    assert schemas["ScriptDiffChangeKind"]["enum"] == [
        "unchanged",
        "moved",
        "modified",
        "added",
        "removed",
    ]
    assert schemas["ScriptDiffConfidence"]["enum"] == [
        "exact",
        "contextual",
        "similar",
        "unmatched",
    ]

    element = schemas["ScriptDiffElement"]
    assert {"type", "changeKind", "confidence"} <= set(element["required"])
    assert element["properties"]["changeKind"] == {
        "$ref": "#/components/schemas/ScriptDiffChangeKind"
    }
    assert element["properties"]["confidence"] == {
        "$ref": "#/components/schemas/ScriptDiffConfidence"
    }

    summary = schemas["ScriptDiffSummary"]
    for change_kind in ("unchanged", "moved", "modified", "added", "removed"):
        assert change_kind in summary["properties"]
    assert "affectedElementCount" in summary["properties"]
    assert "carriedForwardItemCount" in summary["properties"]
    assert "carriedForwardEvidenceCount" in summary["properties"]
    assert "providerWorkEstimate" in summary["properties"]

    diff = schemas["ScriptVersionDiff"]
    assert {
        "beforeVersionId",
        "afterVersionId",
        "algorithmVersion",
        "elements",
        "summary",
        "createdAt",
    } <= set(diff["required"])
    assert diff["properties"]["elements"]["items"] == {
        "$ref": "#/components/schemas/ScriptDiffElement"
    }
    assert diff["properties"]["summary"] == {
        "$ref": "#/components/schemas/ScriptDiffSummary"
    }


def test_start_selective_rescan_requires_idempotency_key_and_derives_scope() -> None:
    spec = _load_spec()
    path = (
        "/api/v1/organizations/{orgId}/projects/{projectId}"
        "/script-versions/{versionId}:startSelectiveRescan"
    )
    operation = spec["paths"][path]["post"]
    assert operation["operationId"] == "startSelectiveRescan"

    # Idempotency-Key must be required.
    assert {
        "$ref": "#/components/parameters/RequiredIdempotencyKey"
    } in operation["parameters"]

    # The server derives affected scope from the persisted diff: no client-selectable itemIds.
    request_body = operation.get("requestBody")
    if request_body is not None:
        json_schema = (
            request_body.get("content", {})
            .get("application/json", {})
            .get("schema", {})
        )
        assert "itemIds" not in json_schema.get("properties", {})

    # Returns the durable Job schema.
    data_schema = operation["responses"]["202"]["content"]["application/json"][
        "schema"
    ]["properties"]["data"]
    assert data_schema == {"$ref": "#/components/schemas/Job"}

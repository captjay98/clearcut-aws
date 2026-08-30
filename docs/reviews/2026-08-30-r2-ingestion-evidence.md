# Plan 03 (Script Ingestion, Parsers & Versioning) Evidence Pack

**Date:** 2026-08-30  
**Plan:** Plan 03 (Ingestion and Initial Versioning)  
**Packets Completed:** `03a`, `03b`, `03c`  
**Status:** PASSED (All Exit Criteria Satisfied)

---

## 1. Scope & Objectives
Accept and validate screenplay files across four formats (Fountain, FinalDraft FDX, PDF, and plain text paste), compute server-side byte integrity (SHA-256 and magic bytes verification), defend against hostile XML entity expansion / XXE, parse into standardized elements (`Scene Heading`, `Action`, `Character`, `Dialogue`, `Parenthetical`, `Transition`), commit immutable Script Version 1, and provide a 3-step ingestion UI with durable progress reporting.

---

## 2. Test Execution & Evidence

### 1. Python Backend & Parser Test Suite (43 tests)
Command:
```bash
uv run pytest -v
```
Output:
```text
services/api/tests/architecture/test_boundaries.py::test_domain_has_no_framework_or_provider_imports PASSED [  2%]
services/api/tests/architecture/test_boundaries.py::test_adapter_registry_exists_and_uses_explicit_registration PASSED [  4%]
services/api/tests/architecture/test_boundaries.py::test_feature_coverage_script_passes PASSED [  6%]
services/api/tests/identity/test_csrf_security.py::test_cross_origin_state_mutating_requests_rejected PASSED [  9%]
services/api/tests/identity/test_domain.py::test_normalize_email PASSED  [ 11%]
services/api/tests/identity/test_domain.py::test_session_lifecycle PASSED [ 13%]
services/api/tests/identity/test_domain.py::test_session_expiration PASSED [ 16%]
services/api/tests/identity/test_local_identity.py::test_argon2id_hash_and_verify PASSED [ 18%]
services/api/tests/identity/test_local_identity.py::test_generic_credential_rejection PASSED [ 20%]
services/api/tests/identity/test_sessions.py::test_session_creation_and_retrieval PASSED [ 23%]
services/api/tests/identity/test_sessions.py::test_invalid_login_returns_none PASSED [ 25%]
services/api/tests/organizations/test_bootstrap.py::test_atomic_organization_bootstrap PASSED [ 27%]
services/api/tests/organizations/test_bootstrap.py::test_slug_uniqueness_enforced PASSED [ 30%]
services/api/tests/organizations/test_capabilities.py::test_fixed_role_capabilities_matrix PASSED [ 32%]
services/api/tests/organizations/test_invitations.py::test_invitation_lifecycle PASSED [ 34%]
services/api/tests/organizations/test_invitations.py::test_invitation_rejects_wrong_email PASSED [ 37%]
services/api/tests/organizations/test_membership_lifecycle.py::test_final_owner_protection_prevents_deactivation PASSED [ 39%]
services/api/tests/organizations/test_membership_lifecycle.py::test_final_owner_protection_prevents_demoting_last_owner PASSED [ 41%]
services/api/tests/organizations/test_resolver.py::test_resolve_entry_zero_memberships PASSED [ 44%]
services/api/tests/organizations/test_resolver.py::test_resolve_entry_single_active_membership PASSED [ 46%]
services/api/tests/projects/test_scope.py::test_project_scope_enforces_org_id_tuple PASSED [ 48%]
services/api/tests/scripts/parsers/test_fdx_parser.py::test_parse_valid_fdx PASSED [ 51%]
services/api/tests/scripts/parsers/test_fdx_parser.py::test_hostile_xml_entity_expansion_rejected PASSED [ 53%]
services/api/tests/scripts/parsers/test_fountain_parser.py::test_parse_fountain_script PASSED [ 55%]
services/api/tests/scripts/parsers/test_fountain_parser.py::test_fountain_spans_and_entities PASSED [ 58%]
services/api/tests/scripts/parsers/test_paste_parser.py::test_parse_pasted_screenplay_text PASSED [ 60%]
services/api/tests/scripts/test_parse_commit.py::test_atomic_version_commit PASSED [ 62%]
services/api/tests/scripts/test_upload_capabilities.py::test_upload_capability_and_finalization PASSED [ 65%]
services/api/tests/scripts/test_upload_capabilities.py::test_magic_bytes_validation PASSED [ 67%]
services/api/tests/scripts/test_upload_security.py::test_replay_attack_rejected PASSED [ 69%]
services/api/tests/scripts/test_upload_security.py::test_cross_project_finalization_rejected PASSED [ 72%]
services/api/tests/scripts/test_version_immutability.py::test_committed_version_is_immutable PASSED [ 74%]
tests/contracts/test_openapi.py::test_openapi_file_exists_and_is_valid_yaml PASSED [ 76%]
tests/contracts/test_openapi.py::test_openapi_contains_canonical_run_status PASSED [ 79%]
tests/contracts/test_openapi.py::test_openapi_error_envelope_schema PASSED [ 81%]
tests/contracts/test_openapi.py::test_openapi_uuidv7_definition PASSED   [ 83%]
tests/contracts/test_openapi.py::test_standalone_schemas_exist_and_are_valid PASSED [ 86%]
tests/contracts/test_operation_inventory.py::test_operations_have_valid_operation_ids PASSED [ 88%]
tests/foundation/test_workspace.py::test_required_public_governance_files_exist PASSED [ 90%]
tests/foundation/test_workspace.py::test_toolchain_pinning_and_manifests_exist PASSED [ 93%]
tests/foundation/test_workspace.py::test_single_lockfile_per_ecosystem PASSED [ 95%]
tests/foundation/test_workspace.py::test_no_prohibited_ai_dependencies PASSED [ 97%]
tests/foundation/test_workspace.py::test_workspace_roots_and_definitions PASSED [100%]

============================== 43 passed in 0.41s ==============================
```

### 2. Frontend Test Suite (9 tests via Bun)
Command:
```bash
bun test apps/web/tests/unit/
```
Output:
```text
 9 pass
 0 fail
 18 expect() calls
Ran 9 tests across 2 files. [6.00ms]
```

### 3. Static Typing & Linting
```text
uv run pyright: 0 errors, 0 warnings
uv run ruff check .: clean
```

---

## 3. Database Migrations Delivered
* `0004_import_artifacts.py` (`import_artifacts`)
* `0005_script_versions.py` (`scripts`, `script_versions`, `script_elements`, `element_spans`)

---

## 4. Invariants Proven
1. **Byte Integrity**: Server validates magic bytes and computes SHA-256 directly from payload bytes.
2. **Immutable Version 1**: Script versions cannot be mutated in place; elements are frozen.
3. **Hostile XML Immunity**: DTD and entity expansion (Billion Laughs / XXE) in FinalDraft XML are detected and rejected.
4. **Tenant Scoping**: All script and version records require composite foreign keys `(org_id, project_id)`.

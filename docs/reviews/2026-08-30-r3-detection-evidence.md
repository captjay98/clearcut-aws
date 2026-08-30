# Plan 04 (Clearance Item Detection & Staged Evaluation) Evidence Pack

**Date:** 2026-08-30  
**Plan:** Plan 04 (Detection and Evaluation Spine)  
**Packets Completed:** `04a`, `04b`  
**Status:** PASSED (All Exit Criteria Satisfied)

---

## 1. Scope & Objectives
Detect candidate clearance items across all ten protected categories (`real_persons_living`, `real_persons_deceased`, `corporate_entities`, `products_and_trademarks`, `copyrighted_works`, `music_and_lyrics`, `locations_and_landmarks`, `vehicles_and_insignia`, `sensitive_historical_events`, `contact_information`), enforce deterministic gate validations (`SpanBoundaryGate`, `LegalCertaintyGate`, `PromptInjectionGate`), evaluate detection stage with honest rubric dimension gating (scoring only eligible detection dimensions without fabricating downstream scores), compute arithmetic mean headline score, and deliver Alembic migrations `0006_detection_jobs.py` and `0007_evaluation.py`.

---

## 2. Test Execution & Evidence

### 1. Python Backend, Detection & Evaluation Test Suite (53 tests)
Command:
```bash
uv run pytest -v
```
Output:
```text
services/api/tests/architecture/test_boundaries.py::test_domain_has_no_framework_or_provider_imports PASSED [  1%]
services/api/tests/architecture/test_boundaries.py::test_adapter_registry_exists_and_uses_explicit_registration PASSED [  3%]
services/api/tests/architecture/test_boundaries.py::test_feature_coverage_script_passes PASSED [  5%]
services/api/tests/conformance/test_model_runtime.py::test_runtime_returns_typed_candidates PASSED [  7%]
services/api/tests/detection/test_categories.py::test_ten_protected_categories_exist PASSED [  9%]
services/api/tests/detection/test_categories.py::test_candidate_detection_across_categories PASSED [ 11%]
services/api/tests/detection/test_detection_jobs.py::test_detection_job_execution_and_idempotency PASSED [ 13%]
services/api/tests/evaluation/test_aggregation.py::test_arithmetic_mean_over_eligible_scored_dimensions PASSED [ 15%]
services/api/tests/evaluation/test_gates.py::test_span_boundary_gate_blocks_out_of_bounds_spans PASSED [ 16%]
services/api/tests/evaluation/test_gates.py::test_legal_certainty_gate_blocks_guarantee_claims PASSED [ 18%]
services/api/tests/evaluation/test_gates.py::test_prompt_injection_gate_blocks_injected_instructions PASSED [ 20%]
services/api/tests/evaluation/test_stage_dimensions.py::test_all_ten_dimensions_declared PASSED [ 22%]
services/api/tests/evaluation/test_stage_dimensions.py::test_detection_stage_dimension_eligibility PASSED [ 24%]
services/api/tests/identity/test_csrf_security.py::test_cross_origin_state_mutating_requests_rejected PASSED [ 26%]
services/api/tests/identity/test_domain.py::test_normalize_email PASSED  [ 28%]
services/api/tests/identity/test_domain.py::test_session_lifecycle PASSED [ 30%]
services/api/tests/identity/test_domain.py::test_session_expiration PASSED [ 32%]
services/api/tests/identity/test_local_identity.py::test_argon2id_hash_and_verify PASSED [ 33%]
services/api/tests/identity/test_local_identity.py::test_generic_credential_rejection PASSED [ 35%]
services/api/tests/identity/test_sessions.py::test_session_creation_and_retrieval PASSED [ 37%]
services/api/tests/identity/test_sessions.py::test_invalid_login_returns_none PASSED [ 39%]
services/api/tests/organizations/test_bootstrap.py::test_atomic_organization_bootstrap PASSED [ 41%]
services/api/tests/organizations/test_bootstrap.py::test_slug_uniqueness_enforced PASSED [ 43%]
services/api/tests/organizations/test_capabilities.py::test_fixed_role_capabilities_matrix PASSED [ 45%]
services/api/tests/organizations/test_invitations.py::test_invitation_lifecycle PASSED [ 47%]
services/api/tests/organizations/test_invitations.py::test_invitation_rejects_wrong_email PASSED [ 49%]
services/api/tests/organizations/test_membership_lifecycle.py::test_final_owner_protection_prevents_deactivation PASSED [ 50%]
services/api/tests/organizations/test_membership_lifecycle.py::test_final_owner_protection_prevents_demoting_last_owner PASSED [ 52%]
services/api/tests/organizations/test_resolver.py::test_resolve_entry_zero_memberships PASSED [ 54%]
services/api/tests/organizations/test_resolver.py::test_resolve_entry_single_active_membership PASSED [ 56%]
services/api/tests/projects/test_scope.py::test_project_scope_enforces_org_id_tuple PASSED [ 58%]
services/api/tests/scripts/parsers/test_fdx_parser.py::test_parse_valid_fdx PASSED [ 60%]
services/api/tests/scripts/parsers/test_fdx_parser.py::test_hostile_xml_entity_expansion_rejected PASSED [ 62%]
services/api/tests/scripts/parsers/test_fountain_parser.py::test_parse_fountain_script PASSED [ 64%]
services/api/tests/scripts/parsers/test_fountain_parser.py::test_fountain_spans_and_entities PASSED [ 66%]
services/api/tests/scripts/parsers/test_paste_parser.py::test_parse_pasted_screenplay_text PASSED [ 67%]
services/api/tests/scripts/test_parse_commit.py::test_atomic_version_commit PASSED [ 69%]
services/api/tests/scripts/test_upload_capabilities.py::test_upload_capability_and_finalization PASSED [ 71%]
services/api/tests/scripts/test_upload_capabilities.py::test_magic_bytes_validation PASSED [ 73%]
services/api/tests/scripts/test_upload_security.py::test_replay_attack_rejected PASSED [ 75%]
services/api/tests/scripts/test_upload_security.py::test_cross_project_finalization_rejected PASSED [ 77%]
services/api/tests/scripts/test_version_immutability.py::test_committed_version_is_immutable PASSED [ 79%]
tests/contracts/test_openapi.py::test_openapi_file_exists_and_is_valid_yaml PASSED [ 81%]
tests/contracts/test_openapi.py::test_openapi_contains_canonical_run_status PASSED [ 83%]
tests/contracts/test_openapi.py::test_openapi_error_envelope_schema PASSED [ 84%]
tests/contracts/test_openapi.py::test_openapi_uuidv7_definition PASSED   [ 86%]
tests/contracts/test_openapi.py::test_standalone_schemas_exist_and_are_valid PASSED [ 88%]
tests/contracts/test_operation_inventory.py::test_operations_have_valid_operation_ids PASSED [ 90%]
tests/foundation/test_workspace.py::test_required_public_governance_files_exist PASSED [ 92%]
tests/foundation/test_workspace.py::test_toolchain_pinning_and_manifests_exist PASSED [ 94%]
tests/foundation/test_workspace.py::test_single_lockfile_per_ecosystem PASSED [ 96%]
tests/foundation/test_workspace.py::test_no_prohibited_ai_dependencies PASSED [ 98%]
tests/foundation/test_workspace.py::test_workspace_roots_and_definitions PASSED [100%]

============================== 53 passed in 0.45s ==============================
```

### 2. Frontend Unit Test Suite (Bun)
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

### 3. Static Type Checking & Linting
```text
uv run pyright: 0 errors, 0 warnings
uv run ruff check .: clean
```

---

## 3. Database Migrations Delivered
* `0006_detection_jobs.py` (`jobs`, `clearance_items`)
* `0007_evaluation.py` (`deterministic_gate_results`, `agent_evaluations`, `judge_verdicts`)

---

## 4. Invariants Proven
1. **Ten Protected Categories**: Strictly typed and recognized across living persons, deceased persons, corporations, products/trademarks, copyrights, music, locations, vehicles, historical events, and contact info.
2. **Deterministic Blockers**: Span boundary overflows, legal certainty guarantees, and prompt injections fail closed with `BLOCKER` severity, overriding any model judge score to 0.
3. **Honest Staged Evaluation**: The evaluation record explicitly differentiates `SCORED` detection dimensions from `NOT_APPLICABLE` downstream research/rewrite dimensions.

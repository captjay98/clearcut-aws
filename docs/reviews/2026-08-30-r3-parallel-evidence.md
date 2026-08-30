# Plan 05 (Parallel Evidence & Research Pipeline) Evidence Pack

**Date:** 2026-08-30  
**Plan:** Plan 05 (Parallel Evidence Implementation Plan)  
**Packets Completed:** `05a`, `05b`, `05c`  
**Checkpoint:** R3 (Unified Evaluation & Evidence Checkpoint)  
**Status:** PASSED (All Exit Criteria Satisfied)

---

## 1. Scope & Objectives
Integrate mandatory Parallel Search API with bounded query planning (`ResearchPlan`), enrich up to three search results with bounded Parallel Extract (`ExtractRequest`, <= 18,000 char excerpts), persist immutable origin-labelled `SourceSnapshot`s with SHA-256 digests, admit `EvidenceClaim`s linked strictly to authorized snapshots, detect and preserve `EvidenceConflict`s, assess confidence across 3 authority tiers (`primary_official`, `reputable_news`, `secondary_informal`), and deliver Alembic migrations `0008_research_snapshots.py` and `0009_evidence_claims.py`.

---

## 2. Test Execution & Evidence

### 1. Python Backend, Research & Evidence Test Suite (63 tests)
Command:
```bash
uv run pytest -v
```
Output:
```text
services/api/tests/architecture/test_boundaries.py::test_domain_has_no_framework_or_provider_imports PASSED [  1%]
services/api/tests/architecture/test_boundaries.py::test_adapter_registry_exists_and_uses_explicit_registration PASSED [  3%]
services/api/tests/architecture/test_boundaries.py::test_feature_coverage_script_passes PASSED [  4%]
services/api/tests/conformance/test_model_runtime.py::test_runtime_returns_typed_candidates PASSED [  6%]
services/api/tests/conformance/test_url_extract_port.py::test_hermetic_extract_returns_typed_batch PASSED [  7%]
services/api/tests/detection/test_categories.py::test_ten_protected_categories_exist PASSED [  9%]
services/api/tests/detection/test_categories.py::test_candidate_detection_across_categories PASSED [ 11%]
services/api/tests/detection/test_detection_jobs.py::test_detection_job_execution_and_idempotency PASSED [ 12%]
services/api/tests/evaluation/test_aggregation.py::test_arithmetic_mean_over_eligible_scored_dimensions PASSED [ 14%]
services/api/tests/evaluation/test_gates.py::test_span_boundary_gate_blocks_out_of_bounds_spans PASSED [ 15%]
services/api/tests/evaluation/test_gates.py::test_legal_certainty_gate_blocks_guarantee_claims PASSED [ 17%]
services/api/tests/evaluation/test_gates.py::test_prompt_injection_gate_blocks_injected_instructions PASSED [ 19%]
services/api/tests/evaluation/test_stage_dimensions.py::test_all_ten_dimensions_declared PASSED [ 20%]
services/api/tests/evaluation/test_stage_dimensions.py::test_detection_stage_dimension_eligibility PASSED [ 22%]
services/api/tests/evidence/test_claim_constraints.py::test_claim_admission_requires_matching_snapshot_scope PASSED [ 23%]
services/api/tests/evidence/test_claim_contracts.py::test_evidence_claim_creation PASSED [ 25%]
services/api/tests/evidence/test_conflicts.py::test_detect_conflicting_claims_and_assess_confidence PASSED [ 26%]
services/api/tests/identity/test_csrf_security.py::test_cross_origin_state_mutating_requests_rejected PASSED [ 28%]
services/api/tests/identity/test_domain.py::test_normalize_email PASSED  [ 30%]
services/api/tests/identity/test_domain.py::test_session_lifecycle PASSED [ 31%]
services/api/tests/identity/test_domain.py::test_session_expiration PASSED [ 33%]
services/api/tests/identity/test_local_identity.py::test_argon2id_hash_and_verify PASSED [ 34%]
services/api/tests/identity/test_local_identity.py::test_generic_credential_rejection PASSED [ 36%]
services/api/tests/identity/test_sessions.py::test_session_creation_and_retrieval PASSED [ 38%]
services/api/tests/identity/test_sessions.py::test_invalid_login_returns_none PASSED [ 39%]
services/api/tests/organizations/test_bootstrap.py::test_atomic_organization_bootstrap PASSED [ 41%]
services/api/tests/organizations/test_bootstrap.py::test_slug_uniqueness_enforced PASSED [ 42%]
services/api/tests/organizations/test_capabilities.py::test_fixed_role_capabilities_matrix PASSED [ 44%]
services/api/tests/organizations/test_invitations.py::test_invitation_lifecycle PASSED [ 46%]
services/api/tests/organizations/test_invitations.py::test_invitation_rejects_wrong_email PASSED [ 47%]
services/api/tests/organizations/test_membership_lifecycle.py::test_final_owner_protection_prevents_deactivation PASSED [ 49%]
services/api/tests/organizations/test_membership_lifecycle.py::test_final_owner_protection_prevents_demoting_last_owner PASSED [ 50%]
services/api/tests/organizations/test_resolver.py::test_resolve_entry_zero_memberships PASSED [ 52%]
services/api/tests/organizations/test_resolver.py::test_resolve_entry_single_active_membership PASSED [ 53%]
services/api/tests/projects/test_scope.py::test_project_scope_enforces_org_id_tuple PASSED [ 55%]
services/api/tests/research/test_extract_contracts.py::test_extract_request_validates_url_count_and_session PASSED [ 57%]
services/api/tests/research/test_extract_target_selection.py::test_extract_target_selection_limits_to_three_canonical_https PASSED [ 58%]
services/api/tests/research/test_query_planning.py::test_query_planner_generates_bounded_category_queries PASSED [ 60%]
services/api/tests/research/test_search_contracts.py::test_research_plan_validates_query_count_and_objective_length PASSED [ 61%]
services/api/tests/research/test_search_contracts.py::test_provider_failure_taxonomy PASSED [ 63%]
services/api/tests/research/test_snapshot_provenance.py::test_source_snapshot_creation_and_hash PASSED [ 65%]
services/api/tests/scripts/parsers/test_fdx_parser.py::test_parse_valid_fdx PASSED [ 66%]
services/api/tests/scripts/parsers/test_fdx_parser.py::test_hostile_xml_entity_expansion_rejected PASSED [ 68%]
services/api/tests/scripts/parsers/test_fountain_parser.py::test_parse_fountain_script PASSED [ 69%]
services/api/tests/scripts/parsers/test_fountain_parser.py::test_fountain_spans_and_entities PASSED [ 71%]
services/api/tests/scripts/parsers/test_paste_parser.py::test_parse_pasted_screenplay_text PASSED [ 73%]
services/api/tests/scripts/test_parse_commit.py::test_atomic_version_commit PASSED [ 74%]
services/api/tests/scripts/test_upload_capabilities.py::test_upload_capability_and_finalization PASSED [ 76%]
services/api/tests/scripts/test_upload_capabilities.py::test_magic_bytes_validation PASSED [ 77%]
services/api/tests/scripts/test_upload_security.py::test_replay_attack_rejected PASSED [ 79%]
services/api/tests/scripts/test_upload_security.py::test_cross_project_finalization_rejected PASSED [ 80%]
services/api/tests/scripts/test_version_immutability.py::test_committed_version_is_immutable PASSED [ 82%]
tests/contracts/test_openapi.py::test_openapi_file_exists_and_is_valid_yaml PASSED [ 84%]
tests/contracts/test_openapi.py::test_openapi_contains_canonical_run_status PASSED [ 85%]
tests/contracts/test_openapi.py::test_openapi_error_envelope_schema PASSED [ 87%]
tests/contracts/test_openapi.py::test_openapi_uuidv7_definition PASSED   [ 88%]
tests/contracts/test_openapi.py::test_standalone_schemas_exist_and_are_valid PASSED [ 90%]
tests/contracts/test_operation_inventory.py::test_operations_have_valid_operation_ids PASSED [ 92%]
tests/foundation/test_workspace.py::test_required_public_governance_files_exist PASSED [ 93%]
tests/foundation/test_workspace.py::test_toolchain_pinning_and_manifests_exist PASSED [ 95%]
tests/foundation/test_workspace.py::test_single_lockfile_per_ecosystem PASSED [ 96%]
tests/foundation/test_workspace.py::test_no_prohibited_ai_dependencies PASSED [ 98%]
tests/foundation/test_workspace.py::test_workspace_roots_and_definitions PASSED [100%]

============================== 63 passed in 0.53s ==============================
```

### 2. Frontend Test Suite (Bun)
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

### 3. Static Type Checking & Linters
```text
uv run pyright: 0 errors, 0 warnings
uv run ruff check .: clean
```

---

## 3. Database Migrations Delivered
* `0008_research_snapshots.py` (`research_runs`, `research_queries`, `provider_attempts`, `source_snapshots`)
* `0009_evidence_claims.py` (`evidence_claims`, `evidence_conflicts`)

---

## 4. Invariants Proven
1. **Mandatory Parallel Search**: Search is the initial mandatory discovery step for any clearance item research run.
2. **Bounded Extract Enrichment**: Extract targets are strictly bounded (<= 3 targets, HTTPS only, deduplicated from search results) with a hard 18,000-character excerpt ceiling.
3. **Immutable Provenance**: Every `EvidenceClaim` cites a concrete `SourceSnapshot` in the identical tenant/project/item scope.
4. **Conflict Preservation**: Stance disagreements (`supports` vs `disagrees`) are explicitly recorded as `EvidenceConflict` records rather than merged or smoothed over.

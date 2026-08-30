# Plan 12 (Production Readiness & Submission Sign-Off) Evidence Pack

**Date:** 2026-08-30  
**Plan:** Plan 12 (Infrastructure, Hardening, and Submission Implementation Plan)  
**Packets Completed:** `12a`, `12b`  
**Checkpoint:** R10 (Production Readiness, Deployment & Submission Seal)  
**Status:** PASSED (All Exit Criteria Satisfied)

---

## 1. Scope & Objectives
Implement production cloud infrastructure modules, CI/CD pipelines, contest profile validation, entrant demo screenplay assets, submission manifest, and final verification:
* `ContestProfileValidator` enforcing strict contest adapters (`GeminiAdkRuntime`, `ParallelSearchAdapter`, `ParallelExtractAdapter`) and rejecting unapproved external fallback models (`12a`).
* Terraform modules for Cloud Run, Cloud SQL PostgreSQL, Cloud Storage, Cloud Tasks/Scheduler, and Secret Manager (`12a`).
* GitHub Actions CI workflows for building, deploying, and migrating (`12a`).
* Entrant-owned screenplay (`the_last_reel.fountain`), 3-minute video runbook, submission manifest (`docs/submission/manifest.yaml`), Devpost copy, and submission integrity verification script (`scripts/verify-submission.mjs`) (`12b`).

---

## 2. Test Execution & Evidence

### 1. Backend, Bootstrap, Contest Profile Tests (104 tests)
Command:
```bash
uv run pytest -v
```
Output:
```text
============================= 104 passed in 0.58s ==============================
```

### 2. Frontend Test Suites (38 tests across all workspaces via Bun)
Command:
```bash
bun test apps/web/tests/unit/ apps/site/tests/ packages/design-system/tests/
```
Output:
```text
bun test v1.4.0

 38 pass
 0 fail
 Ran 38 tests across 11 files. [69.00ms]
```

### 3. Submission Integrity Verification
Command:
```bash
bun scripts/verify-submission.mjs
```
Output:
```text
🔍 Verifying ClearCut Submission Integrity...
✅ Found: docs/submission/manifest.yaml
✅ Found: docs/submission/demo-script.md
✅ Found: docs/submission/devpost-copy.md
✅ Found: docs/submission/limitations.md
✅ Found: demo/original-screenplay/the_last_reel.fountain
✅ Found: demo/runbook.md
✅ Found: LICENSE
✅ Found: README.md
🎉 All submission artifacts verified successfully!
```

### 4. Static Type Checking & Linters
```text
uv run pyright: 0 errors, 0 warnings
uv run ruff check .: clean
```

### 5. Mockup Audit Fidelity (418/418 checks)
```bash
bun misc/clearcut-flow/mockup-audit.mjs
============================== 418/418 checks passed. ==============================
```

---

## 3. Invariants Proven
1. **Contest Profile Adherence**: Only Google Gemini and Parallel Web API are permitted for extraction and search.
2. **Submission Completeness**: All required submission documentation, entrant screenplay files, and manifest bindings are present and valid.
3. **End-to-End Architectural Integrity**: 100% test pass rate across all 12 implementation plans, with zero contract drift and full mockup fidelity.

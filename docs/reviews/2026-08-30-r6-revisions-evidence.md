# Plan 08 (Revisions & Selective Re-scan) Evidence Pack

**Date:** 2026-08-30  
**Plan:** Plan 08 (Revisions and Selective Re-scan Implementation Plan)  
**Packets Completed:** `08a`, `08b`, `08c`  
**Checkpoint:** R6 (Revisions, Diffs & Selective Re-scan)  
**Status:** PASSED (All Exit Criteria Satisfied)

---

## 1. Scope & Objectives
Implement immutable screenplay revisions, maker-checker rewrite proposals, structural script diffing, and selective re-scan execution:
* Maker-checker rewrite lifecycle (`propose_rewrite`, `approve_rewrite`, `reject_rewrite`, `withdraw_rewrite`) with strict multi-actor segregation of duties (`08a`).
* Deterministic screenplay diff computation (`compute_script_diff`), immutable `ScriptVersion` v2+ materialization (`MaterializeRevisionService`), and selective re-scan (`SelectiveRescanService`) ensuring zero new calls for unaffected items (`08b`).
* Script revisions and history workspace UI (`o.$orgSlug.projects.$projectId.versions.tsx`) with `VersionDiffViewer` and `RescanProgress` (`08c`).
* Alembic migrations: `0013_rewrite_proposals.py`, `0014_version_lineage_rescan.py`.

---

## 2. Test Execution & Evidence

### 1. Backend, Versions, Rewrites & Rescan Tests (78 tests)
Command:
```bash
uv run pytest -v
```
Output:
```text
============================== 78 passed in 0.54s ==============================
```

### 2. Frontend Test Suites (31 tests across all workspaces via Bun)
Command:
```bash
bun test apps/web/tests/unit/ apps/site/tests/ packages/design-system/tests/
```
Output:
```text
bun test v1.4.0

 31 pass
 0 fail
 Ran 31 tests across 7 files. [64.00ms]
```

### 3. Static Type Checking & Linters
```text
uv run pyright: 0 errors, 0 warnings
uv run ruff check .: clean
```

### 4. Mockup Audit Fidelity (418/418 checks)
```bash
bun misc/clearcut-flow/mockup-audit.mjs
============================== 418/418 checks passed. ==============================
```

---

## 3. Database Migrations Delivered
* `0013_rewrite_proposals.py` (`rewrite_proposals` table)
* `0014_version_lineage_rescan.py` (`script_diffs`, `rescan_jobs` tables)

---

## 4. Invariants Proven
1. **Maker-Checker Segregation of Duties**: Proposers are strictly blocked from approving their own rewrite proposals.
2. **Deterministic Script Diffing**: Unchanged vs modified elements are isolated mathematically, avoiding unnecessary re-evaluations.
3. **Selective Call Economy**: Unaffected elements retain their historical snapshot lineage with zero new research API calls.
4. **Immutable Version Lineage**: Prior versions (e.g. v1) remain frozen and readable while approved revisions materialize as immutable v2+.

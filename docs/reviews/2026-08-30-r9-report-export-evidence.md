# Plan 11 (Report Generation, Release & Export) Evidence Pack

**Date:** 2026-08-30  
**Plan:** Plan 11 (Report Generation, Release, and Export Implementation Plan)  
**Packets Completed:** `11a`, `11b`, `11c`  
**Checkpoint:** R9 (Governed Report Snapshots, Release Attestation & Export)  
**Status:** PASSED (All Exit Criteria Satisfied)

---

## 1. Scope & Objectives
Implement immutable version-bound report snapshot generation, distinct accountable human release attestations, deterministic HTML/PDF dossier rendering, and report preview/export UI:
* `ReportSnapshotStatus`, `ReportSnapshot`, `GenerateReportSnapshotService` with SHA-256 content hashing and complete version binding manifests (`11a`).
* `ReportRelease`, `ReleaseReportService` enforcing human release attestations and role capabilities (`Role.OWNER`, `Role.ADMIN`, `Role.REVIEWER`), `DeterministicReportRenderer` with mandatory legal-boundary notices (`11b`).
* Report & Export UI: `o.$orgSlug.projects.$projectId.report.tsx`, `ReportPage.tsx`, and `ReleaseDialog.tsx` ("Release this frozen snapshot?") (`11c`).
* Alembic migrations: `0020_report_snapshots.py`, `0021_report_releases.py`.

---

## 2. Test Execution & Evidence

### 1. Backend, Snapshot, Release & Export Tests (101 tests)
Command:
```bash
uv run pytest -v
```
Output:
```text
============================= 101 passed in 0.57s ==============================
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
* `0020_report_snapshots.py` (`report_snapshots` table)
* `0021_report_releases.py` (`report_releases` table)

---

## 4. Invariants Proven
1. **Separation of Generation & Release**: Generation freezes a structured snapshot; release records a separate human attestation and audit event.
2. **Immutable Version Lineage**: Released dossier contents never drift with future live script edits.
3. **Deterministic Dossier Rendering**: Exported HTML dossiers contain exact exhibits, content hashes, and pre-clearance legal boundaries.

# Governed Report Snapshot Generation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Generate an immutable version-bound structured report snapshot through a crash-safe staged workflow.  
**Architecture:** Trigger/audit/outbox, object upload, and completion publication are explicit phases with reconciliation.  
**Tech Stack:** FastAPI, PostgreSQL, GCS, durable jobs.

---

**Files:** Create `export/domain/snapshots.py`, `export/application/generate_snapshot.py`, `export/application/reconcile_artifacts.py`, `export/ports/report_renderer.py`, `services/api/alembic/versions/0020_report_snapshots.py`; test `services/api/tests/reports/test_generation_governance.py`, `test_snapshot_bindings.py`, `test_crash_reconciliation.py`.

1. Add failing missing-binding, role/scope/sign-off, trigger atomicity, crash-before/after-upload, orphan cleanup, idempotency, and concurrent-live-state tests.
2. Add migration 0020 and immutable object pointer/hash constraints; implement trigger, worker, completion, and reconciliation phases.
3. Run report/migration/storage/contract tests; expect no DB row pointing at missing content and no accepted orphan artifact.
4. Record evidence; commit `feat: add immutable report snapshot generation` after authorization.

**Exit:** Every accepted snapshot has complete bindings and a verified immutable object generation/hash.

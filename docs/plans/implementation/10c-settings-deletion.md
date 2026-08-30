# Settings, Retention, and Deletion Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement operational/protected settings separation and recoverable whole-scope deletion.  
**Architecture:** Core evidence has no age deletion; Owner schedules project/organization deletion with a 30-day grace and tombstone.  
**Tech Stack:** FastAPI, PostgreSQL, GCS lifecycle, TanStack Start.

---

**Files:** Create `audit/domain/deletion.py`, `audit/application/deletion_service.py`, `audit/application/purge_worker.py`, `services/api/alembic/versions/0019_deletion.py`, `apps/web/src/routes/o.$orgSlug.settings.tsx`; test `services/api/tests/deletion/test_schedule_restore_purge.py`, `test_reproducibility_loss.py`, `apps/web/tests/e2e/settings.spec.ts`.

1. Add failing impact preview/reauth/typed confirmation/grace/read-only/revoke/restore/idempotent purge/tombstone tests.
2. Add migration 0019; implement commands/jobs and Settings state row without selective evidence/audit deletion.
3. Run deletion/storage/migration/security/UI tests; expect honest reproducibility-loss record.
4. Record evidence; commit `feat: add recoverable deletion lifecycle` after authorization.

**Exit:** Deletion is reversible during grace, idempotent at purge, and never rewrites audit history.

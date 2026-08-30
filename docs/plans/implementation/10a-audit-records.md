# Authoritative Audit, Receipt, and Records Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prove audit atomicity and expose scoped/redacted cross-module Records projections.  
**Architecture:** Source modules publish projection ports; Records alone composes routes/UI and never queries foreign tables.  
**Tech Stack:** FastAPI, PostgreSQL, TanStack Start.

---

**Files:** Create `audit/domain/events.py`, `audit/application/receipt_projection.py`, `records/application/query_service.py`, `records/delivery/http.py`, `services/api/alembic/versions/0017_audit_receipts.py`, `apps/web/src/routes/o.$orgSlug.records.tsx`; test `services/api/tests/audit/test_atomicity.py`, `test_receipt_rebuild.py`, `services/api/tests/records/test_scope_redaction.py`, `apps/web/tests/e2e/records.spec.ts`.

1. Add failing governed-state-without-audit, Receipt rebuild, cross-module port, pagination/link, redaction-canary, and unauthorized parity tests.
2. Add migration 0017; implement authoritative event/Receipt plus Records activity/run/tool/evaluation/policy/operation projections.
3. Run audit/Records/migration/contract/UI-state tests; expect exact scope/counts and no token/body/raw-reasoning leaks.
4. Record evidence; commit `feat: add authoritative audit and records` after authorization.

**Exit:** Receipt is reproducible from authoritative audit and Records leaks no protected content.

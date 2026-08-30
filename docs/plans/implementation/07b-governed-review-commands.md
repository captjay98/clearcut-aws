# Governed Review Commands Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement assignment, evidence decision, referral, and disposition through semantic services.  
**Architecture:** Drawer/page/API clients call the same application commands; governed writes commit with `AuditEvent`.  
**Tech Stack:** FastAPI, PostgreSQL, OpenAPI.

---

**Files:** Create `decisions/domain/models.py`, `decisions/application/commands.py`, `decisions/delivery/http.py`, `services/api/alembic/versions/0011_decisions_assignments.py`; test `services/api/tests/decisions/test_commands.py`, `test_atomic_audit.py`, `test_role_matrix.py`.

1. Add failing role/scope/rationale/version/idempotency/race/maker-checker/deactivation/audit-rollback tests using DG-02/DG-03.
2. Add migration 0011; implement `assignClearanceItem`, `recordEvidenceDecision`, `referClearanceItem`, and `setDisposition`.
3. Run decision/migration/contract/API-only tests; expect no generic status mutation and transaction rollback on audit failure.
4. Record evidence; commit `feat: add governed review commands` after authorization.

**Exit:** Governed commands cannot commit without current capability, intent, version, rationale, and audit.

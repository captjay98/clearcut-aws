# Identity and Opaque Sessions Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement normalized identity and revocable same-origin application sessions.  
**Architecture:** Identity adapters prove identity; PostgreSQL sessions and authorization remain core-owned.  
**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Argon2id, PostgreSQL.

---

**Files:** Create `services/api/src/clearcut/identity/domain/models.py`, `application/session_service.py`, `ports/identity_provider.py`, `adapters/local_identity.py`, `adapters/postgres.py`, `delivery/http.py`, `services/api/alembic/versions/0001_identity_sessions.py`; test `services/api/tests/identity/test_sessions.py`, `test_local_identity.py`, `tests/security/test_session_csrf.py`.

1. Add failing tests for Argon2id, generic credential errors, `__Host-` cookie, CSRF/Origin, fixation rotation, revocation, recovery, and production rejection of test adapters.
2. Add and test migration 0001 using `docs/DATABASE.md`; run identity tests and expect missing-model failures first.
3. Implement ports, local adapter, session service/repository, and semantic operations from `docs/API_OPERATIONS.md`.
4. Regenerate clients and run identity, migration, contract, and cross-origin negative tests; expect exit 0.
5. Record evidence; commit `feat: add revocable application sessions` after authorization.

**Exit:** Browser identity cannot supply roles/capabilities and no bearer credential is stored in browser storage.


# Organizations, Projects, and Resolver Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement atomic organization bootstrap, stable slugs, projects, and organization entry resolution.  
**Architecture:** Organization/project scope is explicit in repositories and generated operations.  
**Tech Stack:** FastAPI, SQLAlchemy, Alembic, PostgreSQL.

---

**Files:** Create `organizations/domain/models.py`, `organizations/application/bootstrap.py`, `organizations/adapters/postgres.py`, `organizations/delivery/http.py`, `projects/domain/models.py`, `projects/adapters/postgres.py`, `services/api/alembic/versions/0002_organizations_projects.py`; test `services/api/tests/organizations/test_bootstrap.py`, `test_resolver.py`, `services/api/tests/projects/test_scope.py`.

1. Write failing atomicity/idempotency tests for organization + Owner + defaults + optional outbox, stable slug, zero/one/many membership resolution, and cross-tenant project lookup.
2. Add migration 0002 with ownership tuples, UUIDv7, unique slug, and ownership-first indexes; test upgrade/downgrade.
3. Implement framework-free aggregates, scoped repositories, and `createOrganization`, `listOrganizations`, `createProject`, and resolver operations.
4. Run narrow tests, contract generation, and unknown/unauthorized timing-parity tests; expect exit 0.
5. Record evidence; commit `feat: add organization and project boundaries` after authorization.

**Exit:** No repository project read/write overload omits `org_id` and `project_id`.


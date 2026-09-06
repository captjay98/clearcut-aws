# Task 9 Spec Review Remediation Implementation Plan

> **For Kiro:** REQUIRED SUB-SKILLS: Use test-driven-development while implementing each task and verification-before-completion before reporting success.

**Goal:** Resolve every Task 9 spec-review finding with persisted, tenant-scoped, truthful behavior across API, contracts, generated clients, and browser flows.

**Architecture:** Preserve one idempotent durable job identity while appending immutable attempt/audit history for accountable retries. Promote the existing validated job payload target into a typed immutable public projection, add an attempt/lease-fenced monotonic progress boundary, align the items runtime route with OpenAPI, and add nullable canonical production columns through one additive migration so legacy project creation remains compatible.

**Tech Stack:** FastAPI, SQLAlchemy/Alembic, PostgreSQL/SQLite test compatibility, Pydantic, OpenAPI-generated TypeScript/Python clients, React/TanStack Query/Router, Playwright, pytest, Ruff, Pyright.

**Constraint:** Do not commit, call paid providers, or read/write `.clearcut/` directories.

---

### Task 1: Governed retry and immutable target contract

**Files:**
- Modify: `services/api/tests/operations/test_local_job_lifecycle.py`
- Modify: `services/api/tests/operations/test_job_http.py`
- Modify: `tests/contracts/test_generated_clients.py`
- Modify: `services/api/src/clearcut/operations/ports/job_repository.py`
- Modify: `services/api/src/clearcut/operations/adapters/sql_job_repository.py`
- Modify: `services/api/src/clearcut/operations/delivery/http.py`
- Modify: `packages/contracts/openapi.yaml`
- Regenerate: `packages/contracts/generated/typescript/index.ts`
- Regenerate: `packages/contracts/generated/python/__init__.py`

1. Add tests proving a cancelled detection job can only be retried through the authenticated mutation, is redispatched after commit, preserves its cancelled attempt, and creates a later attempt without changing idempotent job identity.
2. Add contract/API tests proving every public job has typed `target: { type, id }` and server-derived `canRetry`, with no raw payload exposure.
3. Run focused tests and capture RED failures.
4. Add immutable `JobTarget` to `JobRecord`, parse/validate it from the persisted payload, serialize it publicly, and expose retry eligibility.
5. Permit `cancelled` in the explicit repository retry transition while retaining audit and attempt history; keep duplicate automatic enqueue idempotent.
6. Regenerate clients and rerun focused tests to GREEN.

### Task 2: Lease-fenced truthful detection progress and browser lifecycle gating

**Files:**
- Modify: `services/api/tests/operations/test_local_job_lifecycle.py`
- Modify: `services/api/tests/detection/test_detection_job_execution.py`
- Modify: `services/api/src/clearcut/operations/ports/job_repository.py`
- Modify: `services/api/src/clearcut/operations/adapters/sql_job_repository.py`
- Modify: `services/api/src/clearcut/detection/application/run_detection_job.py`
- Modify: `services/api/src/clearcut/main.py`
- Modify: `apps/web/src/features/operations/JobProgress.tsx`
- Modify: `apps/web/tests/e2e/new-clearance-flow.spec.ts`

1. Add repository tests for monotonic bounded progress updates that require matching tenant, active running status, attempt number, lease owner, and unexpired lease, and reject terminal/expired/stale attempts.
2. Add detection service tests proving persisted stages transition through reading persisted elements, detecting candidates, and evaluating findings; no research stage is emitted; terminal status stops updates.
3. Add Playwright mismatch tests for queued and running wrong-type/wrong-version jobs and assert no cancel/retry/completion controls render.
4. Add browser assertions for persisted named stages, terminal polling stop, and cancelled explicit retry.
5. Run focused tests and capture RED failures.
6. Implement the typed progress port and SQL compare-and-set update, inject it into detection execution, and report only actual work boundaries with monotonic values.
7. Gate all rendering/polling/lifecycle controls on typed target identity before status-specific UI. Replace source-backed detection wording with detected unresolved findings pending evidence research.
8. Rerun focused tests to GREEN.

### Task 3: Real persisted clearance-item route

**Files:**
- Modify: `services/api/src/clearcut/items/delivery/http.py`
- Modify: `services/api/tests/items/test_items_http.py` (create if absent)
- Modify: `tests/contracts/test_mounted_operation_ids.py`
- Modify: `apps/web/src/routes/o/$orgSlug/projects/$projectId/items/index.tsx`
- Modify: `apps/web/tests/e2e/new-clearance-flow.spec.ts`

1. Add tenant-scoped API/contract tests for the canonical `listClearanceItems` path and generated response shape.
2. Add Playwright assertions that clicking Review detected items reaches `/items` and renders persisted items, plus loading/error/empty route coverage.
3. Run focused tests and capture RED failures.
4. Align the mounted handler path and camelCase response with OpenAPI and an explicit operation ID; count only actual evidence claims.
5. Implement the route with generated `api.listClearanceItems` and explicit loading/error/empty/list states.
6. Rerun focused tests to GREEN.

### Task 4: Persist canonical Describe production fields

**Files:**
- Create: `services/api/alembic/versions/0028_project_production_details.py`
- Modify: `services/api/tests/organizations/test_tenant_isolation.py`
- Modify: `services/api/tests/architecture/test_migrated_runtime_schema.py`
- Modify: `tests/contracts/test_generated_clients.py`
- Modify: `services/api/src/clearcut/organizations/delivery/http.py`
- Modify: `services/api/src/clearcut/projects/domain/models.py`
- Modify: `services/api/src/clearcut/projects/application/project_service.py`
- Modify: `services/api/src/clearcut/projects/adapters/sql_repository.py`
- Modify: `packages/contracts/openapi.yaml`
- Regenerate: `packages/contracts/generated/typescript/index.ts`
- Regenerate: `packages/contracts/generated/python/__init__.py`
- Modify: `apps/web/src/routes/o/$orgSlug/projects/new.tsx`
- Modify: `apps/web/tests/e2e/new-clearance-flow.spec.ts`

1. Add API, migration, contract, and browser tests for production type, stage, jurisdiction, target lock date, and review brief, including reload and old title-only creation compatibility.
2. Run focused tests and capture RED failures.
3. Add nullable columns in one additive migration with a reversible downgrade.
4. Extend typed domain/repository/API/OpenAPI models and generated clients without using the description blob; retain tenant predicates on reads/writes.
5. Add canonical form controls and render persisted values after create/reload.
6. Regenerate clients and rerun focused tests to GREEN.

### Task 5: Verification and self-review

1. Run focused API/contract tests for changed behavior.
2. Run Task 9 Playwright tests.
3. Run the web build.
4. Run Ruff and Pyright on changed Python scope.
5. Run `git diff --check`.
6. Inspect the final diff for tenant scoping, CSRF/accountable actions, immutable attempt history, lease fencing, additive migration compatibility, generated-client drift, absence of fabricated evidence/provider calls, and absence of legal conclusions.
7. Report exact RED and GREEN commands/results and all changed files. Do not commit.

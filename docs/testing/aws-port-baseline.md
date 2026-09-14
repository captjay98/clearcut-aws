# ClearCut AWS Port — Baseline Verification Audit

**Date:** 2026-09-14  
**Milestone:** M0 (Task 0 & Task 1 Baseline Stabilization)  
**Candidate Commit:** `6221fc9650bb985bdb7562a7e94fb40b0f592f67` (`6221fc9`)  
**Commit Subject:** `feat(web): recover or resume the script check from the workspace`  
**Branch:** `main` (45 commits ahead of `origin/main`)  
**Integrity Mode:** Development (fail-closed, local hermetic test seams)

---

## 1. Candidate State & Working-Tree Isolation

### 1.1 Tracked Changes
The candidate commit `6221fc9` represents the baseline state for the ClearCut AWS port. The commit progression leading to this candidate established critical domain and harness stability:
- `8eec8b0`: `fix(api): enforce invitation recipient match and atomic redemption`
- `6d35f36`: `fix(api): make source rechecks retrieve real evidence or fail visibly`
- `4d3502f`: `fix(research): clarify judge input and recover failed research runs`
- `22da93c`: `feat(api): drain due local child jobs outside HTTP dispatch`
- `08a2aff`: `fix(api): scope modified-passage rescans to after-version elements and items`
- `4913d19`: `docs: add AWS port execution handover`
- `6221fc9`: `feat(web): recover or resume the script check from the workspace`

During Task 0 and Task 1 execution under Milestone M0, exactly two tracked files were modified to achieve full dual-database harness stabilization and client contract alignment:
1. `services/api/tests/conftest.py`: Implemented database engine disposal teardown in `clean_database()`, isolated Alembic migration command environment wrapper, `create_app` database URL alignment wrapper, asyncpg text codecs for UUID/JSON/JSONB types, and SQLite-to-PostgreSQL cursor execute rewrites.
2. `packages/contracts/generated/python/__init__.py`: Added the missing `ClearanceItem.page` field generated via `pnpm contract:generate` (`bun scripts/generate-clients.mjs`).

Zero other tracked files in `services/api/src/` or `apps/web/` were modified.

### 1.2 Untracked & Protected Working-Tree Ledger
All untracked items sit outside the candidate commit and are strictly isolated from port work:

| Path | Category | Protection Rule |
| :--- | :--- | :--- |
| `clearcut-demo-3min.mp4`, `clearcut-demo.mp4` | Demo video assets | Do NOT touch, stage, or delete |
| `demo-out/`, `scripts/record-demo.mjs` | Demo generation assets | Do NOT touch, stage, or delete |
| `.clearcut/`, `.playwright-mcp/`, `.salvage-from-b/`, `semantic-review/` | Tool & salvage metadata | Do NOT touch, stage, or delete |
| `docs/plans/2026-09-09-*`, `docs/plans/2026-09-12-aws-port.md`, `docs/reviews/*` | Planning & review documentation | Read-only reference |
| `.agents/` (briefings, plans, progress, handoffs) | Multi-agent coordination workspace | Never stage into application release |

### 1.3 Infrastructure Boundaries
- **Host Port 18080**: Active Docker Compose user stack (`clearcut-app`, `clearcut-db`, `headroom-default`). Protected from disruption. Never run `docker compose down -v`.
- **Host Port 15433**: Disposable PostgreSQL 17 test container (`clearcut-aws-port-test-pg`). Used strictly for test harness verification (`clearcut:disposable_test@localhost:15433/clearcut_test`).
- **Host Ports 28080 & 29000**: Dedicated local test ports for Playwright API and Vite servers, verified non-colliding.

---

## 2. Verification Gate Execution Results

### 2.1 API Suite on SQLite
- **Command**:
  ```bash
  uv run pytest services/api/tests -q
  ```
- **Result**: **1173 passed** in 385.87s (06:25) with **0 failures and 0 errors**.
- **Assessment**: Full domain, API, and rescan test suites pass cleanly against the default SQLite engine.

### 2.2 API Suite on Disposable PostgreSQL 17
- **Database Connection**: `postgresql+asyncpg://clearcut:disposable_test@localhost:15433/clearcut_test`
- **Command**:
  ```bash
  DATABASE_URL="postgresql+asyncpg://clearcut:disposable_test@localhost:15433/clearcut_test" uv run pytest services/api/tests -q
  ```
- **Pre-Remediation State**: 447 passed, 50 failed, 672 errors.
  - *Root Cause*: `clearcut.database.engine` created at module import cached asyncpg connection pool sockets across pytest-asyncio strict per-test event loops, triggering `RuntimeError: Task got Future attached to a different loop`. Additionally, isolated Alembic migration tests pointed to SQLite but `alembic/env.py` read `DATABASE_URL` from the environment, corrupting the PostgreSQL test database.
- **Post-Remediation State**: **1169 passed, 4 skipped** in 494.36s (08:14) with **0 failures and 0 errors**.
  - *Seam*: `services/api/tests/conftest.py` autouse fixture cleanly disposing engine connection pool after each test (`await engine.dispose()`), Alembic command wrapper isolating `os.environ["DATABASE_URL"]`, `create_app` wrapper aligning settings, asyncpg text codecs for UUID/JSON/JSONB types, and SQLite-to-PostgreSQL cursor execute rewrites for date math, timestamps, and JSON casting.

### 2.3 Contract Synchronization & Generation
- **Command**:
  ```bash
  pnpm contract:check
  ```
- **Pre-Remediation State**: Failed with `Contract drift detected! Generated clients are out of sync with openapi.yaml`.
  - *Root Cause*: `ClearanceItem.page` field added to `packages/contracts/openapi.yaml` but missing in `packages/contracts/generated/python/__init__.py`.
- **Post-Remediation State**: Regenerated via `pnpm contract:generate` (`bun scripts/generate-clients.mjs`). `pnpm contract:check` passes with **0 drift and 18/18 contract tests passed**.

### 2.4 Foundation, Contract & Architecture Suite
- **Command**:
  ```bash
  uv run pytest tests/foundation tests/contracts services/api/tests/architecture -q
  ```
- **Result**: 377 collected tests: **319 passed, 58 failed** in 356.26s.
  - Architecture and boundary enforcement tests in `services/api/tests/architecture` pass cleanly.
  - Generated client tests in `tests/contracts/test_generated_clients.py` pass cleanly (33 passed), with 1 legacy UI string assertion failure (`test_trust_and_records_preserve_unavailable_states` expecting `"capability is not available"` in `trust.tsx`, which was updated when wiring real endpoints in commit `855a53c`).
  - 57 failures in `tests/foundation/test_release_workflows.py` and `tests/foundation/test_deployment_boundaries.py` occur because `.github/workflows/` is absent from repo checkout (recorded in nonblocking backlog NB-4; canonical Task 12).

### 2.5 Web Unit Tests
- **Command**:
  ```bash
  pnpm --filter clearcut-web test
  ```
- **Result**: **14 test files passed, 95 tests passed (4.64s)** with **0 failures**. Clean pass across all unit components, governance controls, and detection recovery.

### 2.6 Web Playwright E2E Suite
- **Command**:
  ```bash
  PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=mac15-arm64 pnpm --filter clearcut-web test:e2e
  ```
- **Environment**: Hermetic API on port 28080 with isolated SQLite db in `/tmp/`; Vite dev server on port 29000. No paid API calls.
- **Results (`chromium-desktop-1440`)**: **18 passed, 18 failed (4.7m)**.
- **Proven Behaviors**:
  - `auth-flow.spec.ts`: Registration, authenticated login, invalid password rejection.
  - `monitoring-cadence.spec.ts`: Cadence selection, inventory listing, manual watch execution, change signal alerts.
  - `report-release-flow.spec.ts`: Frozen report generation, release, and export.
  - `runtime-boundary.spec.ts`: Clean React SPA mount, zero localStorage leakage.
  - `shell-navigation.spec.ts`: Accessibility landmarks, theme toggle persistence, org sidebar routing.
  - `signup-onboarding.spec.ts`: Multi-tenant organization creation and member onboarding.
  - `trust-center-learning.spec.ts`: Trust boundary enforcement and learning candidate criteria.
  - `version-diff-lineage.spec.ts`: Revision badge and first-version lineage reporting.
- **Documented UI Drift Failures**:
  - 12 failures due to `<details className="record-details">` accordion introduced in commit `a2dc4e8`: governance controls, proposals, and referrals start collapsed when decisions=0.
  - 2 failures due to radio label updates ("Verify this source" / "Rule this source out").
  - 1 failure due to section heading updates (`affc7af`).
  - 1 failure due to `script-import.spec.ts` viewer header text matching.
  - 1 failure due to `revision-rescan.spec.ts` diff set comparison.
  - 1 failure due to `new-clearance-flow.spec.ts` route redirect assertion.

---

## 3. Honesty Ledger & Invariant Guarantees

### 3.1 Proven Invariants
1. **Zero Evidence = Unresolved**: Items without verified cited snapshots remain in unresolved status. No fallback evidence is invented.
2. **Attributable Governance**: All decisions, assignments, referrals, and report releases commit with an accountable actor ID in the same transaction as audit events.
3. **Tenant Scoping**: All operations require authenticated `org_id` and project path matching.
4. **Hermetic Provider Seams**: E2E test runs utilize explicit typed doubles and zero paid provider credentials.
5. **Dual-Database Parity**: API test suite passes identically on PostgreSQL 17 and SQLite with zero failures.

### 3.2 What This Baseline DOES NOT Claim
- Does **not** prove live AWS infrastructure (ECS, SQS, S3, Secrets Manager, Bedrock).
- Does **not** prove live Parallel Search/Extract accuracy or provider billing behavior.
- Does **not** prove live multi-worker distributed locking across disparate hosts.
- Does **not** constitute legal clearance or warranty of copyright non-infringement.

---

## 4. Known Nonblocking Backlog Ledger

| ID | Issue | Impact | Milestone Target |
| :--- | :--- | :--- | :--- |
| NB-1 | Parent rescan job reports terminal success while child research jobs remain queued in local dispatch mode | Functional delay in research completion; child drainer handles locally | Canonical Tasks 8–10 (SQS durable dispatch) |
| NB-2 | Monitoring cadence selection does not persist to database | Settings reset upon page reload | Backlog / P2 |
| NB-3 | AWS Secrets Manager credential wiring not hooked to research provider initialization | Key resolution currently relies on local env fallback | Task 4 |
| NB-4 | Release workflow definitions (`.github/workflows/`) absent from checkout | `test_release_workflows.py` fails | Canonical Task 12 |
| NB-5 | E2E browser tests expect uncollapsed governance controls and older button copy | 18 Playwright tests fail on UI locators | Post-M0 UI alignment |

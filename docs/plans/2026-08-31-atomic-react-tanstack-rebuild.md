# Atomic React and TanStack Rebuild Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the mock-derived browser runtime with a fully server-authoritative React/TanStack application and complete every product capability before one atomic production cutover.

**Architecture:** Build the replacement in an isolated worktree. TanStack Start, Router, and Query consume an executable generated OpenAPI client over the same-origin `/api/v1` boundary; FastAPI application services own domain behavior, organization/project scope, persistence, providers, and transactional audit events. Delete the legacy runtime at the beginning of the replacement branch and never add compatibility behavior or fixture fallbacks.

**Tech Stack:** React 18, TanStack Start/Router/Query, Vite 8, TypeScript, ClearCut design system, FastAPI, Pydantic, SQLAlchemy, PostgreSQL, Alembic, OpenAPI 3.1, Vitest/Testing Library, Playwright/axe, pytest.

---

## Governing inputs

Read these before starting and stop if they conflict:

- `docs/plans/2026-08-31-atomic-react-tanstack-rebuild-design.md`
- `docs/ARCHITECTURE.md`
- `docs/API_OPERATIONS.md`
- `docs/UI_SURFACE_CONTRACT.md`
- `docs/UI_STATE_MATRIX.md`
- `docs/plans/implementation/README.md`
- `AGENTS.md`

The packet files under `docs/plans/implementation/` remain useful file inventories and domain acceptance references. Their old `PASSED` evidence is not proof of reachable behavior. Reopen each packet named below and satisfy its exit criteria against the replacement runtime.

## Non-negotiable execution rules

1. Work in an isolated worktree and feature branch. Do not deploy the branch until Task 16 passes.
2. Delete `apps/web/src/runtime.js` before building the replacement. Do not copy or translate its router, reducer, timers, local receipts, or local-storage state.
3. Do not import product fixtures from production code or return fixed success-shaped product responses.
4. Do not invent evidence. An `EvidenceClaim` requires a persisted cited `SourceSnapshot`; zero evidence is unresolved.
5. Enforce authenticated `org_id` and project ownership on every project-owned operation.
6. Commit governed domain changes and immutable `AuditEvent` rows in one transaction.
7. Protected rules remain human-only. This implementation may expose authorized read/write workflows but may not autonomously change permissions, approval policy, categories, authority tiers, evidence schemas, blocking rules, retention/privacy settings, or legal-boundary language.
8. Run the narrow failing test before implementation, then the narrow passing test, then the packet gate.
9. Create commits only after explicit user authorization. Suggested commit messages below are checkpoints, not permission.

## Pinned frontend dependency target

At plan creation on 2026-08-31, registry metadata reported these compatible targets to validate and pin exactly in the lockfile:

```text
@tanstack/react-start@1.168.49
@tanstack/react-router@1.170.32
@tanstack/react-query@5.102.8
@tanstack/router-plugin@1.168.35
vite@8.2.2
@vitejs/plugin-react@6.1.1
vitest@4.1.11
@testing-library/react@16.3.3
@testing-library/user-event@14.6.6
jsdom@30.0.1
nitro@3.0.260610-beta
```

Before installation, run `pnpm view <package>@<version> peerDependencies --json` for the complete set. Stop rather than selecting an unpinned replacement if peer requirements conflict. TanStack Start requires Vite 7 or newer; the current Vite 5 setup is not sufficient.

### Task 1: Create the isolated replacement worktree and record the truthful baseline

**Files:**
- Create: `docs/reviews/2026-08-31-atomic-rebuild-baseline.md`
- Modify: `docs/reviews/2026-08-30-06b-evidence.md`
- Modify: other `docs/reviews/2026-08-30-*-evidence.md` files only where they claim reachable frontend completion

**Step 1: Create the worktree**

Run from the repository root after selecting a branch name:

```bash
git worktree add ../clearcut-atomic-react -b feat/atomic-react-tanstack-rebuild
```

Expected: a clean worktree on the new branch. If the branch or directory already exists, stop and inspect it; do not delete it.

**Step 2: Capture the baseline evidence**

Record exact commands and output for:

```bash
git status --short
pnpm --filter clearcut-web build
pnpm --filter clearcut-web test
uv run pytest tests/contracts services/api/tests -q
```

Expected: record actual results without converting failures into non-claims.

**Step 3: Mark unsupported evidence as superseded**

Add a prominent supersession note to evidence packs that claimed TanStack/reachable completion. Link to the approved design and baseline. Preserve historical text; do not rewrite history.

**Step 4: Verify documentation consistency**

Run:

```bash
git diff --check -- docs/reviews
```

Expected: exit 0.

**Checkpoint:** Request authorization before `docs: record atomic rebuild baseline`.

### Task 2: Add executable no-legacy and architecture gates

**Files:**
- Create: `scripts/check-no-legacy-runtime.mjs`
- Create: `tests/foundation/test_web_runtime_boundary.py`
- Modify: `package.json`
- Modify: `scripts/verify-submission.mjs`

**Step 1: Write the failing boundary test**

The test must scan production web source and fail for:

```python
PROHIBITED = {
    "runtime import": 'import "./runtime.js"',
    "hash routing": "window.location.hash",
    "test fixture import": "tests/fixtures",
    "domain local storage": "clearcut-flow-state",
}
```

It must also assert that `apps/web/src/runtime.js` does not exist and that no production source imports `runtime.js`.

**Step 2: Run the test and confirm the intended failure**

```bash
uv run pytest tests/foundation/test_web_runtime_boundary.py -q
```

Expected: FAIL because `main.tsx` imports `runtime.js` and the file exists.

**Step 3: Add the Node architecture check**

Implement a deterministic scanner with explicit allowlists for generated transport and theme-only local storage. It must reject direct `fetch(` in `apps/web/src` except the generated transport directory.

**Step 4: Wire the gate into root verification**

Add `check:no-legacy` and include it in `verify` and submission verification.

**Step 5: Leave the gate red until Task 4**

Do not weaken patterns to make the current implementation pass.

**Checkpoint:** Request authorization before `test: enforce replacement runtime boundaries`.

### Task 3: Repair the OpenAPI contract and generate an executable client

**Packets reopened:** `01b-contracts-generated-clients.md`, all later packets that own operations.

**Files:**
- Modify: `package.json`
- Modify: `packages/contracts/openapi.yaml`
- Modify: `packages/contracts/schemas/error.json`
- Modify: `scripts/generate-clients.mjs`
- Replace generated output: `packages/contracts/generated/typescript/`
- Replace generated output: `packages/contracts/generated/python/`
- Modify: `packages/contracts/README.md`
- Modify: `tests/contracts/test_openapi.py`
- Modify: `tests/contracts/test_operation_inventory.py`
- Create: `tests/contracts/test_generated_clients.py`

**Step 1: Write failing executable-client assertions**

Assert that every operation ID in `docs/API_OPERATIONS.md` exists and that generated TypeScript exports a callable operation with typed success and error results—not only metadata.

**Step 2: Run contract tests**

```bash
uv run pytest tests/contracts -q
```

Expected: FAIL because current TypeScript output is not an executable client and required operations/errors are incomplete.

**Step 3: Normalize contract boundaries**

For each operation, define:

- opaque cookie session security;
- organization/project path parameters where ownership applies;
- typed request and success body;
- shared typed error envelope;
- idempotency key for retryable writes;
- canonical run/job status;
- pagination for unbounded lists.

Do not add an operation until its owning backend task is scheduled below.

**Step 4: Generate a same-origin TypeScript transport**

The public client shape must force callers to handle typed errors, for example:

```ts
export type ApiResult<T, E extends ApiError = ApiError> =
  | { ok: true; value: T }
  | { ok: false; error: E };
```

The transport uses relative `/api/v1` URLs and `credentials: "include"`. It does not swallow errors or return `{ data: {} }`.

**Step 5: Prove deterministic generation**

```bash
pnpm contract:lint
pnpm contract:generate
pnpm contract:generate
git diff --exit-code -- packages/contracts/generated
pnpm contract:check
uv run pytest tests/contracts -q
```

Expected: all commands pass and the second generation produces no diff.

**Checkpoint:** Request authorization before `feat: generate executable api clients`.

### Task 4: Hard-delete the legacy frontend and establish TanStack Start

**Packets reopened:** `01c-shells-boundaries-ci.md`, `06b-site-web-shell.md`.

**Files:**
- Delete: `apps/web/src/runtime.js`
- Delete: `apps/web/src/App.tsx`
- Delete: `apps/web/src/lib/loaders.ts`
- Replace: `apps/web/index.html` if TanStack Start generation no longer uses it
- Replace: `apps/web/src/main.tsx` with framework entry files required by the selected Start version
- Modify: `apps/web/package.json`
- Modify: `apps/web/vite.config.ts`
- Create: `apps/web/src/router.tsx`
- Create: `apps/web/src/integrations/tanstack-query/root-provider.tsx`
- Replace: `apps/web/src/routes/__root.tsx`
- Create: `apps/web/src/routes/index.tsx`
- Create: `apps/web/tests/e2e/runtime-boundary.spec.ts`

**Step 1: Write a failing browser reachability test**

The test must load `/`, assert a React-rendered root marker, navigate to a typed route, refresh it, and assert no legacy storage key or hash route appears.

**Step 2: Run it against the current app**

```bash
pnpm --filter clearcut-web test:e2e -- runtime-boundary
```

Expected: FAIL because the current app executes `runtime.js` and has no TanStack route tree.

**Step 3: Pin and install the validated dependencies**

Use exact versions only. Update the lockfile with `pnpm --save-exact`; do not preserve open ranges for newly added packages.

**Step 4: Configure TanStack Start**

Configure the Start plugin before the React plugin:

```ts
import { tanstackStart } from "@tanstack/react-start/plugin/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [tanstackStart(), react()],
});
```

Adapt only as required by the pinned version's official API.

**Step 5: Create the root route and Query context**

Use `createRootRouteWithContext<{ queryClient: QueryClient }>()`, `HeadContent`, `Outlet`, and `Scripts`. Configure Query defaults so governed writes never retry automatically and ordinary reads retry only typed retryable failures.

**Step 6: Delete legacy files and production fixture imports**

Remove the files listed above. Do not migrate their behavior.

**Step 7: Run the architecture and build gates**

```bash
pnpm check:no-legacy
pnpm --filter clearcut-web build
pnpm --filter clearcut-web test:e2e -- runtime-boundary
```

Expected: pass; a production bundle search finds no `clearcut-flow-state-v2` or legacy prototype banner.

**Checkpoint:** Request authorization before `feat: replace legacy runtime with tanstack start`.

### Task 5: Make sessions, repositories, and tenant scope production-authoritative

**Packets reopened:** `02a-identity-sessions.md`, `02b-organizations-projects.md`, `02c-memberships-invitations.md`.

**Files:**
- Modify: `services/api/src/clearcut/main.py`
- Modify: `services/api/src/clearcut/database.py`
- Replace in-memory composition under: `services/api/src/clearcut/identity/adapters/`
- Replace in-memory composition under: `services/api/src/clearcut/organizations/adapters/`
- Replace in-memory composition under: `services/api/src/clearcut/projects/adapters/`
- Modify services under: `services/api/src/clearcut/identity/application/`
- Modify services under: `services/api/src/clearcut/organizations/application/`
- Modify services under: `services/api/src/clearcut/projects/application/`
- Modify delivery: `services/api/src/clearcut/identity/delivery/http.py`
- Modify delivery: `services/api/src/clearcut/organizations/delivery/http.py`
- Test: `services/api/tests/identity/`, `organizations/`, `projects/`, `bootstrap/`

**Step 1: Add failing persistence and isolation tests**

Cover restart-safe sessions, invitation persistence, organization membership, project ownership, last-owner protection, CSRF/origin behavior, and cross-organization denial.

**Step 2: Run narrow tests**

```bash
uv run pytest services/api/tests/identity services/api/tests/organizations services/api/tests/projects services/api/tests/bootstrap -q
```

Expected: FAIL on in-memory composition, fixed responses, or missing scope checks.

**Step 3: Implement SQL repositories and request scope**

Construct one authenticated scope object per request containing user, organization membership, project when applicable, role/capabilities, and active policy reference. Application services accept this typed scope; delivery handlers do not substitute rows on lookup failure.

**Step 4: Remove in-memory production wiring**

In-memory adapters may remain test-only. `main.py` must compose SQL-backed repositories in production.

**Step 5: Run tests and migration checks**

```bash
uv run pytest services/api/tests/identity services/api/tests/organizations services/api/tests/projects services/api/tests/bootstrap -q
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
```

Expected: all pass against an isolated test database.

**Checkpoint:** Request authorization before `feat: persist sessions and tenant scope`.

### Task 6: Implement the labeled server-owned demo dataset

**Files:**
- Replace ad hoc seeding in: `services/api/src/clearcut/init_db.py`
- Modify or replace: `services/api/scripts/seed_db.py`
- Create: `services/api/src/clearcut/bootstrap/application/demo_dataset.py`
- Create: `services/api/src/clearcut/bootstrap/domain/demo.py`
- Modify relevant migrations under: `services/api/alembic/versions/`
- Test: `services/api/tests/bootstrap/test_demo_dataset.py`
- Test: `services/api/tests/conformance/test_demo_normal_paths.py`

**Step 1: Write failing idempotency and labeling tests**

Run bootstrap twice and assert one labeled demo organization/project exists, all records have valid ownership, and claims reference persisted source snapshots.

**Step 2: Verify failure**

```bash
uv run pytest services/api/tests/bootstrap/test_demo_dataset.py services/api/tests/conformance/test_demo_normal_paths.py -q
```

Expected: FAIL because current seed data is not modeled as an explicit normal-path demo dataset.

**Step 3: Implement idempotent bootstrap through application services**

Do not insert orphaned or presentation-only rows. The demo resource marker is persisted and exposed by contracts.

**Step 4: Prove normal-path access**

Use authenticated API calls to list, read, and mutate permitted demo resources. Do not use a frontend demo shortcut.

**Step 5: Run tests**

Expected: both tests pass and a second bootstrap creates no duplicates.

**Checkpoint:** Request authorization before `feat: add server-owned demo dataset`.

### Task 7: Build the authenticated TanStack shell and identity/organization routes

**Packets reopened:** `02d-identity-entry-ui.md`, `06b-site-web-shell.md`.

**Files:**
- Replace routes under: `apps/web/src/routes/auth/`
- Replace: `apps/web/src/routes/onboarding.tsx`
- Replace routes under: `apps/web/src/routes/o/$orgSlug/`
- Modify: `apps/web/src/components/navigation/Header.tsx`
- Modify: `apps/web/src/components/navigation/Sidebar.tsx`
- Create: `apps/web/src/auth/session.ts`
- Create: `apps/web/src/queries/session.ts`
- Create: `apps/web/src/queries/organizations.ts`
- Create: `apps/web/src/mutations/identity.ts`
- Create: `apps/web/src/mutations/organizations.ts`
- Test: `apps/web/tests/e2e/identity-entry.spec.ts`
- Test: `apps/web/tests/e2e/tenant-navigation.spec.ts`

**Step 1: Write failing direct-navigation and role tests**

Exercise sign-in, sign-out, invite acceptance, onboarding, organization selection, team access, forbidden routes, unknown organization, refresh, and browser back/forward.

**Step 2: Run the tests**

Expected: FAIL because routes are not yet TanStack route modules backed by the generated client.

**Step 3: Implement route loaders and query options**

Session and organization loaders call generated operations and throw typed redirects/errors. Route parameters, not browser storage, establish scope.

**Step 4: Implement mutations without fake success**

On failure, retain the form and show the typed error. Invalidate only affected query keys after a confirmed success.

**Step 5: Run API-connected browser tests**

```bash
pnpm --filter clearcut-web test:e2e -- identity-entry tenant-navigation
```

Expected: pass against the real API and database.

**Checkpoint:** Request authorization before `feat: add authenticated tanstack workspace shell`.

### Task 8: Complete script ingestion, parsing, versions, and analysis-run control

**Packets reopened:** `03a-upload-artifacts.md`, `03b-parsers-immutable-v1.md`, `03c-ingestion-ui.md`.

**Files:**
- Complete backend under: `services/api/src/clearcut/scripts/`
- Complete run orchestration under: `services/api/src/clearcut/operations/`
- Add migrations for uploads, artifacts, scripts, versions, scenes, parse warnings, and jobs
- Replace frontend: `apps/web/src/features/ingestion/`
- Replace route: `apps/web/src/routes/o/$orgSlug/projects/new.tsx`
- Replace route: `apps/web/src/routes/o/$orgSlug/projects/$projectId/workspace.tsx`
- Test: `services/api/tests/scripts/`
- Create: `apps/web/tests/e2e/ingestion.spec.ts`

**Step 1:** Add failing tests for upload capability, finalize, parser outcomes, immutable v1, duplicate idempotency, scoped reads, and unsupported formats.

**Step 2:** Run `uv run pytest services/api/tests/scripts -q`; expect failures on missing persistence/integration.

**Step 3:** Implement storage and parser ports with typed outcomes. Persist artifacts and versions; never pretend to read a browser-selected file.

**Step 4:** Implement generated-client upload/finalize/progress routes with explicit pending, warning, failure, and success states.

**Step 5:** Run backend and Playwright ingestion tests; expect pass.

**Checkpoint:** Request authorization before `feat: implement real script ingestion`.

### Task 9: Complete detection, research, source snapshots, claims, and item read models

**Packets reopened:** `04a`, `04b`, `05a`, `05b`, `05c`, `07a`.

**Files:**
- Complete: `services/api/src/clearcut/detection/`
- Complete: `services/api/src/clearcut/research/`
- Complete: `services/api/src/clearcut/evidence/`
- Replace SQL reads in: `services/api/src/clearcut/items/delivery/http.py`
- Add provider adapters and migrations owned by the packets
- Test: `services/api/tests/detection/`, `research/`, `evidence/`, `items/`, `evaluation/`

**Step 1:** Add failing provider-contract, provenance, zero-evidence, partial-outcome, conflict, authority, pagination, and tenant-isolation tests.

**Step 2:** Run the five test directories; expect failures on hermetic/fixed behavior and unscoped item reads.

**Step 3:** Implement typed provider ports and persisted run state. Parallel Search is mandatory; bounded Extract enriches only cited snapshots. Provider errors create visible review outcomes.

**Step 4:** Build orthogonal item projections from persisted domain state. Do not manufacture severity, confidence, source, excerpt, or display IDs in the browser.

**Step 5:** Run provider contract tests, database integration tests, and contract drift checks; expect pass.

**Checkpoint:** Request authorization before `feat: implement sourced detection and research`.

### Task 10: Complete the evidence workspace and governed collaboration commands

**Packets reopened:** `07b-governed-review-commands.md`, `07c-comments-events.md`, `07d-evidence-workspace-ui.md`.

**Files:**
- Complete: `services/api/src/clearcut/decisions/`
- Complete: `services/api/src/clearcut/collaboration/`
- Replace: `services/api/src/clearcut/items/delivery/http.py`
- Replace routes under: `apps/web/src/routes/o/$orgSlug/projects/$projectId/items/`
- Replace: `apps/web/src/routes/o/$orgSlug/projects/$projectId/index.tsx`
- Replace evidence features under: `apps/web/src/features/evidence/`
- Create queries/mutations under: `apps/web/src/queries/`, `apps/web/src/mutations/`
- Test: `services/api/tests/decisions/`, `collaboration/`, `audit/`, `items/`
- Test: `apps/web/tests/e2e/evidence-workspace.spec.ts`
- Test: `apps/web/tests/e2e/evidence-access.spec.ts`

**Step 1:** Write failing tests for evidence decisions, assignment, comments, mentions, referrals, dispositions, capability denial, concurrent updates, and audit atomicity.

**Step 2:** Confirm the current fallback-to-first-item behavior fails the tests.

**Step 3:** Implement commands against exact scoped IDs. Use transactions and immutable events. No governed mutation uses optimistic UI updates.

**Step 4:** Implement worklist/detail routes with persisted claims and source snapshots, explicit zero-evidence state, conflict display, and role explanations.

**Step 5:** Run API and multi-user Playwright tests; expect pass.

**Checkpoint:** Request authorization before `feat: implement governed evidence workspace`.

### Task 11: Complete rewrites, immutable revisions, diffs, and selective rescans

**Packets reopened:** `08a-rewrite-maker-checker.md`, `08b-diff-selective-rescan.md`, `08c-versions-ui.md`.

**Files:**
- Complete: `services/api/src/clearcut/rewrites/`
- Complete: `services/api/src/clearcut/versions/`
- Complete: `services/api/src/clearcut/rescan/`
- Replace: `apps/web/src/routes/o/$orgSlug/projects/$projectId/versions.tsx`
- Replace: `apps/web/src/features/versions/`
- Test: `services/api/tests/rewrites/`, `versions/`, `rescan/`
- Test: `apps/web/tests/e2e/versions-rescan.spec.ts`

**Step 1:** Add failing maker/checker, immutable lineage, diff, affected-item selection, untouched-item, run-failure, and rollback tests.

**Step 2:** Verify failures against current local/timer behavior.

**Step 3:** Implement persisted proposals, approvals, versions, diffs, and jobs with typed states.

**Step 4:** Implement TanStack routes that poll/query authoritative job state; do not use browser timers to simulate progression.

**Step 5:** Run backend and browser tests; expect pass.

**Checkpoint:** Request authorization before `feat: implement governed revisions and rescans`.

### Task 12: Complete monitoring and notifications

**Packets reopened:** `09a`, `09b`, `09c`, `09d`.

**Files:**
- Complete: `services/api/src/clearcut/monitoring/`
- Complete notification persistence/delivery under: `services/api/src/clearcut/collaboration/`
- Replace: `apps/web/src/routes/o/$orgSlug/projects/$projectId/watch.tsx`
- Replace: `apps/web/src/routes/o/$orgSlug/notifications.tsx`
- Replace: `apps/web/src/features/watch/`
- Replace: `apps/web/src/features/notifications/`
- Test: `services/api/tests/monitoring/`, `notifications/`
- Test: `apps/web/tests/e2e/watch-notifications.spec.ts`

**Step 1:** Add failing schedule, provider state, webhook verification, Search/Extract recheck, materiality, governed review, recipient projection, read-state, and tenant-isolation tests.

**Step 2:** Confirm fixed endpoint responses and local inbox behavior fail.

**Step 3:** Persist watch configuration, runs, deltas, reviews, and notifications. Use scheduler/task ports with typed failures.

**Step 4:** Implement generated-client routes and mutations. Browser notification permission is optional presentation behavior, not delivery proof.

**Step 5:** Run backend and browser tests; expect pass.

**Checkpoint:** Request authorization before `feat: implement monitoring and notifications`.

### Task 13: Complete records, trust/evaluation, learning, settings, retention, and deletion

**Packets reopened:** `10a-audit-records.md`, `10b-trust-learning.md`, `10c-settings-deletion.md`.

**Files:**
- Complete: `services/api/src/clearcut/records/`
- Complete: `services/api/src/clearcut/evaluation/`
- Complete: `services/api/src/clearcut/learning/`
- Complete deletion/retention modules owned by packet 10c
- Replace: `apps/web/src/routes/o/$orgSlug/records.tsx`
- Replace: `apps/web/src/routes/o/$orgSlug/trust.tsx`
- Replace: `apps/web/src/routes/o/$orgSlug/settings.tsx`
- Replace corresponding features under: `apps/web/src/features/`
- Test: `services/api/tests/records/`, `audit/`, `evaluation/`, `learning/`, `deletion/`
- Test: `apps/web/tests/e2e/governance.spec.ts`

**Step 1:** Add failing tests for authoritative audit projection, org scope, immutable protected configuration, candidate/shadow/canary/promote/rollback, retention authorization, and deletion lifecycle.

**Step 2:** Confirm fixed rubric/settings and browser-only promotion fail.

**Step 3:** Implement persisted organization-scoped configuration and governed workflows. Do not allow automated modification of protected rules.

**Step 4:** Implement read and command routes with capability explanations and typed confirmations.

**Step 5:** Run all backend and browser governance tests; expect pass.

**Checkpoint:** Request authorization before `feat: implement records trust and settings`.

### Task 14: Complete report snapshot, release, export, and print

**Packets reopened:** `11a-report-snapshot.md`, `11b-report-release-export.md`, `11c-report-ui-print.md`.

**Files:**
- Complete: `services/api/src/clearcut/export/`
- Replace: `services/api/src/clearcut/export/delivery/http.py`
- Replace: `apps/web/src/routes/o/$orgSlug/projects/$projectId/report.tsx`
- Replace: `apps/web/src/features/report/`
- Test: `services/api/tests/reports/`, `audit/`
- Test: `apps/web/tests/e2e/report-release.spec.ts`
- Test: `apps/web/tests/e2e/report-print.spec.ts`

**Step 1:** Add failing version-bound snapshot, provenance, unresolved-risk, maker/reviewer, transactional release, deterministic render, supersession, download, and cross-tenant tests.

**Step 2:** Confirm fixed `snap-001`/`rel-001` responses fail.

**Step 3:** Implement draft generation and governed release through application services. Generation/release and the immutable audit event commit atomically. Store rendered artifacts through the storage port.

**Step 4:** Implement preview/release/download/print routes. Never present a draft as released.

**Step 5:** Run report, audit, Playwright, and deterministic-render tests; expect pass.

**Checkpoint:** Request authorization before `feat: implement governed dossier release`.

### Task 15: Re-establish design-system, accessibility, and route-state parity

**Packets reopened:** `06a-design-system-mock-contract.md`, `06c-ui-quality-gates.md`.

**Files:**
- Complete primitives under: `packages/design-system/src/`
- Complete tests: `packages/design-system/tests/`
- Create: `apps/web/tests/e2e/ui-foundation.spec.ts`
- Create: `apps/web/tests/e2e/route-state-matrix.spec.ts`
- Create visual baselines in the repository-approved snapshot directory
- Modify: `docs/UI_STATE_MATRIX.md` only for reviewed production truth

**Step 1:** Generate failing route/state cases from the canonical matrix, including pending, empty, error, forbidden, not-found, zero-evidence, conflict, and print.

**Step 2:** Run component and E2E suites; expect missing state/route failures.

**Step 3:** Implement ClearCut-owned primitives and adapters. Feature code must not import a visual/headless library directly.

**Step 4:** Verify 320, 375, 768, 1024, and 1440 widths; both themes; keyboard/focus; reduced motion; coarse pointer; no overflow; route announcements; and print isolation.

**Step 5:** Run:

```bash
pnpm --filter @clearcut/design-system test
pnpm --filter clearcut-web test:e2e -- ui-foundation route-state-matrix
pnpm --filter clearcut-web build
```

Expected: all pass with reviewed visual noise thresholds.

**Checkpoint:** Request authorization before `feat: complete production ui quality gates`.

### Task 16: Prove no legacy behavior and execute the atomic release gate

**Packets reopened:** `12a-gcp-deployment.md`, `12b-release-demo-submission.md`.

**Files:**
- Modify: `Dockerfile`
- Modify: `cloudbuild.yaml`
- Modify: `scripts/deployment_smoke.py`
- Modify: `scripts/verify-submission.mjs`
- Create: `docs/reviews/2026-08-31-atomic-rebuild-release-evidence.md`
- Update: `docs/IMPLEMENTATION_PLAN.md`
- Update: `docs/ARCHITECTURE.md`
- Update: `DEVLOG.md`

**Step 1: Run static no-legacy checks**

```bash
pnpm check:no-legacy
```

Also inspect the fresh production bundle and require all of these to be absent:

```text
clearcut-flow-state-v2
full-surface clearance workspace prototype
window.location.hash
runtime.js
```

**Step 2: Run the complete local gate**

```bash
pnpm contract:lint
pnpm contract:generate
pnpm contract:check
pnpm --filter @clearcut/design-system test
pnpm --filter clearcut-web test
pnpm --filter clearcut-web build
pnpm --filter clearcut-web test:e2e
uv run pytest tests/foundation tests/contracts services/api/tests -q
AGENTS_STRICT=1 bun .agents/scripts/build.mjs
bun .agents/scripts/lint.mjs
bun .agents/scripts/verify.mjs
bun .agents/scripts/signoff.mjs
```

Expected: zero failures. Record exact output, commit SHA, and tree status.

**Step 3: Run security and tenant-isolation gate**

Exercise cross-organization and cross-project reads/writes for every project-owned module. Expected: typed 403/404 behavior with no data leakage and no writes.

**Step 4: Build and smoke the deployment candidate**

The smoke flow must cover:

```text
sign in
  -> select labeled demo organization/project
  -> upload and parse script
  -> run detection
  -> run sourced research
  -> review evidence
  -> record governed decision
  -> create revision and rescan
  -> configure/run watch
  -> generate and release dossier
  -> inspect immutable audit record
```

Expected: every step uses the deployed API and database; no fixture or local fallback is possible.

**Step 5: Verify migration and rollback compatibility**

Test database upgrade from the currently deployed schema, replacement startup, smoke flow, and rollback to the approved compatible previous image or forward-fix procedure. The replacement application itself contains no legacy runtime.

**Step 6: Record release evidence**

Document commands, outputs, SHA, deployment image digest, migration revision, demo identifiers, residual risks, and explicit non-claims. Supersede prior unsupported completion evidence.

**Step 7: Request release authorization**

Do not merge, deploy, release, or commit without the required human authorization.

**Checkpoint:** Suggested final commit after authorization: `feat: complete atomic react tanstack rebuild`.

## Definition of done

The plan is complete only when:

- `apps/web/src/runtime.js`, the hash-router `App.tsx`, and fixture production loaders do not exist;
- TanStack Start/Router/Query own the reachable production application;
- every product route appears in the generated TanStack route tree and survives direct refresh;
- the generated OpenAPI client is the only browser transport;
- every visible capability is backed by persisted, tenant-scoped application services;
- demo data is labeled, server-owned, idempotent, and accessed through normal APIs;
- evidence provenance and zero-evidence invariants hold;
- governed actions and audit events are transactional;
- no fixed-success endpoint, timer-simulated job, browser-local receipt, or fixture fallback remains;
- all verification and deployment gates in Task 16 pass;
- one authorized atomic cutover replaces the prior deployment.

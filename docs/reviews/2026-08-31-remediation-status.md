# Post-Review Remediation Status

**Date:** 2026-08-31
**Branch:** `feat/rebuild-a` (selected winner of the two rebuild attempts)
**Scope:** Close the critical gaps found in review of the rebuild attempts, under the directive "get the product ready" (correct + truthful over feature-complete).

This document is the authoritative, honest record of what was changed and what was
deliberately deferred. It does not claim completeness.

## Done (verified)

1. **Removed fabricated evidence data (commit `5f95859`).**
   - Deleted `default*` datasets from `ClaimTable`, `CommentThread`, `RecordsPage`,
     `NotificationsPage`, `TrustPage`.
   - Removed the item-detail route's hardcoded "Vega Camera" seed and its optimistic
     fake-success fallback; the route now loads authoritative state and shows real
     loading / error / empty states. A failed governed decision surfaces the failure
     instead of falsely reporting "committed".
   - Zero evidence is presented as unresolved, never as fabricated clearance.
   - Verified: `check-no-legacy` PASS, web build succeeds.

2. **Removed unscoped detection delivery stub (commit `58474e6`).**
   - `detection/delivery/http.py` was a duplicate, unmounted, unscoped stub
     (`/o/{org_slug}` prefix, in-memory `ItemProjectionService`, `project_id` passed
     as `org_id`). Mounting it would have exposed a tenant-scope bypass.
   - The real, scoped `/api/v1/organizations/{org_id}/projects/{project_id}/items`
     router already serves detection output. Stub deleted.
   - Verified: 115 backend/contract/foundation tests still pass.

3. **Honest e2e baseline (this commit).**
   - Added `auth-flow.spec.ts`: a real API-backed sign-in test (valid creds
     authenticate via POST /api/v1/sessions and navigate away; invalid creds surface
     a typed error and do not authenticate).
   - Added `tests/e2e/TESTING.md` classifying every spec as REAL vs SMOKE so no
     evidence can overclaim coverage.

## Deliberately deferred (documented, not hidden)

1. **TanStack Start + Vite 7 migration.**
   The app remains TanStack **Router** + Query on **Vite 5** (builds green).
   Rationale: `@vitejs/plugin-react@latest` now requires `vite ^8` plus
   oxc-transform-react / @rolldown/plugin-babel / react-compiler, and `vitest@2.1.9`
   targets vite 5 — there is no low-risk "bump to Vite 7" path; it is a full
   toolchain migration coupled to the Start rewrite. Start's value is SSR/server
   functions, which add little to this authenticated SPA. Deferring protects the
   verified-good backend that made this branch the winner. Revisit only if SSR is
   actually required.

2. **Detection/research run TRIGGERING endpoints.**
   Domain logic and typed provider ports (`research/ports/*`, `detection/ports/*`,
   parallel + hermetic adapters) exist but there is no scoped API endpoint to start a
   run. Detection *output* is served via the real items endpoints. Adding run
   triggers is new feature work that touches the frozen contract; deferred.

3. **Upgrading the SMOKE e2e specs.**
   9 of 11 specs assert element visibility only and do not sign in or assert
   API-backed data. They must be upgraded before the suite is called a real
   reachability gate. See `apps/web/tests/e2e/TESTING.md`.

## Environment limitation (honesty note)

The full live Playwright suite (which needs the API on :8000 and the web app on
:3000 running simultaneously) could not be executed in the current agent
environment because background servers are blocked here. The specs are therefore
verified by static reading, not by a recorded green run. Do NOT record a green e2e
result until the suite is actually run in a real environment per
`apps/web/tests/e2e/TESTING.md`.

## Gates confirmed this session

Final full-gate run (tree clean at HEAD `7a54b84`):

- `node scripts/check-no-legacy-runtime.mjs` → PASS (no legacy/architecture violations)
- `uv run pytest tests/contracts tests/foundation services/api/tests -q` → **115 passed**
- `pnpm --filter clearcut-web build` → success (Vite 5, 216 modules)
- `vitest run` (web unit) → 11 failed | 19 passed — the 11 failures are the
  pre-existing hollow symbol-existence tests documented below, NOT regressions.
- Live Playwright e2e → NOT run in this environment (background servers blocked);
  see environment-limitation note. Must be run in a real environment before any
  release claim.

## Pre-existing broken unit tests (NOT caused by this session)

`apps/web/tests/unit/*` contains hollow "symbol is defined" tests. Several import
named route exports that never existed — e.g. `workspace_routes.test.ts` imports
`ItemWorklistRoute`/`ScreenplayWorkspaceRoute`, but those route files only export
`Route` + default. Verified at the pristine baseline commit `f49fb63`: the named
exports were already absent, so these tests were already failing before any
remediation edit. Running `vitest run` directly reports `18 failed | 4 passed`
files (`11 failed | 19 passed` tests).

This is inherited fake-verification debt: the tests assert nothing about real
behavior and are broken against the actual exports. They should be deleted or
replaced with real render/interaction tests rather than patched to import the
current symbol names (which would restore a meaningless green). The prior baseline
evidence's "30 passed" was an invocation artifact and should not be trusted.

Recommended follow-up: remove `apps/web/tests/unit/*route*` symbol-existence tests;
rely on the e2e layer (see `apps/web/tests/e2e/TESTING.md`) for real coverage.

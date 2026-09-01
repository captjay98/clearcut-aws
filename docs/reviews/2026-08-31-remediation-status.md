# Post-Review Remediation Status

**Date:** 2026-08-31
**Branch:** `feat/rebuild-a` (selected winner of the two rebuild attempts)
**Scope:** Close the critical gaps found in review of the rebuild attempts, under the directive "get the product ready" (correct + truthful over feature-complete).

This document is the authoritative, honest record of what was changed and what was
deliberately deferred. It does not claim completeness.

## Architecture decision: TanStack Router (no Start/SSR), latest supported Vite

SSR is not needed for this authenticated clearance workspace (no SEO/crawl
surface; data loads client-side via the generated client). The accepted
architecture is **TanStack Router + Query**, not TanStack Start.

Upgraded to the latest cleanly Router-supported toolchain (commit `e3f7272`),
pinned exactly:
- vite `5.4.14` → `7.3.6`
- `@vitejs/plugin-react` `4.3.4` → `5.2.0` (the last line peering Vite 7; the
  6.x "latest" requires Vite 8 + oxc/rolldown/react-compiler, deliberately avoided)
- vitest `2.1.9` → `4.1.11`
- jsdom `25.0.1` → `30.0.1`

Verified: Vite 7 build succeeds (210 modules); web unit results unchanged from
pre-upgrade (same pre-existing hollow-test failures, no new regressions);
no-legacy PASS; python contract/foundation gates unaffected. Vite 8 was NOT
taken because it forces the bleeding-edge transformer chain for no product gain.

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

1. **TanStack Start / SSR.**
   Not adopted. SSR/server functions add no value to this authenticated SPA, and
   `@vitejs/plugin-react@6` (the only line requiring it) drags in the Vite 8 +
   oxc/rolldown/react-compiler chain. Accepted architecture is Router + Query on
   Vite 7 (see decision above). Revisit only if SSR is actually required.

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


---

## Session 2 addendum — cleanup + detection/research wiring

### Additional work done (verified)

4. **Pruned stale docs + hollow tests (commit `9d3dd51`).** Removed 48 superseded
   `2026-08-30-*` packet evidence docs (kept `06b` and `ui-plan-to-mock-audit` — both
   still referenced) and all 11 hollow `apps/web/tests/unit/*` symbol-existence tests.
   CI updated to drop the deleted path and run the no-legacy scanner.

5. **Moved narrative docs into `docs/` (commit `ecc204a`).** `feature-ledger.md`,
   `product-plan.md`, `submission-strategy.md` moved out of repo root; feature-coverage
   script path, steering structure tree, and doc references updated. Root now holds only
   required governance + config + the `clearcut` CLI + `start.sh`.

6. **Wired detection + research endpoints (commit `ddb0a9c`).** The two previously
   dormant contract operations are now mounted and scoped:
   - `POST .../script-versions/{versionId}:detect` (startDetection)
   - `POST .../clearance-items/{itemId}:research` (startResearch)

   Each verifies CSRF + authenticated org/project/target-ownership scope (cross-tenant
   target ⇒ 404) and persists a real job row + immutable audit event in one transaction.
   Runtime selection is production-honest: detection is Gemini-only, research is
   Parallel-only; missing credentials ⇒ typed **503**, never a hermetic fallback.
   Hermetic/test doubles are injected only via `dependency_overrides` in tests. Added a
   `jobs` table and 6 endpoint tests (persistence, 503-unconfigured, cross-tenant 404).

### Final gate (tree clean, HEAD `ddb0a9c`)

- no-legacy scanner → PASS
- contract-drift → PASS (endpoints implement existing contract ops; no schema change)
- feature-coverage → PASS (47 features)
- `uv run pytest tests/contracts tests/foundation services/api/tests` → **121 passed**
- `pnpm --filter clearcut-web build` (Vite 7) → success

### Still deferred (honest)

- **Live Gemini/Parallel provider adapters.** The detection/research endpoints are wired,
  scoped, and audited, but a *configured* live provider currently returns 503 until its
  adapter is implemented. This is intentional — no silent hermetic fallback, no fabricated
  evidence. Requires real API credentials to verify end-to-end.
- **Live Playwright e2e run** in a real 2-server environment (see `tests/e2e/TESTING.md`).
- **TanStack Start / SSR** — not needed; Router + Vite 7 is the accepted architecture.


---

## Session 3 addendum — live provider adapters (Parallel + Vertex/Gemini)

### Done (verified locally; Vertex global live-probed)

- **Parallel search/extract adapters corrected to the real API contract.** The
  existing adapters had wrong shapes; fixed against docs.parallel.ai:
  - search sends `{search_queries: [...], objective, max_chars_total}` and reads
    `excerpts[]` (was `query`/`max_results` + `snippet`);
  - extract reads `full_content`/`excerpts` (was `content`/`text`);
  - auth is `x-api-key` only (removed a bogus `Authorization: Bearer` header);
  - `ProviderFailure.kind` values corrected to the allowed literal set
    (`authentication` / `rate_limited` / `retryable` / `permanent`).
  - `get_research_runtime()` now constructs the real Parallel adapters when
    `PARALLEL_API_KEY` is set; missing key ⇒ typed 503. Hermetic never selected.

- **Vertex/Gemini detection adapter added** (`detection/adapters/vertex_runtime.py`):
  google-genai SDK in Vertex mode (`vertexai=True`, `project`, `location=global`,
  ADC auth), structured JSON output constrained to the ten `ClearanceCategory`
  enum values, rejects any category outside that fixed set, emits typed
  `CandidateItem`s. `get_detection_runtime()` constructs it when
  `GOOGLE_CLOUD_PROJECT` is set; missing ⇒ typed 503. Hermetic never selected.
  Added `google-genai>=1.33.0` to `services/api/pyproject.toml`.

### Configuration surface (all via env; no secrets in code)

- `PARALLEL_API_KEY` — Parallel Search/Extract (header `x-api-key`).
- `GOOGLE_CLOUD_PROJECT` (or `CLEARCUT_GCP_PROJECT`) — Vertex project; auth via ADC
  (`gcloud auth application-default login`; set quota project with
  `gcloud auth application-default set-quota-project clearcut-workspace`).
- `CLEARCUT_VERTEX_LOCATION` (default `global`), `CLEARCUT_GEMINI_MODEL`,
  `CLEARCUT_DETECTION_RUNTIME` (default `vertex`).

gcloud confirms `aiplatform.googleapis.com` is enabled on `clearcut-workspace`,
ADC is available, and `generativelanguage.googleapis.com` is NOT — so Vertex+ADC
is the correct path (not a Gemini API key).

### Gate (tree clean)

- `uv run pytest tests/contracts tests/foundation services/api/tests` → **127 passed**
  (added 6 provider-selection tests: 503-when-unconfigured, real-adapter-when-configured,
  never-hermetic, for both providers; the Vertex one constructs the client with no
  network call).
- contract-drift → PASS · no-legacy → PASS · foundation → PASS.

### Live Vertex global verification

On 2026-09-01 UTC, authenticated minimal `generateContent` calls were sent to:

`https://aiplatform.googleapis.com/v1/projects/clearcut-workspace/locations/global/publishers/google/models/{MODEL_ID}:generateContent`

All three configured model IDs returned HTTP 200 and reported the exact matching
`modelVersion`:

- `gemini-3.7-flash`
- `gemini-3.1-flash-lite`
- `gemini-3.1-pro-preview`

The model IDs are valid as bare IDs in the google-genai SDK; no publisher-qualified
normalization is needed in `VertexDetectionRuntime`. For the `global` location, the
REST host is `aiplatform.googleapis.com`—not `global-aiplatform.googleapis.com`.
The checks used a gcloud access token and `x-goog-user-project: clearcut-workspace`,
which avoided modifying local ADC configuration.

### Remaining live-verification boundary

1. **Parallel is not yet live-verified.** The Parallel key has not been exercised
   end-to-end here. Its adapters are built to the documented contracts and
   unit-verified for wiring, but a real search/extract round-trip remains required.
2. **Job execution is still deferred.** The `:detect` and `:research` endpoints persist a
   real 202 job + audit event but do not yet *run* the adapter and write
   snapshots/claims. The job runner that invokes these runtimes and persists results is
   the next piece of work.

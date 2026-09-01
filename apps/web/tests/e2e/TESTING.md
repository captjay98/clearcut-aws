# E2E test honesty ledger

This file states exactly what the end-to-end suite proves, so evidence docs
cannot overclaim. Do not describe the suite as "full green reachable coverage"
until the smoke specs below are upgraded to real assertions.

## How to run

The suite needs BOTH servers up:

```bash
# terminal 1 — API on :8000 with seeded demo user
cd services/api && uv run uvicorn clearcut.main:app --port 8000

# terminal 2 — Playwright starts the web app via its webServer config
pnpm --filter clearcut-web test:e2e
```

Seeded demo credentials: `jamie@northlight.example` / `password123`.

## Classification (verify by reading, not by trust)

| Spec | Level | What it actually asserts |
|------|-------|--------------------------|
| `runtime-boundary.spec.ts` | REAL | Signs into typed routes, asserts React root marker, no hash routing, no legacy localStorage across reload. Meaningful architecture gate. |
| `auth-flow.spec.ts` | REAL | Drives sign-in form; asserts real POST /api/v1/sessions succeeds and navigates away on valid creds; asserts typed error + no auth on invalid creds. |
| `e2e-clearance-lifecycle.spec.ts` | SMOKE | Navigates project routes and asserts element visibility only. Does NOT sign in or assert API-backed data. Some data-testids now sit behind real loading/error gates, so this may require an authenticated, seeded item to pass. |
| `clearance-evidence-drawer.spec.ts` | SMOKE | Visibility only. |
| `monitoring-cadence.spec.ts` | SMOKE | Visibility only. |
| `report-release-flow.spec.ts` | SMOKE | Visibility only. |
| `review-collaboration-actions.spec.ts` | SMOKE | Visibility only. |
| `script-import-viewer.spec.ts` | SMOKE | Visibility only. |
| `shell-navigation.spec.ts` | SMOKE | Mostly visibility. |
| `trust-center-learning.spec.ts` | SMOKE | Visibility only; the Trust page now renders an honest "not available" state when no evaluation exists, so visibility assertions must account for that. |
| `version-diff-lineage.spec.ts` | SMOKE | Visibility only. |

## Known follow-up (deliberately deferred, not hidden)

- The SMOKE specs must be upgraded to sign in and assert API-backed data before
  the suite can be called a real reachability gate.
- After the data-honesty fixes (removal of fabricated `default*` data), specs
  that relied on always-present fabricated content must seed real data via the
  API first, or assert the honest empty/error state instead.

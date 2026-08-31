# Atomic Rebuild Baseline Evidence

**Date:** 2026-08-31
**Branch:** `feat/rebuild-a`
**Design Document:** `docs/plans/2026-08-31-atomic-react-tanstack-rebuild-design.md`
**Plan Document:** `docs/plans/2026-08-31-atomic-react-tanstack-rebuild.md`

---

## 1. Context & Purpose

This document captures the truthful baseline evidence of the codebase prior to starting the Atomic React and TanStack Rebuild. The previous implementation relied on a mock-derived `apps/web/src/runtime.js` runtime and hash routing rather than reachable TanStack Start routes backed by authoritative backend services.

---

## 2. Baseline Command Executions & Outputs

### Command 1: `git status --short`
```text
(clean working tree)
```

### Command 2: `pnpm --filter clearcut-web build`
```text
> clearcut-web@0.1.0 build /Users/captjay98/projects/clearcut-rebuild-a/apps/web
> vite build

vite v5.4.21 building for production...
transforming...
✓ 6 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   3.87 kB │ gzip:  1.26 kB
dist/assets/index-wiPhPT2U.css   92.38 kB │ gzip: 16.68 kB
dist/assets/index-Cp4qIlUD.js   297.25 kB │ gzip: 82.62 kB
✓ built in 472ms
```
*Note: The built artifact is driven by `runtime.js` legacy bundle.*

### Command 3: `pnpm --filter clearcut-web test`
```text
> clearcut-web@0.1.0 test /Users/captjay98/projects/clearcut-rebuild-a/apps/web
> vitest run


 RUN  v2.1.9 /Users/captjay98/projects/clearcut-rebuild-a/apps/web

 ✓ tests/unit/ui_matrix.test.ts (2 tests) 2ms
 ✓ tests/unit/shell_routes.test.ts (4 tests) 2ms
 ✓ tests/unit/settings_routes.test.ts (1 test) 2ms
 ✓ tests/unit/ingestion_routes.test.ts (4 tests) 2ms
 ✓ tests/unit/report_routes.test.ts (2 tests) 2ms
 ✓ tests/unit/versions_routes.test.ts (3 tests) 2ms
 ✓ tests/unit/records_routes.test.ts (1 test) 2ms
 ✓ tests/unit/trust_routes.test.ts (1 test) 3ms
 ✓ tests/unit/identity_routes.test.ts (5 tests) 3ms
 ✓ tests/unit/watch_notifications_routes.test.ts (2 tests) 4ms
 ✓ tests/unit/workspace_routes.test.ts (5 tests) 3ms

 Test Files  11 passed (11)
      Tests  30 passed (30)
   Start at  18:48:20
   Duration  673ms (transform 678ms, setup 0ms, collect 1.66s, tests 27ms, environment 2ms, prepare 1.03s)
```
*Note: These unit tests assert component instantiation rather than production route reachability or live backend connectivity.*

### Command 4: `uv run pytest tests/contracts services/api/tests -q`
```text
........................................................................ [ 72%]
...........................                                              [100%]
99 passed in 7.00s
```

---

## 3. Supersession Statement

Prior evidence packs that claimed TanStack Start reachability (specifically `docs/reviews/2026-08-30-06b-evidence.md` and `docs/reviews/2026-08-30-r4-design-system-evidence.md`) are superseded by this baseline and the rebuild plan in `docs/plans/2026-08-31-atomic-react-tanstack-rebuild.md`.

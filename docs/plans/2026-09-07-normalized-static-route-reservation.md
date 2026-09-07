# Normalized Static Route Reservation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prevent encoded aliases of reserved API and health paths from being served by public static delivery.

**Architecture:** Canonicalize each static route parameter once with one percent-decode pass, reject residual percent ambiguity and unsafe relative paths, and pass one `PurePosixPath` to both namespace classification and filesystem resolution. Preserve route ordering, SPA behavior, and resolved-root/symlink containment.

**Tech Stack:** Python 3.12, FastAPI/Starlette, pytest/httpx, Astro, Vite/TanStack, Playwright, Ruff.

---

### Task 1: Add the encoded reserved-namespace regression

**Files:**
- Modify: `services/api/tests/architecture/test_same_origin_delivery.py`

**Step 1: Add colliding fixture files**

Create `site-dist/api/private` containing `reserved-api-file` and `site-dist/healthz` containing `reserved-health-file` in `_write_distributions`.

**Step 2: Add a parameterized regression test**

Request `/api/private`, `/%2561pi/private`, `/%252561pi/private`, `/%2568ealthz`, and `/%252568ealthz`. Assert each response is JSON 404 and contains neither reserved fixture body nor either HTML index.

**Step 3: Run the focused test and verify RED**

Run: `uv run pytest services/api/tests/architecture/test_same_origin_delivery.py::test_encoded_reserved_namespaces_never_serve_public_files -q`

Expected: encoded aliases return `reserved-api-file` or `reserved-health-file`, proving the blocker.

### Task 2: Canonicalize once and reuse the canonical path

**Files:**
- Modify: `services/api/src/clearcut/static_delivery.py`
- Test: `services/api/tests/architecture/test_same_origin_delivery.py`

**Step 1: Replace repeated decoding with one canonical boundary**

Change `_decoded_relative_path` into `_canonical_relative_path(value: str) -> PurePosixPath`: call `unquote` once; reject `"%"`, backslash, NUL, absolute paths, and `.`/`..` segments; return the validated `PurePosixPath`.

**Step 2: Make resolvers accept only canonical paths**

Change `_resolved_candidate`, `_exact_file`, and `_public_file` to accept `PurePosixPath` and perform no decoding. Canonicalize each asset/workspace/public route parameter once at the route boundary.

**Step 3: Classify the same canonical path used for resolution**

In `serve_public_path`, reserve a first segment equal to `api` and exact canonical `healthz`, then pass the unchanged canonical path to `_public_file`.

**Step 4: Run focused and preservation tests**

Run: `uv run pytest services/api/tests/architecture/test_same_origin_delivery.py -q`

Expected: PASS, including traversal, symlink, public site, workspace, docs, and API behavior.

### Task 3: Validate and commit

**Files:**
- Modify: `services/api/src/clearcut/static_delivery.py`
- Modify: `services/api/tests/architecture/test_same_origin_delivery.py`

**Step 1: Run Python contracts**

Run: `uv run pytest services/api/tests/architecture/test_same_origin_delivery.py tests/contracts/test_mounted_operation_ids.py -q`

Expected: PASS.

**Step 2: Run frontend validation**

Run the site test file directly because `clearcut-site` has no test script: `pnpm exec tsx --test apps/site/tests/public_pages.test.ts` if the repository toolchain supports it; otherwise record the unavailable script and rely on the site build. Run `pnpm --filter clearcut-site build`, `pnpm --filter clearcut-web build`, and `pnpm --filter clearcut-web test:e2e -- tests/e2e/runtime-boundary.spec.ts`.

Expected: available checks PASS and both builds succeed.

**Step 3: Run static checks**

Run: `uv run ruff check services/api/src/clearcut/static_delivery.py services/api/tests/architecture/test_same_origin_delivery.py`, `uv run ruff format --check services/api/src/clearcut/static_delivery.py services/api/tests/architecture/test_same_origin_delivery.py`, and `git diff --check` for the changed files.

Expected: PASS.

**Step 4: Review and commit**

Stage only the implementation plan, static-delivery source, and same-origin tests. Commit with `fix(runtime): reserve normalized api namespaces`.

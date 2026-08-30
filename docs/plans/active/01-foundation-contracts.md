# Foundation and Contracts Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a reproducible monorepo, enforce module/tenant boundaries, and establish one OpenAPI/schema source that generates synchronized TypeScript and Python clients.

**Architecture:** Pin the three application shells and shared packages without product behavior. Contracts and boundary tests precede FastAPI/UI implementation; `.agents/profile.toml` becomes truthful only after commands exist and pass.

**Tech Stack:** Python 3.12, uv, FastAPI/Pydantic/SQLAlchemy/Alembic/pytest/Ruff/Pyright/import-linter; Node/TypeScript, pnpm, TanStack Start, Astro, Vitest/ESLint/Prettier; OpenAPI 3.1 and JSON Schema.

---

**Status:** roadmap summary; execute packets 01a, 01b, and 01c after explicit authorization  
**Depends on:** none  
**Checkpoint:** R1

### Task 1: Freeze toolchain and workspace decisions

**Files:** Create `pyproject.toml`, `package.json`, `pnpm-workspace.yaml`, `.tool-versions`, `docs/adr/0001-workspace-toolchain.md`, `LICENSE`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, and `SECURITY.md` as specified by packet 01a.

1. Write the ADR with exact versions, package manager, generator candidates, generated-file policy, and rejected alternatives.
2. Add minimal manifests and lockfiles; do not add domain routes/components.
3. Run version/install commands and record output.
4. Commit: `chore: establish pinned workspace toolchains`.

### Task 2: Write failing architecture and coverage tests

**Files:** Create `services/api/tests/architecture/test_boundaries.py`, `scripts/check-feature-coverage.mjs`, `tests/foundation/test_workspace.py`.

Required boundary shape:

```python
FORBIDDEN_DOMAIN_IMPORTS = {"fastapi", "sqlalchemy", "google", "parallel"}

def test_domain_has_no_framework_or_provider_imports() -> None:
    assert scan_imports("services/api/src/clearcut/*/domain").isdisjoint(
        FORBIDDEN_DOMAIN_IMPORTS
    )
```

1. Run the narrow tests before source paths exist; expect a clear failure naming missing foundations.
2. Add package skeletons and import-linter contracts.
3. Re-run; expect pass.
4. Commit: `test: enforce architecture and feature ownership`.

### Task 3: Define the contract baseline

**Files:** Create `packages/contracts/openapi.yaml`, `packages/contracts/schemas/error.json`, `packages/contracts/schemas/events/envelope.v1.json`, `packages/contracts/README.md`.

Start with health, error envelope, IDs/timestamps, pagination, scoped path parameters, async run state, and idempotency—not all product endpoints.

```yaml
components:
  schemas:
    RunStatus:
      type: string
      enum: [queued, claimed, running, retry_wait, succeeded, failed, manual_retry, cancelled]
```

Add lint tests, run them red then green, and commit: `feat: define versioned contract foundation`.

### Task 4: Generate clients and drift checks

**Files:** Create `packages/contracts/generated/typescript/`, `packages/contracts/generated/python/`, generator config, `scripts/check-contract-drift.mjs`.

1. Generate both clients from the same OpenAPI file.
2. Add a test that mutates a temporary contract and proves stale output fails.
3. Ensure generated files carry “do not edit” markers.
4. Run generation twice and verify deterministic output.
5. Commit: `build: generate synchronized api clients`.

### Task 5: Add minimal application shells and truthful gates

**Files:** Create `apps/site/`, `apps/web/`, `services/api/`, `packages/design-system/`, `.github/workflows/ci.yml`; modify `.agents/profile.toml` only now.

Each shell exposes health/build proof only. Run backend format/lint/type/test, frontend lint/type/test/build, contract checks, feature coverage, and `.agents` signoff. Record exact commands/results in `docs/reviews/<date>-r1-foundation-evidence.md` with explicit non-claims.

### Exit criteria

- A clean checkout installs from lockfiles and runs every recorded gate.
- Boundary, coverage, schema, generation, and drift tests pass.
- Both generated clients agree with one versioned contract.
- Three shells compile independently and contain no fake product behavior.
- Mock audit still passes; current count is read from command output, not hard-coded.
- R1 evidence is reviewed before Plan 02.

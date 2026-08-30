# Application Shells, Boundaries, and CI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create buildable API/web/site shells and enforce module, adapter, contract, and repository gates.  
**Architecture:** Three deployables share contracts/config but no product behavior; backend layers follow domain → application → adapters → delivery.  
**Tech Stack:** FastAPI, TanStack Start, Astro, pytest, import-linter, Vitest, GitHub Actions.

---

**Files:** Create `services/api/src/clearcut/main.py`, `services/api/src/clearcut/bootstrap/adapter_registry.py`, `services/api/tests/architecture/test_boundaries.py`, `apps/web/src/routes/index.tsx`, `apps/site/src/pages/index.astro`, `packages/design-system/src/index.ts`, `.github/workflows/ci.yml`, `scripts/check-feature-coverage.mjs`; modify `.agents/profile.toml` only after commands pass.

1. Write failing boundary tests for forbidden domain SDK imports, cross-module ORM imports, direct environment reads, implicit plugin discovery, and 47 single-owner feature rows.
2. Run `uv run pytest services/api/tests/architecture tests/foundation -q`; expect missing-shell failures.
3. Add health/build-only shells, explicit empty adapter registry, and root `pnpm verify` orchestration.
4. Run backend lint/type/test, frontend lint/type/test/build, contract checks, feature coverage, and agent signoff; expect all exit 0.
5. Record R1 evidence and explicit non-claims; commit `build: add guarded application shells and ci` after authorization.

**Exit:** Clean-clone gates pass; no shell fakes domain/provider behavior.


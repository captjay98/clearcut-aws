# Contract Package and Generated Clients Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Establish one OpenAPI/schema source and deterministic TypeScript/Python clients.  
**Architecture:** `packages/contracts/openapi.yaml` is authoritative; FastAPI and clients are consumers.  
**Tech Stack:** OpenAPI 3.1, JSON Schema, Spectral, selected generator.

---

**Files:** Create `packages/contracts/openapi.yaml`, `packages/contracts/schemas/error.json`, `packages/contracts/schemas/events/envelope.v1.json`, `packages/contracts/generated/typescript/`, `packages/contracts/generated/python/`, `packages/contracts/README.md`, `scripts/check-contract-drift.mjs`; test `tests/contracts/test_openapi.py`, `tests/contracts/test_operation_inventory.py`.

1. Add failing assertions for `docs/API_OPERATIONS.md` operation IDs, UUIDv7 formats, error envelope, scoped paths, idempotency headers, and canonical `RunStatus`. Run `uv run pytest tests/contracts -q`; expect missing-contract failure.
2. Add the minimal schemas and security definitions; do not add undeclared product operations.
3. Configure generation into the two declared directories and add do-not-edit headers.
4. Run `pnpm contract:lint`, `pnpm contract:generate` twice, and `pnpm contract:check`; expect exit 0 and no second-generation diff.
5. Record evidence; commit `feat: establish versioned api contract package` after authorization.

**Exit:** There is no second OpenAPI/schema source and both clients expose identical operation IDs and nullability.


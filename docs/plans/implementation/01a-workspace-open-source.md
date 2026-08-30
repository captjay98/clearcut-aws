# Workspace and Open-Source Foundation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create pinned reproducible workspace metadata and the public repository governance baseline.  
**Architecture:** Root manifests define one Python and one TypeScript workspace; public policies make contribution and security expectations explicit.  
**Tech Stack:** Python 3.12, uv, Node.js, pnpm, Markdown.

---

**Files:** Create `pyproject.toml`, `uv.lock`, `package.json`, `pnpm-lock.yaml`, `pnpm-workspace.yaml`, `.tool-versions`, `LICENSE`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `docs/adr/0001-workspace-toolchain.md`; test `tests/foundation/test_workspace.py`, `scripts/check-package-managers.mjs`.

1. Write failing tests for exact runtime versions, one lockfile per ecosystem, approved workspace roots, required public files, and no prohibited AI dependencies. Run `uv run pytest tests/foundation/test_workspace.py -q`; expect missing-manifest failures.
2. Record exact versions, rejected alternatives, license choice, supported platforms, and update policy in ADR 0001.
3. Add the minimal manifests/policies and generate lockfiles without application packages.
4. Run the foundation test and `node scripts/check-package-managers.mjs`; expect exit 0 and deterministic lockfiles.
5. Record `docs/reviews/<date>-01a-evidence.md`; commit `chore: establish open source workspace foundation` after authorization.

**Exit:** A clean checkout selects the same runtimes/dependencies and contains no product behavior or non-Google AI runtime.


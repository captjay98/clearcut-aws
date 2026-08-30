# ADR 0001: Workspace Structure, Package Managers, and Toolchain Pinning

## Status
**Accepted** (2026-08-30)

## Context
ClearCut is an open-source, hosted screenplay pre-clearance evidence desk. The project architecture requires:
1. A modular backend service (`clearcut-api`) implemented in Python 3.12 using FastAPI, Google ADK (Gemini), and the `parallel-web` SDK.
2. Two frontend applications: a public marketing & competition site (`clearcut-site` in Astro) and an authenticated workspace (`clearcut-web` in TanStack Start).
3. Shared contract packages (`packages/contracts`) providing OpenAPI 3.1 specifications and generated TypeScript/Python clients.
4. Deterministic, reproducible builds across local developer workstations, CI pipelines, and Cloud Run container images.

## Decisions

### 1. Package Managers and Ecosystem Toolchains
* **Python Workspace (`uv`)**:
  * We adopt [`uv`](https://github.com/astral-sh/uv) as the single Python package and project manager.
  * Root `pyproject.toml` defines workspace members (`services/*`) and root development dependencies (`pytest`, `ruff`, `pyright`, `import-linter`).
  * Dependency resolution is locked via a single `uv.lock`.
* **TypeScript / Node.js Workspace (`pnpm`)**:
  * We adopt [`pnpm`](https://pnpm.io/) as the Node.js monorepo package manager.
  * Root `pnpm-workspace.yaml` declares `apps/*` (`apps/site`, `apps/web`) and `packages/*` (`packages/contracts`, `packages/ui`).
  * Dependency resolution is locked via a single `pnpm-lock.yaml`.

### 2. Version Pinning
* Runtime versions are pinned in `.tool-versions`:
  * Python: `3.12.9`
  * Node.js: `20.18.0`
  * pnpm: `9.15.0`
  * bun: `1.2.0` (for `.agents/` generation and verification scripts)

### 3. Contract-First Client Generation
* `packages/contracts/openapi.yaml` is the single source of truth for all API definitions.
* TypeScript clients (`packages/contracts/generated/typescript/`) and Python client libraries are generated directly from the canonical OpenAPI spec.
* Hand-written API schemas or drift between FastAPI routes and frontend client fetches are prohibited.

### 4. Banned Dependencies and Runtimes
* To uphold deterministic governance, provenance, and competition compliance, general-purpose LLM orchestration wrappers (such as `langchain`, `llamaindex`, `autogen`, `crewai`) are prohibited.
* AI inference is restricted strictly to Gemini via Google ADK, and web research is restricted strictly to the official `parallel-web` SDK.

## Consequences
* Every developer and CI pipeline uses identical package managers (`uv` and `pnpm`).
* Build artifacts and lockfiles remain deterministic with zero lockfile proliferation.
* Strict import boundaries are enforced by automated architecture tests before domain logic is implemented.

## Rejected Alternatives
* **Poetry / Pipenv**: Slower resolution times, complex monorepo workspace support compared to `uv`.
* **npm / yarn**: Less efficient disk deduplication and slower workspace symlink resolution compared to `pnpm`.
* **Multi-repo separation**: Higher maintenance overhead for contract synchronization between backend and frontend compared to a contract-driven monorepo.

---
trigger: always
globs: ['**/*']
---

# Always Run Verification

Never claim work is complete without running relevant verification commands and reporting their output. Match checks to the changed scope and the repository phase.

## ClearCut Verification Commands

```bash
# Mock prototype (only if misc/clearcut-flow changed)
node misc/clearcut-flow/mockup-audit.mjs

# Agent config (canonical changes)
bun .agents/scripts/build.mjs
node .agents/scripts/signoff.mjs

# Python backend (when services/api and its toolchain exist)
cd services/api && ruff check . && ruff format --check . && pyright && pytest

# TypeScript workspace (when manifests and targets exist)
pnpm lint && pnpm format:check && pnpm typecheck && pnpm test

# Contract drift and E2E (when configured)
pnpm --filter contracts generate && git diff --exit-code packages/contracts/
pnpm test:e2e
```

## Phase-Aware Application

This repository is currently pre-implementation. Do not claim absent backend, frontend, contract, or E2E checks ran. For canonical `.agents` changes, regenerate unless the current delegation explicitly reserves generation, then run non-mutating source checks and report the deferral. Re-evaluate available checks after implementation work creates a manifest or target; newly applicable tests and builds become required before completion.

If a verification command fails, fix the source or report the blocker before claiming completion. Never hide a failure with a fabricated success or an empty fallback.

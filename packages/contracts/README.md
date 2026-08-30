# ClearCut API Contracts (`@clearcut/contracts`)

This package contains the single canonical API specification and deterministic client bindings for ClearCut.

## Structure

* `openapi.yaml`: Canonical OpenAPI 3.1.0 specification.
* `schemas/`: Standalone JSON Schemas (error models, domain event envelopes).
* `generated/typescript/`: Auto-generated TypeScript types and client interface definitions.
* `generated/python/`: Auto-generated Python Pydantic client models.

## Commands

```bash
# Verify schema syntax and zero drift
bun scripts/check-contract-drift.mjs

# Re-generate TypeScript and Python clients from openapi.yaml
bun scripts/generate-clients.mjs
```

> **Warning:** Do not edit files under `generated/` directly. Always update `openapi.yaml` and re-run the generator.

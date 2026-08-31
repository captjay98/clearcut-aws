# ClearCut API Contracts (`@clearcut/contracts`)

This package contains the single canonical API specification and deterministic client bindings for ClearCut.

## Structure

* `openapi.yaml`: Canonical OpenAPI 3.1.0 specification.
* `schemas/`: Standalone JSON Schemas (error models, domain event envelopes).
* `generated/typescript/`: Auto-generated TypeScript types, `ApiResult` envelope, and executable same-origin client transport.
* `generated/python/`: Auto-generated Python Pydantic client models.

## Client Usage (TypeScript)

```ts
import { api, type ApiResult } from '@clearcut/contracts';

const result = await api.getSessionContext();
if (result.ok) {
  console.log('Session context:', result.value);
} else {
  console.error('API Error:', result.error.code, result.error.message);
}
```

## Commands

```bash
# Verify schema syntax and zero drift
pnpm contract:check

# Re-generate TypeScript and Python clients from openapi.yaml
pnpm contract:generate
```

> **Warning:** Do not edit files under `generated/` directly. Always update `openapi.yaml` and re-run the generator.

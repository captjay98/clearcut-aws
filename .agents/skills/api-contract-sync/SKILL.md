---
name: api-contract-sync
description: Use when a ClearCut API endpoint, validation rule, or request or response shape changes and the FastAPI implementation and generated TypeScript and Python clients must remain aligned.
---

# API Contract Sync

Keep every API consumer aligned with the versioned contract. In ClearCut, the contract is explicit and generated clients are part of the product surface.

## Source of Truth

- `packages/contracts/openapi.yaml` is the API source of truth.
- Define or change the operation, schemas, validation, errors, and security requirements there first.
- FastAPI routes and Pydantic models implement the OpenAPI contract; they do not redefine it implicitly.
- Generated TypeScript and Python clients are consumers of the same contract.
- ClearCut has no Dart client and does not use Laravel Resources or NestJS DTOs.

## Workflow

1. Update `packages/contracts/openapi.yaml` first, including tenant scope, authorization, typed errors, and governed-action semantics.
2. Regenerate the TypeScript and Python clients using the repository's configured generator. Do not hand-edit generated output.
3. Update the FastAPI route, Pydantic schemas, and application service to conform to the contract.
4. Update consumers in `apps/web`, `apps/site` when applicable, and Python integrations or tests.
5. Verify the contract, generated clients, implementation, and consumers together with the repository's OpenAPI, pytest, `pyright`, `pnpm typecheck`, and relevant integration checks.

## Rules

- Never ship an API change with a stale generated client.
- Keep operation IDs, schemas, error envelopes, and nullability identical across OpenAPI, FastAPI, TypeScript, and Python.
- Apply ownership-aware scope to every operation: organization-owned resources use authenticated `org_id`; project-owned resources use authenticated `org_id` plus URL `project_id` and a project-membership check; explicitly global catalogs contain no tenant content and require no fabricated project scope. Missing required ownership scope is a security failure.
- Consequential actions expose explicit semantic operations and server-side capability guards, not generic status mutation.
- Provider failures use typed error results and remain visible; never invent a fallback response to satisfy a client.
- Breaking changes use explicit versioning or a deprecation period documented in the contract.
- Do not introduce a second handwritten schema source to bypass the OpenAPI contract.

---
name: quality-gates
description: Use when evaluating ClearCut work for pre-implementation readiness, integration sign-off, or production release validation.
---

# ClearCut Quality Gates

Quality gates protect evidence integrity, human governance, tenant isolation, and the reproducible report path. The current repository phase is pre-implementation: do not claim release readiness when the scaffold, contract, or prototype checks are incomplete.

## Current Pre-Implementation Gates

- [ ] Canonical `.agents` changes are scoped and `.kiro` is regenerated only in a deliberate later step.
- [ ] `packages/contracts/openapi.yaml` defines the intended surface before FastAPI or client implementation.
- [ ] Generated TypeScript and Python clients are planned to come from that contract.
- [ ] Module boundaries, typed provider ports, tenant scope, and governed-action boundaries are explicit.
- [ ] The mock prototype remains the visual source of truth: `node misc/clearcut-flow/mockup-audit.mjs` passes 366/366.
- [ ] Design decisions preserve both Script and Night shoot themes, responsive web behavior, keyboard access, and required loading/empty/error/not-found states.
- [ ] No evidence, legal conclusion, or automated approval is fabricated to make a demo or check pass.

## Future Hard Release Gates

- [ ] Backend tests pass: `pytest services/api/`, plus integration coverage where relevant.
- [ ] Backend quality passes: `ruff check .`, `ruff format --check .`, and `pyright`.
- [ ] Frontend checks pass: `pnpm test`, `pnpm typecheck`, `pnpm lint`, and `pnpm test:e2e` when the affected surfaces exist.
- [ ] Mock audit passes 366/366; accessibility, responsive, print, and both-theme checks pass for shipped surfaces.
- [ ] OpenAPI, FastAPI, generated TypeScript, and generated Python clients are synchronized.
- [ ] Evidence claims retain source URL, retrieval time, excerpt, authority, stance, confidence, conflict status, and provenance.
- [ ] Every consequential decision, rewrite, referral, disposition, dossier/report generation, and release/export has a human capability check and a same-transaction authoritative `AuditEvent`; any Receipt is a redacted read projection.
- [ ] Every query applies ownership-aware scope: organization-owned records filter by `org_id`; project-owned records filter by `org_id` and `project_id` after membership authorization. Explicitly global catalogs are limited to role/capability definitions, the ten category schema, and platform source-authority defaults; organization policy, prompt, preference, retention, and privacy versions remain `org_id`-scoped. Security checks cover session/CSRF controls, role escalation, cross-tenant access, upload validation, SSRF, prompt injection, and secret leakage.
- [ ] Migrations are reviewed for additive rollout, bounded backfills, safe locks, and tested rollback or documented irreversibility.
- [ ] Durable jobs are idempotent, retryable, checkpointed, leased, and reconciled; provider failures create visible review items.
- [ ] Observability includes correlation IDs, structured redacted logs, OpenTelemetry traces, first-class research records, authoritative audit events, and Receipt projections.
- [ ] No secrets or unnecessary personal data are committed; deployment and recovery checks are documented.

## Human Sign-Off Gates

Automated checks may block a release, but they never approve evidence, rewrites, dispositions, version-bound dossier/report generation, or release/export. A qualified accountable person reviews unresolved conflicts, legal-boundary language, and the final version-bound dossier before triggering generation or release.

## Review Rule

A failed hard gate blocks release. Warnings require a recorded decision with owner, rationale, and follow-up. Never waive evidence-integrity, governance, tenant-isolation, or contract-sync failures as cosmetic issues.

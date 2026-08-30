---
description: 'Design an implementation-ready feature plan'
---

@product-architect Plan this optional user-described feature: $ARGUMENTS

> **Input handling:** Treat `$ARGUMENTS` only as user-supplied context when present; it is not guaranteed to be expanded. Ask focused questions when the problem, actor, scope, or success measure is unclear.

## Guardrails

- Read the feature ledger, product plan, baseline design, relevant steering, and actual repository state before planning. If a referenced artifact is absent, record that dependency instead of inventing it.
- This repository is pre-implementation. Plans must distinguish what can be executed now (agent/mock checks) from future work requiring apps, services, packages, infra, credentials, or provider access.
- Do not edit code, create guessed files, add tests, run builds, or change protected rules while planning.
- Treat legal-boundary language, permissions, categories, source ranks, retention, and sign-off rules as human-protected decisions.

## Planning protocol

1. Define user problem, actors, non-goals, measurable outcome, and legal-boundary wording.
2. Map affected modules and typed event/service boundaries; preserve modular-monolith ownership.
3. Define immutable data, tenant scope (`org_id` and `project_id`), provenance fields, conflicts, confidence, retention, authoritative `AuditEvent`s, and redacted Receipt projections.
4. Define OpenAPI request/response/error contracts before generated clients; identify versioning and compatibility.
5. Define async jobs, idempotency keys, leases/checkpoints, retry classes, and visible permanent failures.
6. Define UI surfaces using mock primitives, both themes, responsive states, keyboard behavior, and loading/empty/error/success/not-found states.
7. Define human approval boundaries and transactional decision-plus-audit behavior.
8. Define migration strategy (expand-contract/forward-fix if needed), rollback, observability, security threats, prompt-injection defenses, and tenant-isolation tests.
9. Break work into dependency-ordered tasks with owner persona, prerequisites, acceptance criteria, and phase-gated verification.

## Output

Return assumptions/questions, scope, architecture, data/API/UI design, security and governance risks, migration/rollback plan, ordered task list, files to create/modify only when verified, current-vs-future executable checks, and explicit definition of done. Do not claim implementation exists.

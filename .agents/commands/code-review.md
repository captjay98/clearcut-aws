---
description: 'Review changes for correctness, security, and ClearCut invariants'
---

@security-engineer Review these changes using this optional user context: $ARGUMENTS

> **Input handling:** Treat `$ARGUMENTS` only as user-supplied context when present; it is not guaranteed to be expanded. If no diff, commit, or path is supplied, inspect the working tree and ask the user to identify the intended change. Never review files not actually present.

## Guardrails

- Read the diff and relevant neighboring code before judging behavior.
- Establish the current phase first. This repository is pre-implementation, so absent apps, services, packages, generated clients, and deployment files are not review failures unless the change claims to add them.
- Do not run builds, mutate data, call live providers, or edit code during review. Do not add tests; identify missing tests as findings.
- Preserve unrelated untracked `.github/`, `.pi/`, and `README.md` files in scope reports.

## Review order

1. **Scope and contracts** — summarize changed behavior, affected module boundaries, API/schema impact, migration impact, and whether the change stays within the requested paths.
2. **Evidence integrity** — every claim is tied to a Parallel source URL, retrieval time, excerpt, authority rank, stance, confidence basis, and provenance. Failed research creates a visible review item, never fallback evidence. Conflicts remain visible.
3. **Governed actions** — verify evidence, rewrite approval, referral, disposition, and report release require an accountable human; capability checks are server-side; the decision and authoritative `AuditEvent` commit transactionally, and any Receipt is a redacted read projection.
4. **Tenant isolation** — organization-owned queries use authenticated `org_id`; project-owned queries use `org_id` + `project_id` with membership/ownership checks; explicitly global catalogs are allowlisted and contain no tenant content. No cross-module storage reads; events and typed services carry the required scope.
5. **Provider and job boundaries** — external calls use typed ports and typed results/errors, bounded idempotent retries, leases/checkpoints, and visible permanent failures. No prompt or source content can change policy or permissions.
6. **Immutable and reproducible records** — script versions are snapshots; reports bind exact script, policy, prompt, rubric, judge, evidence, and source versions.
7. **API and UI discipline** — OpenAPI changes precede generated clients; no raw dicts/ambiguous booleans across boundaries; UI follows mock primitives, both themes, token spacing, accessible gated controls, and no unapproved inline styles.
8. **General quality** — explicit error paths, strict types, naming, retention, logging without secrets, and tests for behavior rather than implementation details.

## Finding format

For each finding report file/line, category, severity (`blocker`, `warning`, `nit`), violated invariant, concrete impact, and recommended fix. State what you verified and what was unavailable because the repository is pre-implementation. Finish with a concise risk summary; do not make a pass claim without evidence.

# Agent Conventions

## Canonical Source and Runtime

`.agents/` is the canonical source for personas, steering, rules, and shared includes. `.kiro/` is generated output; project `.kiro/settings/` is optional and may be absent. Every Kiro persona intentionally uses `tools: ["@builtin"]` plus `includeMcpJson: true` for autonomy. Do not reverse that decision. Safety is enforced by user-level `~/.kiro/settings/permissions.yaml`, not by narrowing persona tools.

The repository is currently pre-implementation. Planned `apps/`, `services/`, `packages/`, `infra/`, and `demo/` paths are target architecture, not proof that runtime code exists.

## Delegation Model

- Database, API, evidence pipeline, governed actions, durable jobs → `@backend-engineer` (implementation).
- TanStack Start workspace, Astro marketing site, components, accessibility → `@frontend-engineer` (implementation owner).
- Contract-first vertical slices spanning API + UI → `@fullstack-engineer`.
- Domain model, workflow, architecture, category/rubric/policy design and review → `@product-architect` (design/review; delegates implementation).
- Approval boundaries, provenance, tenant isolation, prompt-injection defense → `@security-engineer` (security design/review; delegates implementation).
- GCP infrastructure, three service images, CI/CD, observability → `@devops-engineer`.
- Test strategy, evaluation corpus, Playwright E2E, parser suites → `@qa-engineer`.
- Evidence quality metrics, judge score trends, tool-call costs → `@data-analyst`.
- Responsive parity review at 320–1440px → `@mobile-engineer` (reviewer; Frontend implements fixes).

### Utility Agents

- Multi-file implementation/refactor → `@builder`.
- Bulk mechanical transforms → `@codex`.
- Read-only research → `@explorer`.
- Boilerplate only after a real Plan 01+ foundation and sibling pattern exists → `@scaffolder`.
- Mechanical cleanup → `@janitor`.
- Run checks and report failures without fixing → `@triager`.

## Verification Requirements

Always provide the command and output before claiming completion. For canonical `.agents` changes, regenerate and run signoff after the source is ready unless the active delegation explicitly reserves generation. When implementation exists, use the backend, frontend, mock, contract, and E2E checks appropriate to the changed scope, and re-evaluate available checks after edits create new targets.

## Scope and Evidence Invariants

- Organization-owned resources require authenticated `org_id`; project-owned resources require `org_id` + `project_id`; explicitly global catalogs are limited to role/capability definitions, the ten category schema, and platform source-authority defaults. Organization policy, prompt, preference, retention, and privacy configuration remains `org_id`-scoped.
- A `ClearanceItem` may have zero evidence claims while research is pending, unavailable, failed, or empty. Every `EvidenceClaim` requires a cited Parallel `SourceSnapshot` with complete provenance.
- Governed actions—including dossier/report generation and release/export—require an accountable human and commit with their audit event in one transaction.
- Modules communicate through typed events, not by reading each other's storage.
- Provider ports return typed results or typed errors.
- The mock prototype's 366-check audit must not regress.
- Protected permissions, sign-off/approval policy, category definitions, source-authority tiers, evidence schemas, deterministic blocking rules, retention/privacy settings, and legal-boundary language are human-only. Gated learning candidates are limited to approved low-risk query/example/prompt/preference changes through regression, shadow/canary, promotion, and rollback.

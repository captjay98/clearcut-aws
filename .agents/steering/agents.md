# Agent Conventions

## Canonical Source and Runtime

`.agents/` is canonical for personas, steering, rules, and shared includes. Regenerate `AGENTS.md`, `.kiro/`, and `.agents/render-manifest.json` through the repository scripts; do not hand-edit generated output. Every Kiro persona intentionally uses `tools: ["@builtin"]` plus `includeMcpJson: true`. Safety is enforced by user-level `~/.kiro/settings/permissions.yaml`, not by narrowing persona tools.

The repository contains implemented application, package, infrastructure, and demo directories. Distinguish source implementation from runtime evidence: the local and portable contracts exist, while Terraform remains unapplied and no hosted deployment is verified.

## Delegation Model

- Database, API, evidence pipeline, governed actions, durable jobs → `@backend-engineer`.
- TanStack workspace, Astro pages, components, accessibility → `@frontend-engineer`.
- Contract-first slices spanning API and UI → `@fullstack-engineer`.
- Domain, workflow, rubric, category, and policy design/review → `@product-architect`.
- Approval boundaries, provenance, tenant isolation, and prompt-injection defense → `@security-engineer`.
- One-image packaging, Local/Portable/GCP profiles, GCP infrastructure, release workflows, observability → `@devops-engineer`.
- Test strategy, evaluation corpus, Playwright E2E, parser suites → `@qa-engineer`.
- Evidence quality, judge trends, and provider cost metrics → `@data-analyst`.
- Responsive parity review at 320–1440px → `@mobile-engineer`; Frontend implements fixes.

### Utility Agents

- Multi-file implementation/refactor → `@builder`.
- Bulk mechanical transforms → `@codex`.
- Read-only investigation → `@explorer`.
- Boilerplate after a real sibling pattern exists → `@scaffolder`.
- Mechanical cleanup → `@janitor`.
- Run checks and report failures without fixing → `@triager`.

## Deployment Truth Boundary

- One immutable `clearcut` image packages Astro, TanStack Start, FastAPI, migrations, and scripts.
- FastAPI is the sole public entry point; `/api/internal/*` remains private authenticated delivery.
- GCP Starter is one public Cloud Run service plus a same-digest migration job.
- Local, Portable Server, and GCP Starter share the image and select adapters through configuration.
- Portable PostgreSQL dispatch and Firebase runtime composition are not yet wired.
- Gemini and Parallel default disabled and require cost acknowledgement plus bounded concurrency.
- Terraform validation and workflow tests are not hosted evidence. Never claim deployment, recovery, provider, or production readiness without external proof in the submission manifest.

## Verification Requirements

Always provide commands and output before claiming completion. For canonical `.agents` changes, run strict generation, lint, verify, and signoff. For runtime work, select backend, frontend, contract, container, Terraform, and E2E checks appropriate to the scope. Never perform cloud mutation or paid-provider calls merely to satisfy verification.

## Scope and Evidence Invariants

- Organization-owned resources require authenticated `org_id`; project-owned resources require authenticated `org_id` plus `project_id`; global catalogs are limited to role/capability definitions, the category schema, and platform authority defaults.
- A `ClearanceItem` may have zero claims while research is pending, unavailable, failed, or empty. Every `EvidenceClaim` requires a cited Parallel `SourceSnapshot` with complete provenance.
- Governed actions, including report generation and release, require an accountable human and same-transaction audit event.
- Modules communicate through typed events and ports, not by reading another module's storage.
- Provider ports return typed results or typed errors; failures remain visible.
- Protected policy and legal boundaries are human-only.

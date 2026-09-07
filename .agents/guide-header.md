## Repository and Agent Runtime State

`.agents/` is the canonical source for personas, steering, rules, and shared includes. The repository contains implemented Astro, TanStack Start, FastAPI, contracts, design-system, infrastructure, and demo surfaces. Generated agent outputs such as `AGENTS.md` and `.agents/render-manifest.json` must be regenerated from canonical sources rather than hand-edited.

Every Kiro persona intentionally uses `tools: ["@builtin"]` and `includeMcpJson: true` for full agent autonomy. Do not narrow that list. Safety and approval enforcement come from user-level `~/.kiro/settings/permissions.yaml`; project `.kiro/settings/` is optional generated/client configuration, not the canonical source or security boundary.

## Critical Patterns

- **Evidence provenance is mandatory.** Detection may create a project-owned `ClearanceItem` with zero claims while research is pending, unavailable, failed, or empty. Every `EvidenceClaim` requires a cited Parallel `SourceSnapshot` with URL, retrieval time, attributable excerpt, publisher/authority classification, stance, query/research-run identity, and provenance. Zero evidence is unresolved, never clearance; no fallback evidence is invented.
- **Governed actions are transactional.** Evidence decisions, rewrite approvals, referrals, dispositions, and report generation and release/export require an accountable human trigger. Owner, Admin, and Reviewer may trigger governed report operations only within authorized projects and active policy. The authoritative immutable `AuditEvent` commits in the same database transaction; any Receipt is a redacted read projection.
- **Tenant scope follows ownership.** Organization-owned records use authenticated `org_id`; project-owned records require authenticated `org_id` plus project path scope. Explicitly global catalogs are limited to role/capability definitions, the ten category schema, and platform source-authority defaults. Organization policy, prompt, preference, retention, and privacy configuration remains organization-scoped.
- **Provider ports return typed results or typed errors.** No booleans, `None`, or raw dictionaries cross module boundaries. Provider failures create visible review items, not silent fallbacks.
- **Paid providers are fail-closed.** Gemini and Parallel default disabled. Enabling either requires explicit cost acknowledgement and a positive bounded concurrency limit before client resolution or a paid call.
- **The mock is the design source of truth.** The 20-surface mock at `misc/clearcut-flow/` defines visual identity, component vocabulary, and interaction patterns.
- **Protected rules are human-only.** Permissions, sign-off policy, categories, authority tiers, evidence schemas, deterministic blocking rules, retention/privacy settings, and legal-boundary language are never changed automatically.
- **No legal conclusions.** ClearCut presents sourced findings and unresolved risk for qualified human review; it is not legal counsel or a clearance guarantee.

## Deployment Architecture

One immutable `clearcut` image contains Astro, TanStack Start, FastAPI, migrations, and operational scripts. FastAPI is the sole public entry point: public Astro routes, `/app/*`, `/api/*`, and protected `/api/internal/*`. Local, Portable Server, and GCP Starter select storage, dispatch, secret, and identity adapters through validated configuration while using the same image.

GCP Starter uses one public Cloud Run service, GCS, Cloud Tasks, Secret Manager, and an existing PostgreSQL database or separately acknowledged Cloud SQL. Its migration job reuses the exact application digest. Built-in opaque sessions are the default. Portable PostgreSQL dispatch and Firebase runtime composition remain explicit deferrals. Terraform is unapplied and no hosted release evidence exists.

## Domain Context

ClearCut is an implemented screenplay pre-clearance evidence workspace for independent producers, screenwriters, and clearance teams. It parses scripts, detects items across ten protected categories, supports mandatory Parallel Search with bounded Extract when authorized, coordinates fixed-role human review, re-evaluates revisions, monitors source changes, and exports reproducible version-bound reports. It supports evidence gathering and workflow coordination, not legal advice or final legal clearance. The submission targets the Parallel track of Agentic Cinema; the submission manifest remains the authoritative GO/NO-GO ledger.

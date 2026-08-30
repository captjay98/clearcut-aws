# AI Agent Guide for Clearcut

Generated root guide for the unified multi-tool system. Canonical source of truth is .agents/.

## Canonical Source

This file is generated from `.agents` by `bun .agents/scripts/build.mjs`.

## Inventory

- Personas: 15
- Subagents: 15
- Commands: 18
- Skills: 16
- Rules: 10
- Steering docs: 8

## Repository and Agent Runtime State

The canonical configuration source is `.agents/`. The repository is currently **pre-implementation**: the mock, plans, contracts/design guidance, and agent configuration exist, while the planned `apps/`, `services/`, `packages/`, `infra/`, and `demo/` product directories are not yet implemented. Treat the target tree below as planned architecture, not as an inventory of present runtime code.

Every Kiro persona intentionally uses `tools: ["@builtin"]` and `includeMcpJson: true` for full agent autonomy. This is deliberate and must not be replaced with a narrower tool list. Safety and approval enforcement come from the user-level `~/.kiro/settings/permissions.yaml`. Project `.kiro/settings/` is optional generated/client configuration, not the canonical source and not the security boundary; do not assume it exists or edit it directly.

## Critical Patterns

- **Evidence provenance is mandatory, with a precise boundary.** Detection may create a project-owned `ClearanceItem` with zero claims while research is pending, unavailable, failed, or returns no results. An `EvidenceClaim` requires a cited Parallel `SourceSnapshot`: URL, retrieval time, attributable excerpt, publisher/authority classification, stance, query/research-run identity, and provenance. Zero evidence is unresolved, never clearance; no fallback evidence is invented.
- **Governed actions are transactional.** Evidence decisions, rewrite approvals, referrals, dispositions, and dossier/report generation and release/export require an accountable human trigger. Owner, Admin, and Reviewer may trigger governed report generation/release only within authorized projects and active policy. A draft dossier may be prepared for review, but governed generation and release/export commit with the authoritative immutable `AuditEvent` in the same database transaction; any Receipt is a redacted read projection.
- **Tenant scope follows ownership.** Organization-owned records use authenticated `org_id`; project-owned records require authenticated `org_id` plus the project path scope; explicitly global catalogs are limited to role/capability definitions, the ten category schema, and platform source-authority defaults. Organization policy, prompt, preference, retention, and privacy configurations and versions remain `org_id`-scoped and must never be treated as global. A missing organization or project check is a security failure.
- **Provider ports return typed results or typed errors.** No booleans, `None`, or raw dicts cross module boundaries. Provider failures create visible review items, not silent fallbacks.
- **The mock prototype is the design source of truth.** The 20-surface mock at `misc/clearcut-flow/` defines the visual identity, component vocabulary, and interaction patterns. Production implements it; it does not redesign it.
- **Protected rules are human-only.** Permissions, sign-off/approval policy, category definitions, source-authority tiers, evidence schemas, deterministic blocking rules, retention/privacy settings, and legal-boundary language are never changed by an automated process. Gated learning candidates may change query phrasing, retrieval or category examples, prompt refinements, and organization-scoped preferences only through candidate → shadow/canary → promote → rollback, with regression gates and automatic rollback.
- **No legal conclusions.** ClearCut presents sourced findings and unresolved risk for qualified human review. Legal-boundary compliance is one of the ten judge dimensions; scoring rewards explicit pre-clearance framing, uncertainty, evidence grounding, and human governance. It is not a legal-clearance guarantee or a 100-point claim.

## Target Architecture (planned)

The target is a FastAPI modular monolith with bounded modules (identity, scripts, detection, research, decisions, collaboration, monitoring, evaluation, export) behind application services and typed events. Modules do not read each other's storage. External systems (Parallel, Gemini/ADK, Cloud Storage, Cloud Tasks) sit behind typed provider ports. TanStack Start and Astro consume OpenAPI-generated clients. The hosted target has three separately deployable services/images—`clearcut-site`, `clearcut-web`, and `clearcut-api`—with the API using Cloud SQL PostgreSQL, Cloud Storage, the deployment-selected local or Firebase identity adapter, Secret Manager, Cloud Tasks, Cloud Scheduler, Gemini/ADK, and Parallel. The browser uses a same-origin public workspace/API boundary with opaque revocable server sessions. Separate deployability does not mean separate backend microservices.

## Domain Context

ClearCut is a planned screenplay pre-clearance evidence workspace for independent producers, screenwriters, and clearance teams. It will parse scripts, detect items across ten protected categories, run mandatory Parallel Search with bounded Extract for source-backed evidence, coordinate human review with fixed roles, re-evaluate revisions, monitor source changes through scheduled Search/Extract and optional verified Monitor signals, and export reproducible version-bound dossiers. It supports evidence gathering and workflow coordination, not legal advice or final legal clearance. The submission targets the Parallel track of Agentic Cinema (deadline September 9, 2026 at 2:00 PM Pacific time).

## Tool Surface (Enabled Toolchains: (none))

- Agents/subagents
- Commands/prompts
- Skills
- Hooks
- Project steering/rules

## Regeneration

Run:

```bash
bun .agents/scripts/build.mjs
```

Strict check:

```bash
AGENTS_STRICT=1 bun .agents/scripts/build.mjs && bun .agents/scripts/lint.mjs && bun .agents/scripts/verify.mjs
```

Sign-off gate:

```bash
bun .agents/scripts/signoff.mjs
```

## Canonical Roots

- Personas: `.agents/personas`
- Commands: `.agents/commands`
- Skills: `.agents/skills`
- Hooks: `.agents/hooks/hooks.json`
- Rules: `.agents/rules`
- Steering: `.agents/steering`
- Memory: `.agents/memory/project-memory.md`

## Steering Index

- [agents](.agents/steering/agents.md)
- [coding-standards](.agents/steering/coding-standards.md)
- [product-map](.agents/steering/product-map.md)
- [product](.agents/steering/product.md)
- [structure](.agents/steering/structure.md)
- [tech](.agents/steering/tech.md)
- [testing-guidelines](.agents/steering/testing-guidelines.md)
- [ui-standards](.agents/steering/ui-standards.md)

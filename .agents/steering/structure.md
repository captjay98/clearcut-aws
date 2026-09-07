# Project Structure

## Current State

The repository contains implemented application, package, infrastructure, demo, documentation, and agent-configuration surfaces. Source implementation is not hosted evidence: Terraform remains unapplied, live paid-provider proof is absent, and the submission verdict is NO-GO.

## Repository Layout

```text
clearcut/
├── .agents/                    # canonical agent configuration
├── .kiro/                     # generated agent/client output; optional settings
├── .github/workflows/         # one-digest build, migration, and deployment contracts
├── apps/
│   ├── site/                   # Astro public pages
│   └── web/                    # TanStack Start workspace
├── services/
│   └── api/                    # FastAPI modular monolith and migrations
├── packages/
│   ├── contracts/              # OpenAPI source and generated clients
│   ├── design-system/          # mock-derived visual primitives
│   └── config/                 # shared build/lint/type configuration
├── infra/gcp/                  # fail-closed, unapplied Terraform foundation
├── demo/                       # screenplay fixtures and conditional runbook
├── misc/clearcut-flow/         # mock UI and visual baseline
├── docs/                       # architecture, ADRs, plans, and evidence ledgers
├── Dockerfile                  # one portable clearcut image
├── docker-compose.yml          # Local profile orchestration
└── LICENSE
```

## Deployment Structure

One immutable `clearcut` image contains compiled Astro and TanStack frontends, FastAPI, migrations, and scripts. FastAPI serves public routes, `/app/*`, `/api/*`, and protected `/api/internal/*`. Local, Portable Server, and GCP Starter use that image. GCP Starter uses one public Cloud Run service and a separate migration job pinned to the same digest.

Portable PostgreSQL dispatch and Firebase runtime composition remain deferred. Terraform and release workflows are source contracts, not evidence of provisioned or hosted resources.

## Backend Module Boundaries

`services/api/src/clearcut/` contains bounded identity, organization/project, scripts, detection, research, decisions, collaboration, monitoring, evaluation, export, records, and operations concerns. Modules communicate through typed events and application ports and never read another module's storage directly. External systems remain behind typed provider ports.

## Scope Conventions

Organization-owned resources use authenticated `org_id`. Project-owned resources require authenticated `org_id`, authorized `project_id`, and project membership. Explicit global catalogs are limited to role/capability definitions, category schema, and platform authority defaults. Global data never bypasses authorization.

## Source of Truth

`.agents/` is canonical. `AGENTS.md`, `.kiro/`, and `.agents/render-manifest.json` are generated outputs. Regenerate after canonical changes, then run strict lint, verify, and signoff. Kiro personas intentionally use built-in tools and MCP inclusion; user-level permissions are the security boundary.

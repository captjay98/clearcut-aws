# Project Structure

## Current State: Pre-implementation

Planning and design are complete; Plan 01 is next. The mock prototype at `misc/clearcut-flow/`, the planning documents, feature ledger, and `.agents/` canonical configuration are present. The product directories shown below are the **planned target structure** and must not be treated as existing runtime code until their plans are implemented.

## Planned Target Structure

```text
clearcut/
├── .agents/                    # canonical agent configuration; renders to .kiro/
├── .kiro/                     # generated output; optional project settings, never hand-edit
├── apps/
│   ├── site/                   # planned Astro marketing service (clearcut-site)
│   └── web/                    # planned TanStack Start workspace service (clearcut-web)
├── services/
│   └── api/                    # planned FastAPI modular monolith + Google ADK (clearcut-api)
├── packages/
│   ├── contracts/              # planned OpenAPI source + generated TS/Python clients
│   ├── design-system/          # planned shared visual primitives
│   └── config/                 # planned shared build/lint/type configuration
├── infra/
│   └── gcp/                    # planned Cloud Run/SQL/Storage/Tasks/Scheduler infrastructure
├── demo/                       # planned screenplay, fixtures, and expected results
├── misc/clearcut-flow/         # existing mock UI and 366-check visual baseline
├── docs/plans/                 # planning documents and ADRs
├── docs/feature-ledger.md      # existing 47-feature mapping
├── docs/product-plan.md        # product thesis and capability plan
├── docs/submission-strategy.md # competition and submission plan
└── LICENSE
```

The hosted target has three separately deployable services/images: Astro site, TanStack workspace, and FastAPI API. The API is one modular monolith with bounded modules—not a set of independent backend microservices. Separate images/services do not weaken module boundaries or OpenAPI contracts.

## Planned Backend Module Boundaries

`services/api/modules/` will contain identity, scripts, detection, research, decisions, collaboration, monitoring, evaluation, and export. Modules communicate through typed events/application services and never read another module's storage directly. External systems use typed provider ports.

## Scope Conventions

Organization-owned resources use authenticated `org_id`. Project-owned resources require authenticated `org_id` plus `project_id` and project-membership authorization. Explicitly global catalogs are limited to role/capability definitions, the ten category schema, and platform source-authority defaults. Organization policy, prompt, preference, retention, and privacy configurations and versions remain `org_id`-scoped. Global data is never a shortcut around authorization.

## Source of Truth

`.agents/` is the canonical agent source. `.kiro/` is generated output; project `.kiro/settings/` is optional and is not the security boundary. Kiro personas intentionally use built-in tools and MCP inclusion; safety is enforced by user-level `~/.kiro/settings/permissions.yaml`. Regenerate after canonical changes are ready, then run signoff; defer generation only when the active delegation explicitly reserves it.

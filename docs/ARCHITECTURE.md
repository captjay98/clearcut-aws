# ClearCut Architecture

**Status:** implemented local and portable runtime; hosted evidence remains NO-GO

**Style:** OpenAPI-first modular monolith in one portable application image

## System overview

One immutable `clearcut` image contains the compiled Astro site, compiled TanStack Start workspace, FastAPI application, Alembic migrations, and operational scripts. FastAPI is the sole public entry point and serves a same-origin surface:

```text
Browser
  -> FastAPI public runtime
       -> public Astro routes
       -> /app/*                 TanStack workspace
       -> /api/*                 authenticated application API
       -> /api/internal/*        authenticated task delivery only
            -> PostgreSQL
            -> configured object storage
            -> configured durable-job adapter
            -> optional paid providers behind runtime gates
```

This is one deployment unit, not a set of frontend and backend services. The backend remains a modular monolith with bounded storage ownership and typed application ports.

## Repository structure

```text
apps/site/                       # Astro source
apps/web/                        # TanStack Start workspace source
services/api/src/clearcut/       # FastAPI modular monolith
packages/contracts/              # OpenAPI source and generated clients
packages/design-system/          # mock-derived components and tokens
packages/config/                 # shared TypeScript/build configuration
infra/gcp/                       # fail-closed, unapplied Terraform foundation
demo/                            # entrant-owned fixtures and runbook
Dockerfile                       # one portable application image
docker-compose.yml               # Local profile orchestration
```

The mock at `misc/clearcut-flow/` remains the visual and interaction source of truth.

## Request and release flow

1. The image build compiles both frontends and packages their static output with the API runtime.
2. FastAPI serves public pages, the workspace, API routes, and protected internal delivery routes from one process boundary.
3. Database migration is a separate one-shot command using the exact same image digest. Application startup never migrates.
4. A candidate Cloud Run revision is created with no traffic.
5. GET-only smoke checks run against that exact candidate revision.
6. Only the verified revision may receive traffic.

The implemented workflows record one digest through build, migration, candidate, and promotion. They assume pre-existing authorized runtime and migration resources; Terraform does not yet provision the complete workload.

## Deployment profiles

Local, Portable Server, and GCP Starter use the same image and select adapters through validated configuration.

| Concern        | Local                                           | Portable Server                          | GCP Starter                                              |
| -------------- | ----------------------------------------------- | ---------------------------------------- | -------------------------------------------------------- |
| Database       | Compose PostgreSQL or configured local database | Existing PostgreSQL                      | Existing PostgreSQL or separately acknowledged Cloud SQL |
| Object storage | Filesystem                                      | Filesystem or S3-compatible              | GCS                                                      |
| Durable jobs   | Local dispatcher                                | Intended PostgreSQL-backed dispatcher    | Cloud Tasks with OIDC-authenticated internal delivery    |
| Secrets        | Environment/local configuration                 | Environment or operator secret injection | Secret Manager references                                |
| Identity       | Built-in opaque sessions                        | Built-in opaque sessions                 | Built-in opaque sessions by default                      |
| Paid providers | Disabled by default                             | Disabled by default                      | Disabled by default                                      |

Portable PostgreSQL dispatch is not yet wired into application composition, so Portable Server is not yet a complete production worker profile. Firebase runtime composition is not yet wired; the runtime currently composes built-in identity even though Firebase settings are validated. These gaps are explicit deferrals, not silent fallbacks.

## Backend boundaries

Identity, organizations, projects, scripts, detection, research, decisions, collaboration, monitoring, evaluation, export, records, and operations communicate through typed application ports or versioned events. Modules do not import another module's ORM models or query its tables.

```text
domain <- application <- adapters <- delivery
```

- Domain code does not depend on FastAPI, SQLAlchemy, provider SDKs, UI frameworks, environment access, clocks, or random-ID generation.
- Application services receive authorization, provider, task, storage, clock, identifier, and unit-of-work ports.
- Adapters translate third-party data into typed domain results or typed errors.
- Delivery authenticates, validates, invokes an application service, and serializes the declared contract.

## Evidence and governance invariants

- A `ClearanceItem` may have zero claims while research is pending, unavailable, failed, or empty. Zero evidence is unresolved, never clearance.
- Every `EvidenceClaim` cites a recorded source snapshot with URL, retrieval time, attributable excerpt, authority classification, stance, query/run identity, and provenance.
- Provider failures create visible review work and never fabricated fallback evidence.
- Governed decisions and report generation/release require an accountable human and a same-transaction authoritative audit event.
- Organization-owned records use authenticated organization scope; project-owned records additionally require authorized project scope.

## Jobs and provider controls

Durable jobs are idempotent, leased, retryable, and reconciled from queued state when dispatch is stranded. GCP Starter dispatches through Cloud Tasks; task OIDC issuer, audience, and dedicated service-account claims are verified before repository access.

Gemini and Parallel are disabled unless configuration explicitly acknowledges cost and sets a positive bounded concurrency limit. Runtime gates acquire a provider-specific permit before resolving or calling a paid client. No paid call is authorized by documentation, tests, or profile selection alone.

## Current evidence boundary

No hosted deployment is currently verified. No Terraform plan/apply, cloud mutation, provider call, backup/restore drill, hosted smoke test, or cost evidence is implied by the implemented source. `docs/submission/manifest.yaml` remains the authoritative GO/NO-GO ledger. See ADR 0004 for the deployment decision and ADR 0003 for the still-applicable Terraform governance decisions.

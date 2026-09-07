# ADR 0004: Portable Single-Service Deployment

## Status

**Accepted** (2026-08-31)

## Context

ClearCut targets independent filmmakers and small clearance teams. A topology with separate site, workspace, and API workloads would add image, release, identity, networking, and minimum-instance decisions without improving the current modular-monolith boundary. It would also make the open-source path harder to operate outside Google Cloud.

The repository already has Astro, TanStack Start, FastAPI, PostgreSQL persistence, typed storage and task ports, and a same-origin browser/API contract. The deployment shape should preserve those boundaries while minimizing hosted cost and operator burden.

## Decision

### 1. One portable application image

ClearCut builds one immutable image named `clearcut`. It contains the compiled Astro site, compiled TanStack workspace, FastAPI runtime, Alembic migrations, and operational scripts. FastAPI is the only public process and serves public pages, `/app/*`, `/api/*`, and protected `/api/internal/*` routes.

The image is a deployment package, not a license to collapse backend module ownership. Modules continue to communicate through typed application ports and events and do not read another module's storage.

### 2. One hosted service and one same-digest migration job

GCP Starter uses one public Cloud Run service named `clearcut`. Database migrations run as a separate one-shot job using the exact application image digest. Startup never runs migrations. Release automation creates a no-traffic candidate, performs GET-only smoke checks against the exact revision, and promotes only that revision.

Artifact Registry uses one repository contract named `clearcut`. Build, migration, deployment, and submission evidence carry one immutable digest.

### 3. Three configuration profiles

- **Local:** Compose PostgreSQL, filesystem storage, local dispatch, and built-in opaque sessions.
- **Portable Server:** an existing PostgreSQL database plus filesystem or S3-compatible storage. PostgreSQL durable dispatch is the intended portable worker, but it is not yet wired into runtime composition.
- **GCP Starter:** one Cloud Run service, GCS, Cloud Tasks, Secret Manager, and an existing PostgreSQL database or separately acknowledged Cloud SQL.

All profiles use the same image. Configuration selects adapters; it does not change evidence, governance, authorization, or legal-boundary rules.

### 4. Conservative identity and provider defaults

Built-in opaque revocable sessions are the default. Firebase/Identity Platform remains an optional adapter boundary, but current runtime composition still selects built-in identity and must not be described as Firebase-enabled.

Gemini and Parallel are disabled by default. Enabling a paid provider requires explicit cost acknowledgement, a positive bounded concurrency limit, credentials, and authorized quota. Provider failure remains typed and visible; there is no fallback evidence.

### 5. Truthful infrastructure boundary

Terraform remains fail-closed and unapplied. GCP workflows assume pre-existing authorized runtime, migration, identity, and data resources; they do not prove those resources exist. A hosted release, provider trace, recovery drill, or production-readiness claim requires external evidence in the submission manifest.

## Supersession scope

This ADR supersedes only ADR 0003's original deployment-topology premise. ADR 0003 remains accepted for Terraform CLI, portable HCL, state protection, environment isolation, Workload Identity Federation, apply approval, existing-resource disposition, and recovery governance.

## Consequences

- A clean clone has one image contract across laptops, generic container hosts, and GCP.
- GCP Starter can begin with one billed application service rather than coordinating independent web and API workloads.
- Frontend assets and API releases are atomic and roll back together.
- The public same-origin session boundary is simpler to reason about.
- The image is larger and frontend/API scaling cannot be tuned independently.
- A frontend-only change still releases the whole image.
- Portable production jobs and optional Firebase identity require follow-up runtime composition before those profiles can be claimed complete.
- Hosted operation remains NO-GO until separately authorized external verification exists.

## Rejected alternatives

- **Independent site, workspace, and API workloads:** rejected for current cost and operational complexity. Reconsider only with measured scaling or isolation evidence and a new ADR.
- **Cloud Tasks in every profile:** rejected because it would make the open-source runtime depend on Google Cloud.
- **In-process production background work:** rejected because process restarts and scaling cannot provide durable execution semantics.
- **A permanently running PostgreSQL worker on GCP:** deferred to avoid an additional always-on workload in the starter profile.
- **Automatic Cloud SQL provisioning:** rejected as a default because operators may already have PostgreSQL and Cloud SQL incurs material cost. Any managed database adoption requires explicit acknowledgement and infrastructure review.

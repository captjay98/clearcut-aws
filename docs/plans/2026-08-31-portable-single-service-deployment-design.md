# Portable Single-Service Deployment Design

**Status:** Approved

**Date:** 2026-08-31

## Purpose

ClearCut needs an open-source deployment path that is inexpensive, portable, and usable by independent filmmakers, nontechnical operators, and automation agents. The hosted default must not require three continuously deployed services, provider-specific application logic, or unapproved cloud spending.

This design replaces the planned three-image, three-service default with one immutable application image and three guided deployment profiles. It preserves ClearCut's evidence provenance, tenant isolation, human governance, and fail-closed provider behavior.

## Design Goals

- Publish and promote one immutable `clearcut` image digest.
- Run one public application service by default.
- Provide a clear GCP-native happy path without making GCP a core-domain dependency.
- Support local and Docker-capable hosts through typed adapters.
- Keep fixed cloud costs optional and visible before provisioning.
- Make setup safe and understandable for people and noninteractive agents.
- Never create cloud resources, import existing resources, or invoke paid providers without explicit approval.

## Non-Goals

- Maintaining the rejected three-service topology as a supported advanced profile.
- Automatically adopting existing cloud resources into Terraform state.
- Providing presets for every hosting vendor.
- Treating SQLite or an ephemeral container filesystem as hosted production storage.
- Enabling Gemini, Vertex AI, or Parallel by default.
- Replacing qualified human review with an automated legal-clearance conclusion.

## Core Architecture

ClearCut publishes one immutable container image containing:

- Astro public-site assets;
- TanStack authenticated-workspace assets;
- the FastAPI application and API;
- the database migration command; and
- the PostgreSQL worker runtime used by portable deployments.

FastAPI is the single public entry point and serves all browser surfaces from the same origin:

- `/` and public routes serve the Astro site;
- `/app/*` serves the TanStack workspace;
- `/api/*` serves the application API; and
- a dedicated protected route accepts authenticated job-execution requests.

The GCP Starter profile deploys one public Cloud Run service with scale-to-zero enabled. A Cloud Run migration job may run temporarily before traffic promotion, but it must use the exact application image digest selected for deployment. It is not a second persistent service.

Cloud Tasks invokes the protected execution route on the same Cloud Run service. The application verifies the token issuer, audience, and dedicated caller identity before loading a job. No load balancer, browser-to-API proxy service, separate worker service, or second production image is required.

The Portable Server profile runs the same image on a Docker-capable host. Its default runtime combines HTTP serving with the PostgreSQL-backed worker loop in one application container. The image may expose the worker as a separate command for operators who later need independent scaling, but that is not the starter topology.

Local development continues through Docker Compose. The generated Cloud Run HTTPS URL or host-provided HTTPS endpoint is sufficient for initial deployment. Custom-domain configuration is an optional post-deployment step.

## Deployment Profiles

The guided setup selects validated adapters rather than changing domain behavior.

| Capability     | Local                          | Portable Server                     | GCP Starter                               |
| -------------- | ------------------------------ | ----------------------------------- | ----------------------------------------- |
| Application    | Docker Compose                 | One `clearcut` container            | One Cloud Run service                     |
| Database       | Compose PostgreSQL             | Existing PostgreSQL                 | Existing PostgreSQL or optional Cloud SQL |
| Object storage | Local filesystem               | Filesystem or S3-compatible storage | GCS by default; R2/S3-compatible optional |
| Job dispatch   | In-process, one web worker     | PostgreSQL-backed worker loop       | Cloud Tasks                               |
| Authentication | Built-in accounts and sessions | Built-in by default                 | Built-in by default; Firebase optional    |
| Secrets        | Local environment file         | Host secret mechanism               | Secret Manager                            |
| HTTPS          | Local development              | Host or reverse proxy               | Generated Cloud Run URL                   |

### GCP-Native Defaults

The GCP Starter is intentionally opinionated:

- **Cloud Run** is the application runtime.
- **GCS** is the default object store.
- **Cloud Tasks** is the default durable dispatcher.
- **Secret Manager** stores production secrets.
- **Cloud SQL** is recommended when the operator does not already have PostgreSQL.
- **Built-in accounts and server sessions** remain the authentication default.
- **Firebase Authentication** is an optional managed identity adapter.

Cloud SQL is the important exception to automatic recommendation flow because it introduces meaningful fixed cost. Setup must offer an existing PostgreSQL connection first, show a cost warning before Cloud SQL provisioning, and require a distinct acknowledgement.

R2 and other S3-compatible services remain available as advanced storage choices when their cost model is preferable. These choices do not alter the evidence or governance model.

## Adapter Boundaries

Application services continue to depend on typed ports. Startup selects concrete adapters from validated configuration:

- `ObjectStoragePort`: filesystem, GCS, or S3-compatible;
- job dispatch: local, PostgreSQL worker, or Cloud Tasks;
- identity: built-in identity/session adapter or optional Firebase adapter; and
- database: PostgreSQL through the existing SQLAlchemy boundary.

Unsupported, incomplete, or contradictory combinations fail during setup and startup. The application must not silently switch to a cheaper, local, or less durable fallback.

Hosted profiles require PostgreSQL and durable object storage. SQLite and container-local ephemeral storage are local-development options only.

Cloud SQL, GCS, Cloud Tasks, Secret Manager, and Firebase are GCP-profile capabilities rather than assumptions embedded in the core domain.

## Job Execution Flow

Detection, research, reevaluation, monitoring, and report preparation use the existing durable job model:

1. FastAPI authenticates the actor, validates organization and project scope, and persists a job in PostgreSQL.
2. The configured dispatcher sends only the job identity and minimum scoped execution metadata.
3. The executor claims the job through the typed repository and existing lease protocol.
4. The executor reloads authoritative state from PostgreSQL and invokes the typed application service.
5. Long-running execution renews its lease and records visible progress.
6. The executor persists typed success or failure before returning.
7. Recovery identifies expired leases and creates visible retry or review work rather than silently losing execution.

Dispatch differs by profile:

- Local uses the existing in-process dispatcher and enforces one web worker.
- Portable Server claims persisted work through a PostgreSQL-backed worker loop.
- GCP Starter creates a Cloud Task that calls the protected execution route with OIDC authentication.

Retries are idempotent. An already-completed job returns success without repeating provider work. Lease loss, invalid scope, authentication failure, and provider failure remain typed and visible.

## Evidence and Governed Actions

The deployment architecture does not weaken ClearCut's domain constraints:

- An `EvidenceClaim` requires a cited Parallel `SourceSnapshot` with complete provenance.
- No result, provider failure, or unavailable research remains unresolved and never becomes clearance.
- Provider failures create visible review items; they do not trigger invented fallback evidence.
- Approvals, dispositions, governed report generation, and release/export remain accountable human actions.
- Governed state changes and their immutable audit events commit transactionally.
- Organization- and project-owned records retain authenticated tenant scope.
- ClearCut presents sourced findings and uncertainty for qualified review, not legal conclusions.

## Provider Spending Controls

Gemini, Vertex AI, and Parallel are disabled in a fresh installation. Enabling a paid provider requires:

- valid credentials;
- explicit provider enablement;
- per-run request, result, or token limits as applicable;
- concurrency limits;
- an explicit cost acknowledgement; and
- visible configuration in the redacted deployment summary.

Missing controls cause provider work to fail closed. Setup validation must not make a paid provider call. Live provider smoke tests are separately authorized actions.

## Guided Setup

One guided setup interface supports both interactive users and noninteractive agents. It asks only questions relevant to the selected profile and emits machine-readable status alongside concise human output.

The workflow is split into six phases:

1. **Configure** selects the profile and adapters.
2. **Validate** checks tools, configuration, connectivity, and permissions without creating resources.
3. **Plan** reports intended resources, cost-sensitive choices, and material side effects.
4. **Approve** records an explicit confirmation for the exact plan.
5. **Deploy** executes only the approved saved plan.
6. **Verify** runs migrations and profile-appropriate smoke tests.

Safety requirements:

- Configure and validate never run Terraform apply, import resources, invoke paid providers, or mutate cloud resources.
- Existing resources remain referenced but unmanaged until an explicit disposition is approved.
- Cloud SQL creation and paid-provider activation require separate cost acknowledgements.
- Secrets go directly to the selected secret backend and never appear in logs, generated files, or summaries.
- Noninteractive execution requires explicit flags or approval tokens equivalent to interactive confirmation.
- Re-running setup is idempotent and reports drift instead of silently replacing resources.
- Custom domains and DNS changes are optional post-deployment operations.

## Infrastructure and Release Model

Terraform remains fail-closed and provider-portable HCL. Production defaults manage zero resources. Resource management switches, existing-resource dispositions, API side-effect acknowledgement, and saved-plan approval remain separate controls.

The architecture amendment changes the release contract to:

- one Artifact Registry repository/image path named `clearcut`;
- one build producing one immutable digest;
- one migration execution using that same digest;
- one candidate Cloud Run revision deployed without traffic;
- candidate health and functional smoke checks before promotion; and
- one traffic promotion after all gates pass.

A failed migration or candidate smoke test prevents traffic promotion. The previous revision remains active. Rollback selects an earlier immutable digest. Database migrations must remain compatible across the rollout window.

The previous `site`, `web`, and `api` repository keys, three digest inputs, three service URLs, and three-service submission evidence are removed from the default contract. The rejected topology is not retained as a maintained profile without a future evidence-backed design decision.

## Verification Strategy

Implementation verification must include:

- unit and contract tests for profile configuration and adapter selection;
- mocked adapter tests for Cloud Tasks, GCS, S3-compatible storage, Secret Manager, and optional Firebase;
- PostgreSQL-worker tests for claims, leases, retries, idempotency, interruption, and recovery;
- Terraform native tests proving zero-resource defaults and explicit approval gates;
- container smoke tests for the public site, workspace, API, and migration command;
- profile-level smoke tests for Local, Portable Server, and GCP Starter;
- candidate-revision checks before Cloud Run traffic promotion; and
- existing evidence provenance, tenant-isolation, governed-action, and submission gates.

Provider-free verification remains the normal local and CI path. Live cloud or provider verification requires explicit authorization and records the exact environment and immutable image digest used.

## Required Repository Alignment

Implementation must update these sources together so stale three-service constraints cannot remain authoritative:

- `docs/ARCHITECTURE.md` and deployment guidance;
- canonical `.agents` steering, memory, and generated guidance;
- the root `Dockerfile` and static-route composition;
- build, migration, and deployment workflows;
- Terraform Artifact Registry contracts and future workload modules;
- deployment-boundary and Terraform tests; and
- submission manifest fields and readiness gates.

Generated agent files must be changed through the canonical `.agents` source and rebuilt with the repository generator.

## Decision Summary

ClearCut adopts one image with profile-selected adapters. The default GCP path leans on Cloud Run, GCS, Cloud Tasks, Secret Manager, and optionally Cloud SQL while preserving an existing-PostgreSQL choice and portable S3-compatible storage. Local and portable deployments use the same domain model and image. Setup and provider use remain explicit, cost-aware, and fail-closed.

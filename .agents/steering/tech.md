# Tech Stack

## Runtime

ClearCut has an implemented one-image runtime. One immutable `clearcut` image packages compiled Astro and TanStack frontends, the FastAPI application, Alembic migrations, and operational scripts. FastAPI is the sole public entry point.

## Backend

- **Framework:** FastAPI modular monolith
- **Language:** Python 3.12+
- **ORM/DB:** SQLAlchemy 2.0 and Alembic on PostgreSQL
- **Auth:** built-in identity behind opaque revocable application sessions; Firebase/Identity Platform is validated as an optional boundary but is not wired into runtime composition
- **AI/Agent:** Google ADK and Gemini behind typed ports, disabled by default
- **Research:** mandatory Parallel Search plus bounded Extract when authorized; conditional Monitor after a recorded GO
- **Jobs:** local dispatch or OIDC-authenticated Cloud Tasks; Portable PostgreSQL dispatch remains deferred
- **Storage:** filesystem, GCS, or S3-compatible object storage behind typed ports
- **Secrets:** local configuration or Secret Manager references

Paid providers require explicit cost acknowledgement and positive bounded concurrency before client resolution or a paid call. Provider failures remain typed and visible.

## Frontend

- **Public pages:** Astro, compiled into the unified image
- **Workspace:** TanStack Start, compiled into the unified image and served under `/app/*`
- **State:** TanStack Query
- **Styling:** ClearCut design system derived from `misc/clearcut-flow/`; no external visual component library
- **Themes:** Script and Night shoot
- **Responsive range:** 320–1440px; Frontend owns implementation and Mobile reviews parity

## Deployment Profiles

| Profile         | Database                                      | Storage                     | Jobs                                       | Secrets            |
| --------------- | --------------------------------------------- | --------------------------- | ------------------------------------------ | ------------------ |
| Local           | Compose or configured PostgreSQL              | Filesystem                  | Local                                      | Environment/local  |
| Portable Server | Existing PostgreSQL                           | Filesystem or S3-compatible | PostgreSQL dispatcher intended but unwired | Operator injection |
| GCP Starter     | Existing PostgreSQL or acknowledged Cloud SQL | GCS                         | Cloud Tasks                                | Secret Manager     |

GCP Starter has one public Cloud Run `clearcut` service and a separate same-digest migration job. Release automation uses one digest, a no-traffic candidate, GET-only smoke, and exact-revision promotion. Terraform is unapplied and does not provision the complete workload.

## Key Decisions

- One portable image and one public application service, not independent frontend/API workloads.
- Modular monolith, not backend microservices.
- PostgreSQL, not Firestore, for relational evidence, version, and audit integrity.
- Built-in sessions by default; Firebase remains optional and currently unwired.
- Same-origin opaque session cookies with CSRF and Origin validation.
- Fixed roles: Owner, Admin, Editor, Reviewer, Viewer.
- OpenAPI-first contracts with generated-client drift checks.
- Mock-derived visual implementation.
- Typed provider results/errors and ownership-aware tenant scope.
- Cloud/provider evidence is never inferred from local source tests.

## Agent Configuration Boundary

Kiro personas intentionally use `tools: ["@builtin"]` and `includeMcpJson: true`. Safety and approval enforcement come from user-level `~/.kiro/settings/permissions.yaml`; project `.kiro/settings/` is optional generated configuration.

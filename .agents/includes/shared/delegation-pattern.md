# ClearCut Delegation Pattern

ClearCut is an implemented full-stack product: FastAPI modular monolith, TanStack workspace, Astro site, OpenAPI contracts, one portable image, and fail-closed Google Cloud controls. Delegate to the specialist that owns the concern and distinguish source implementation from hosted or provider evidence.

## Scope and Ownership

- **Backend implementation** — `backend-engineer`: FastAPI, SQLAlchemy/Alembic, provider ports, research jobs, and governed actions.
- **Frontend implementation** — `frontend-engineer`: TanStack routes, Astro pages, design-system implementation, accessibility, and user-facing state.
- **Contract-first vertical slices** — `fullstack-engineer`: OpenAPI, generated clients, backend, and frontend as one reviewed slice.
- **Responsive parity review** — `mobile-engineer`: review 320–1440px and route fixes to Frontend.
- **Domain and workflow design/review** — `product-architect`: domain model, categories, workflow, rubric, policy, and acceptance criteria.
- **Security design/review** — `security-engineer`: approvals, provenance, tenant isolation, prompt injection, uploads, SSRF, and secrets.
- **Infrastructure** — `devops-engineer`: one `clearcut` image, Local/Portable/GCP profiles, same-digest migration, Cloud Run/SQL/Storage/Tasks/secrets, CI/CD, and observability.
- **Verification and test strategy** — `qa-engineer`: parser, evidence, governed-action, security, contract, accessibility, deployment-boundary, and Playwright coverage.
- **Read-only investigation** — `explorer`; **mechanical transforms** — `codex`; **lint cleanup** — `janitor`; **verification reports** — `triager`.
- **Scaffolding** — `scaffolder`, only after a real sibling pattern exists. It never invents architecture or leaves TODO markers.

## Data Ownership and Tenant Scope

- **Organization-owned:** organizations, memberships, invitations, organization settings, retention/privacy configuration, and organization-scoped learning preferences. Query with authenticated `org_id`.
- **Project-owned:** projects and screenplay workflow records. Query with authenticated `org_id` plus `project_id`; verify project ownership and membership.
- **Explicitly global:** immutable role/capability definitions, the ten category schema, and platform source-authority defaults. These contain no tenant screenplay data and change only through accountable human governance.

## Evidence and Deployment Boundaries

Detection may create a project-owned `ClearanceItem` with zero claims while research is pending, empty, unavailable, or failed. Every admitted `EvidenceClaim` cites a Parallel `SourceSnapshot` with URL, retrieval time, attributable excerpt, authority classification, stance, query/run identity, and provenance. Never invent fallback evidence.

One immutable image serves every profile. FastAPI is the sole public entry point, and GCP Starter uses one public service plus a same-digest migration job. Portable PostgreSQL dispatch and Firebase runtime composition remain deferred. Gemini and Parallel default disabled and require cost acknowledgement plus bounded concurrency. Never turn local tests into a hosted, provider, recovery, or production claim.

## Structured Handoff Format

```text
DELEGATING TO: @<persona>
TASK: <one sentence>
CONTEXT:
  - Relevant files: <real paths>
  - Current state: <implemented, absent, broken, or externally unverified>
CONSTRAINT: <invariants and forbidden mutations/calls>
ACCEPTANCE: <exact command, artifact, or review output>
```

## How To Delegate

1. Select the owner and state whether work is implementation, design, review, or external evidence collection.
2. Name real files and identify any deferred runtime composition.
3. Include tenant, evidence, governance, cost, and deployment truth boundaries.
4. Request checkable acceptance output.
5. Review the result before closing the handoff.

## Example

```text
DELEGATING TO: @devops-engineer
TASK: Verify the one-digest release workflow without mutating cloud resources.
CONTEXT:
  - Relevant files: Dockerfile, .github/workflows/build.yml, .github/workflows/migrate.yml, .github/workflows/deploy.yml
  - Current state: source contracts exist; Docker and hosted evidence may be unavailable
CONSTRAINT: Do not call GCP, plan/apply Terraform, invoke paid providers, or claim a hosted release. Migration must use the exact application digest and promotion must target the smoke-tested revision.
ACCEPTANCE: Focused release-boundary tests, workflow lint when available, exact command output, and explicit unavailable checks.
```

# ClearCut Delegation Pattern

ClearCut is a planned full-stack product: FastAPI modular monolith, TanStack Start workspace, Astro site, OpenAPI contracts, and Google Cloud deployment. Delegate to the specialist that owns the concern; do not imply that a planned directory or runtime already exists.

## Scope and Ownership

- **Backend implementation** — `backend-engineer`: FastAPI routes and services, SQLAlchemy/Alembic, provider ports, research jobs, governed actions.
- **Frontend implementation** — `frontend-engineer`: TanStack Start routes and components, Astro pages, design-system implementation, accessibility, and user-facing state handling.
- **Contract-first vertical slices** — `fullstack-engineer`: OpenAPI contract, generated clients, backend, and frontend as one reviewed slice.
- **Responsive parity review** — `mobile-engineer`: review every implemented surface at 320–1440px, identify parity/accessibility issues, and route fixes to `frontend-engineer`; it is not the primary UI implementer.
- **Domain and workflow design/review** — `product-architect`: domain model, category definitions, workflow, rubric, policy boundaries, and acceptance criteria; delegate production implementation.
- **Security design/review** — `security-engineer`: approval boundaries, provenance, tenant isolation, prompt-injection defense, upload/SSRF/secret controls; delegate production fixes.
- **Infrastructure** — `devops-engineer`: the three separately deployable services/images (`clearcut-site`, `clearcut-web`, `clearcut-api`), Cloud SQL, storage, tasks, scheduler, secrets, CI/CD, and observability.
- **Verification and test strategy** — `qa-engineer`: parser, evidence, governed-action, security, contract, accessibility, and Playwright coverage.
- **Read-only investigation** — `explorer`; **mechanical transforms** — `codex`; **lint-only cleanup** — `janitor`; **verification reports** — `triager`.
- **Scaffolding** — `scaffolder`, only after the relevant Plan 01+ foundation and a real sibling pattern exist. It never invents production architecture or leaves TODO markers.

## Data Ownership and Tenant Scope

Use the narrowest valid scope; never apply a blanket two-column rule to every query.

- **Organization-owned:** organizations, memberships, invitations, organization settings, retention/privacy configuration, and organization-scoped learning preferences. Query with authenticated `org_id`; project scope is not required unless the resource is also project-owned.
- **Project-owned:** projects and all screenplay workflow records—scripts, immutable versions, elements, `ClearanceItem`s, research runs, `EvidenceClaim`s, source snapshots, conflicts, assignments, comments, monitoring, decisions, receipts, and exports. Query with authenticated `org_id` plus the `project_id` path scope; verify the project belongs to that organization.
- **Explicitly global:** immutable platform catalogs and protected defaults such as role/capability definitions, the ten category schema, and platform source-authority defaults. These are not tenant records, must not contain user data, and may only change through accountable human governance. Organization policy, prompt, preference, retention, and privacy configurations and versions remain organization-scoped.

An organization-level query is scoped by `org_id`; a project-level query is scoped by both `org_id` and `project_id`; a global catalog query is explicitly global and must never be used to bypass tenant authorization.

## Evidence Boundary

Detection may create a project-owned `ClearanceItem` before research runs, while it has zero evidence claims. Valid zero-evidence states include research pending, no results, provider failure, and evidence unavailable; they never mean clear or safe. An `EvidenceClaim` is only persisted or displayed as evidence when it cites a `SourceSnapshot` with a Parallel URL, retrieval time, attributable excerpt, publisher/authority classification, stance, query/run identity, and provenance. Never fill an empty item with invented evidence.

## Structured Handoff Format

When delegating, use this format:

```
DELEGATING TO: @<persona>
TASK: <one sentence — what needs to be done>
CONTEXT:
  - Relevant files: <list paths, or say planned/not yet present>
  - Current state: <what exists now, what is absent, and what is broken>
CONSTRAINT: <what must not change and which invariants apply>
ACCEPTANCE: <exact command, test, artifact, or review output>
```

## How To Delegate

1. Select the owner and state whether the work is design/review or implementation.
2. Name real files; explicitly label planned paths that do not exist yet.
3. Include the applicable org/project/global scope and evidence/provenance constraints.
4. Request checkable acceptance output, including the relevant test or audit command.
5. Review the result against the acceptance criteria before closing the handoff.

## ClearCut Example

```
DELEGATING TO: @fullstack-engineer
TASK: Add the project-scoped evidence summary endpoint and its review surface.
CONTEXT:
  - Relevant files: packages/contracts/openapi.yaml; planned services/api/modules/research/; planned apps/web/
  - Current state: Plan 01 is pre-implementation; those runtime directories are not present yet; the OpenAPI contract is the source of truth.
CONSTRAINT: Scope reads by authenticated org_id and project_id; a ClearanceItem may have zero claims, but every EvidenceClaim must cite a recorded Parallel SourceSnapshot; no legal conclusion or fabricated fallback evidence.
ACCEPTANCE: Contract drift check, backend tests, frontend typecheck/tests, and a review showing the source URL, retrieval time, authority, stance, excerpt, and conflict state.
```

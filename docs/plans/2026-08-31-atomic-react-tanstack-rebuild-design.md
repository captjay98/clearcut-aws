# Atomic React and TanStack Rebuild Design

**Date:** 2026-08-31  
**Status:** Approved  
**Decision:** Replace the production web application atomically. Do not retain or adapt the legacy runtime.

## Context

The approved frontend architecture called for a React workspace built with TanStack Start and Router, generated API clients, organization/project route scopes, and production exclusion of prototype behavior. The current executable application does not satisfy that architecture:

- `apps/web/src/main.tsx` imports `runtime.js` instead of mounting React.
- `runtime.js` is a descendant of the dependency-free mock runtime and remains the active router, state store, renderer, and action dispatcher.
- TanStack Start, Router, and Query are not installed.
- React routes and feature components exist but are not reachable from the production entry point.
- Production loaders contain fixture fallbacks and fixed success-shaped data.
- Several API endpoints return fixed responses or query project-owned data without complete tenant scope.
- Existing verification evidence proves component symbol presence, not production route reachability or end-to-end behavior.

The replacement must correct both the frontend runtime and the incomplete backend capabilities. Replacing only the renderer would preserve fabricated behavior behind a new UI.

## Decision

Build a complete replacement in an isolated branch or worktree and perform one product cutover after all acceptance gates pass.

The replacement branch removes the legacy runtime at the beginning of implementation. It may be incomplete during development, but it must never execute, translate, or preserve legacy runtime behavior. The currently deployed release may remain available until cutover, but no mixed old/new frontend ships.

## Goals

- Replace the mock-derived DOM runtime with React and TanStack.
- Make the API and database authoritative for all domain and workflow state.
- Implement every agreed product surface end to end before cutover.
- Use generated OpenAPI clients as the only browser-to-API transport.
- Enforce authenticated organization and project scope on every owned record.
- Preserve evidence provenance, uncertainty, and human governance invariants.
- Keep an explicitly labeled, server-owned demo dataset that uses normal production APIs.
- Prove reachable behavior with integration and browser tests.

## Non-goals

- Incrementally wrapping or porting `runtime.js` behavior.
- Supporting hash routes or translating legacy runtime actions.
- Preserving browser-local domain records, receipts, timers, or fake jobs.
- Treating source presence or component construction as implementation evidence.
- Inventing evidence, successful mutations, or fallback domain data when services fail.

## Target architecture

```text
Browser
  -> TanStack Start and Router
  -> TanStack Query
  -> generated OpenAPI client
  -> same-origin /api/v1
  -> FastAPI application services
  -> bounded domain modules and typed ports
  -> PostgreSQL and external providers
```

### Frontend responsibilities

TanStack Start owns the workspace application boundary. TanStack Router owns typed routes, nested layouts, route parameters, loaders, pending states, and error boundaries. TanStack Query owns remote server state, mutation execution, invalidation, and retry policy.

React component state is limited to transient presentation concerns such as open dialogs, draft form fields, and local selection. It does not own persisted domain records, authorization, audit history, job state, evidence, or workflow status.

Feature routes consume ClearCut design-system components and generated client adapters. Route components compose features; they do not contain domain rules or direct transport code.

### Route hierarchy

```text
/auth/sign-in
/auth/invite/$token
/onboarding

/o/$orgSlug
/o/$orgSlug/projects
/o/$orgSlug/team
/o/$orgSlug/notifications
/o/$orgSlug/records
/o/$orgSlug/trust
/o/$orgSlug/settings

/o/$orgSlug/projects/$projectId
/o/$orgSlug/projects/$projectId/workspace
/o/$orgSlug/projects/$projectId/items
/o/$orgSlug/projects/$projectId/items/$itemId
/o/$orgSlug/projects/$projectId/versions
/o/$orgSlug/projects/$projectId/watch
/o/$orgSlug/projects/$projectId/report
```

Route loaders establish authenticated organization and project scope before child routes render. Direct navigation and refresh must work for every route.

### API boundary

OpenAPI is the executable contract source of truth. Each operation defines typed requests, successful responses, and error responses. Client generation must produce working HTTP operations, not only TypeScript metadata.

Production frontend code must not call `fetch` directly. A generated transport adapter handles same-origin credentials, request correlation, decoding, and typed errors. Network and HTTP failures remain failures; they never become empty objects or fixture values.

### Server authority

The API is authoritative for:

- identities, credentials, sessions, invitations, and onboarding;
- organizations, memberships, capabilities, policies, and projects;
- scripts, parsing results, scenes, and immutable versions;
- detection and research runs;
- clearance items, source snapshots, and evidence claims;
- decisions, comments, assignments, referrals, and rewrites;
- revision comparison and affected-item rescans;
- monitoring schedules, source changes, and notifications;
- trust/evaluation views and governed learning candidates;
- dossier generation, review, release, export, and audit records;
- organization preferences, retention, and privacy settings.

No fixed-response endpoint qualifies as implemented. A visible mutation must validate scope and capability, persist its result, return a typed response, and create required audit events transactionally.

## Legacy removal boundary

The replacement removes:

- `apps/web/src/runtime.js` and its import from the entry point;
- the hand-written hash-switching `App.tsx`;
- fixture-fallback production loaders;
- direct browser transport outside the generated client;
- browser-owned authorization and workflow state;
- timer-simulated detection, research, rescan, watch, and report work;
- local audit receipts and fabricated mutation success;
- prototype sitemap/state routes from production;
- production imports from test fixtures.

No compatibility module may execute legacy actions, hydrate legacy local storage, translate hash routes, or reuse the legacy state reducer.

## Demo dataset

The demo remains as an explicitly labeled, server-owned organization and project dataset.

- Backend initialization or a dedicated bootstrap operation creates it idempotently.
- API responses identify demo resources explicitly.
- The UI displays a persistent demo label.
- Demo users access and mutate data through the same authorization, application-service, repository, and audit paths as non-demo users.
- The frontend contains no special demo state machine and no fixture substitution.
- Demo evidence claims retain real source-snapshot provenance. Zero evidence remains unresolved.

## Failure behavior

All boundaries use typed results or typed errors. Route and feature boundaries distinguish:

- unauthenticated;
- unauthorized or forbidden;
- organization or project not found;
- valid empty data;
- validation failure;
- provider unavailable;
- retryable system failure;
- non-retryable domain conflict.

Failed mutations leave server and browser state unchanged. Governed actions do not use optimistic updates. Provider failures create visible review states where required and never fabricate evidence or successful completion.

## Security and transactional integrity

Every project-owned operation validates:

```text
authenticated session
  -> organization membership
  -> organization path scope
  -> project ownership in that organization
  -> required role or capability
  -> active policy version when applicable
```

Global queries and first-row fallbacks are prohibited for project-owned data. Governed evidence decisions, approvals, referrals, dispositions, dossier generation, and release/export commit their authoritative immutable `AuditEvent` in the same database transaction as the domain change.

## Full-product scope

The atomic replacement includes these end-to-end capability groups:

1. Identity, sessions, invitations, and onboarding.
2. Organizations, memberships, roles, and projects.
3. Script upload, parsing, immutable versions, and scenes.
4. Detection runs and clearance-item projections.
5. Research runs, source snapshots, and evidence claims.
6. Decisions, comments, assignments, referrals, and rewrites.
7. Revision comparison and affected-item rescans.
8. Monitoring schedules, source changes, and notifications.
9. Trust/evaluation views and governed learning candidates.
10. Dossier generation, review, release, export, and audit records.
11. Organization policies, preferences, retention, and privacy settings.

## Verification strategy

Acceptance evidence must exercise reachable behavior.

1. Domain tests verify state transitions, authorization, evidence invariants, and audit requirements.
2. PostgreSQL integration tests verify persistence, tenant isolation, transactions, and rollback.
3. API tests verify authenticated scope, typed errors, contract conformance, and provider failures.
4. Client-generation tests verify every OpenAPI operation produces executable transport code.
5. React tests render components and exercise user interaction and failure states.
6. Playwright tests navigate direct URLs and execute full workflows against the real API and database.
7. Demo tests verify idempotent bootstrap, labeling, and normal API access.
8. Security tests prove cross-organization and cross-project access fails.
9. Visual and accessibility tests cover required widths, themes, keyboard/focus, reduced motion, overflow, and print.

Tests that only assert a symbol exists or wrap a component in `React.createElement` are not acceptance evidence.

## Automated no-legacy gates

CI fails when production code contains:

- a `runtime.js` import or legacy runtime marker;
- hash-based application routing;
- production imports from test fixtures;
- direct `fetch` outside the generated transport;
- local-storage-backed domain data;
- timer-simulated product jobs;
- fixture fallback responses;
- fixed-success product endpoints;
- unscoped project-owned database queries;
- React routes absent from the generated TanStack route tree.

## Atomic cutover gate

The replacement can ship only when:

- every agreed route is reachable through TanStack Router;
- every product surface is operational end to end;
- all browser domain data comes from authoritative APIs;
- the labeled demo project uses normal production paths;
- governed actions and audit events are transactional;
- all required domain, integration, API, frontend, browser, security, and accessibility suites pass;
- a fresh production bundle contains no legacy runtime code or marker;
- deployment smoke tests cover authentication, project access, ingestion, detection, research, decisions, revisions/rescans, monitoring, and report release;
- legacy runtime and dormant scaffold files are deleted;
- inaccurate completion evidence is marked superseded by fresh evidence.

Rollback deploys the previous compatible application image and follows an explicit database compatibility plan. The new application contains no legacy-runtime rollback path.

## Consequences

The replacement takes longer before a product cutover and the implementation branch may remain incomplete for an extended period. In return, the project avoids preserving mock semantics, eliminates dual frontend architectures, and establishes evidence that corresponds to the application users actually run.

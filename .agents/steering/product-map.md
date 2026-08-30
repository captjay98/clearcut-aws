# Product Map

## Current Phase: Pre-implementation

Planning and design are complete. The mock is complete; the production apps, API, packages, infrastructure, and demo directories are planned target deliverables and must not be described as implemented yet.

## Mock UI Prototype

- **Status:** complete — 20 surfaces, 366-check audit, two themes, responsive, accessible.
- **Location:** `misc/clearcut-flow/`.
- **Role:** visual identity and interaction-design source of truth.

## Implementation Plans (planned target)

| Plan | Scope | Status | Priority |
|------|-------|--------|----------|
| 01 — Foundation and contracts | Monorepo, OpenAPI/schemas, generated clients, CI and contributor gates | Next | P0 |
| 02 — Identity and tenancy | Opaque sessions, organizations, invitations, fixed roles and project scope | Planned | P0 |
| 03 — Ingestion and versioning | Safe storage, four import paths, immutable normalized script versions | Planned | P0 |
| 04 — Detection and evaluation | Ten categories, Gemini/ADK runtime, deterministic gates and staged judge | Planned | P0 |
| 05 — Parallel evidence | Mandatory Search, bounded Extract, snapshots, claims, conflicts and traces | Planned | P0 |
| 06 — Design system and shell | Mock-derived primitives, Astro/TanStack shells and UI quality harness | Planned | P0 |
| 07 — Evidence workspace and collaboration | Project/workspace/items, assignments, decisions, comments and notifications events | Planned | P1 |
| 08 — Revisions and selective re-scan | Maker/checker rewrites, immutable v2+, lineage and affected-only research | Planned | P1 |
| 09 — Monitoring and notifications | Scheduled Search/Extract watch, conditional Monitor signals, governed review and inbox | Planned | P1 |
| 10 — Trust and governance | Audit/Records, protected configuration, bounded learning and deletion | Planned | P1 |
| 11 — Report and export | Frozen generation, separate release, deterministic PDF and print UI | Planned | P1 |
| 12 — Infrastructure and submission | GCP, recovery/security proof, original demo, hosted release and Devpost pack | Planned | P0 |

## Planned Deployment Shape

The target has three separately deployable services/images: `clearcut-site` (Astro), `clearcut-web` (TanStack Start), and `clearcut-api` (FastAPI modular monolith + ADK). This is not a three-microservice backend: the API remains one modular monolith with bounded modules.

## Feature Ledger

47 features total — see `feature-ledger.md` for the complete mapping. Categories are protected product vocabulary; source-authority ranking is a separate protected policy applied to `SourceSnapshot`s, not a property inferred from a category.

| Category | Count |
|----------|-------:|
| Script ingestion and structure | 9 |
| Detection categories | 10 |
| Parallel-powered evidence | 9 |
| Workflow product | 10 |
| Non-AI product | 9 |

## Submission

- Deadline: September 9, 2026, 2:00 PM PT.
- Track: Parallel.
- Judging: September 23 – October 7, 2026.
- Deliverables: hosted web URL, public repo + license, three-minute video, Devpost form.

## Next Milestone

Plan 01: scaffold the repository and OpenAPI contracts, then verify generated TypeScript and Python clients agree. Do not claim those runtime directories exist before this milestone is implemented.

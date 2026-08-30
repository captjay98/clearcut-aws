# Tech Stack (Planned Target)

## Current Phase

ClearCut is pre-implementation. The stack below describes the approved target; the listed application/runtime directories are planned until Plans 01–08 land.

## Backend

- **Framework**: FastAPI modular monolith
- **Language**: Python 3.12+
- **ORM/DB**: SQLAlchemy 2.0 + Alembic migrations on Cloud SQL PostgreSQL
- **Auth**: local PostgreSQL authentication by default behind a ClearCut identity adapter; optional Firebase Authentication/Identity Platform; one provider per deployment. Both modes issue opaque revocable application sessions, while PostgreSQL owns organizations, roles, memberships, and permissions.
- **AI/Agent**: Google ADK (`google-adk`) + Gemini (`google-genai`) for detection, search planning, evidence synthesis, rewrite proposals, and judge evaluation
- **Research**: mandatory Parallel Search plus bounded Extract via `parallel-web`; conditional Monitor `event_stream` after a recorded go/no-go. Task, FindAll, Responses/Chat, Interactions, Deep Research, snapshot Monitor, alternate providers, and silent fallbacks are excluded. `docs/PARALLEL_INTEGRATION.md` is authoritative; source provenance is load-bearing.
- **Async jobs**: Cloud Tasks for durable execution + Cloud Scheduler for monitoring cadence
- **Storage**: Cloud Storage for scripts, snapshots, and exports with signed upload/download URLs
- **Secrets**: Secret Manager

## Frontend

- **Marketing service**: Astro, separately deployable as `clearcut-site`
- **Workspace service**: TanStack Start authenticated workspace, separately deployable as `clearcut-web`
- **State**: TanStack Query for server state
- **Styling**: custom design system derived from `misc/clearcut-flow/`; no external visual component library. One approved headless accessibility library may be used only behind ClearCut-owned adapters for complex interaction behavior.
- **Themes**: Script (light, cream tones) and Night shoot (dark, amber accents)

## Mobile Web

Web-only for the hackathon; no native app. Responsive behavior covers 320–1440px. `frontend-engineer` owns implementation. `mobile-engineer` is the responsive parity reviewer who tests and reports issues, then delegates fixes to Frontend.

## Deployment Topology

The target is three separately deployable services and container images:

- `clearcut-site`: Astro marketing service.
- `clearcut-web`: TanStack Start authenticated workspace.
- `clearcut-api`: FastAPI modular monolith + Google ADK runtime.

All three may run on Cloud Run with independent release, rollback, scaling, and service identities. The public workspace/API boundary is same-origin even though `clearcut-web` and `clearcut-api` are separately deployable. The API connects to Cloud SQL PostgreSQL, Cloud Storage, Gemini/ADK, Parallel, Cloud Tasks, Cloud Scheduler, the configured local or Firebase identity adapter, and Secret Manager. Separate service images are deployment boundaries only; the backend remains a modular monolith.

## Key Decisions

- Local PostgreSQL authentication is the default OSS mode; Firebase/Identity Platform is an optional deployment-selected adapter, not the authorization store.
- Browser authentication uses a same-origin, host-only Secure HttpOnly SameSite cookie carrying an opaque revocable server session; state-changing requests also require CSRF-token and Origin validation.
- Modular monolith, not backend microservices, for the hackathon.
- PostgreSQL, not Firestore, for relational evidence/version/audit integrity.
- Fixed roles: Owner, Admin, Editor, Reviewer, Viewer; no custom permission combinations.
- OpenAPI-first contracts; generated TypeScript and Python clients checked for drift.
- Mock is the visual source of truth; production implements its patterns.
- Every provider port returns typed results or typed errors.
- Organization-owned, project-owned, and explicitly global resources use distinct authorization scopes; do not add `project_id` to organization/global queries merely to satisfy a blanket rule.

## Agent Configuration Boundary

Kiro personas intentionally use `tools: ["@builtin"]` and `includeMcpJson: true`. Do not narrow that autonomy. Safety and approval enforcement come from user-level `~/.kiro/settings/permissions.yaml`; project `.kiro/settings/` is optional generated configuration and may be absent.

# ClearCut: Screenplay Pre-Clearance Evidence Workspace

> **Submission status: draft / NO-GO.** This copy must not be published as a completed entry until the external blockers in `manifest.yaml` are closed and the exact submitted revision is verified.

## Inspiration

Independent filmmakers and clearance teams need a reproducible way to identify screenplay risks, gather attributable public-source evidence, preserve uncertainty, and coordinate qualified human review.

## What it does

ClearCut parses screenplays across ten protected categories, maintains source-backed evidence claims, keeps zero-result research unresolved, supports maker-checker collaboration and rewrites, and generates immutable version-bound clearance reports. It supports evidence gathering and workflow coordination; it does not provide legal advice or final legal clearance.

## How we built it

- **Backend:** FastAPI modular monolith, Python 3.12, SQLAlchemy, Alembic, and PostgreSQL-compatible persistence.
- **Frontend:** React, Vite, TanStack Router, Astro, and the shared ClearCut design system.
- **Contracts:** OpenAPI-generated TypeScript and Python clients.
- **AI and retrieval boundaries:** the production profile is designed to require Gemini ADK and Parallel Search/Extract. Live provider traces tied to an exact deployed candidate are not yet available and are not claimed.
- **Governance:** organization/project authorization, human-triggered decisions, immutable audit events, and separate report generation and release.
- **Toolchain:** pnpm, Bun, uv, pytest, Vitest, and Playwright.

## Current proof status

Local API, unit, contract, build, lint, and multi-browser tests have been run during development. Hosted URLs, immutable production image digests, live Gemini/Parallel traces, recovery drills, a public video, Devpost confirmation, and organizer correspondence remain external blockers. Parallel Monitor is not enabled.

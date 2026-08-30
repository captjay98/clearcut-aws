# ClearCut: Autonomous Screenplay Pre-Clearance Workspace

## Inspiration
Independent filmmakers and production legal teams spend weeks manually searching trademark registries, copyright databases, and public records to clear screenplays before shooting starts.

## What it does
ClearCut parses screenplays across 10 protected clearance categories, uses Parallel Search & Extract for verifiable source grounding, orchestrates multi-actor maker-checker Greeking rewrites, and exports version-bound pre-clearance dossiers.

## How we built it
* **Backend**: FastAPI modular monolith with Python 3.12, PostgreSQL (Cloud SQL), SQLAlchemy & Alembic.
* **Frontend**: TanStack Start & Astro workspace with `@clearcut/design-system`.
* **AI & Retrieval**: Google Gemini ADK for structured detection and Parallel Web API for web search & extract.
* **Toolchain**: Bun for JS/TS execution, uv for Python package management.

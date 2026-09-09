# ClearCut

**A screenplay pre-clearance evidence workspace for independent filmmakers, screenwriters, and clearance teams.**

ClearCut reads a screenplay, finds the things that need clearing — brands, trademarks, real people, locations, music, and more across ten protected categories — and gathers cited, source-backed evidence for each one. It coordinates accountable human review, re-evaluates the script as it is revised, and produces immutable, version-bound clearance reports.

Its distinguishing feature: when you upload a revised draft, ClearCut computes exactly what changed and runs a **durable selective rescan** — re-researching only the passages that were modified or added, carrying forward the evidence for everything that stayed the same, and keeping every prior decision as accountable history. You change one scene; you don't re-run the whole script.

> **Current readiness: NO-GO.** No hosted deployment is currently verified. The repository contains a working local implementation and provider-free release controls, but it does not contain the external cloud, paid-provider, recovery, video, or compliance evidence required for a production or contest release. See `docs/submission/manifest.yaml` for the authoritative GO/NO-GO ledger.

ClearCut does not provide legal advice or final legal clearance. It presents sourced findings, uncertainty, and unresolved risk for qualified human review.

---

## Why it matters

Clearance is slow, expensive, and iterative. A script is not written once — it is revised dozens of times, and every revision can introduce or remove a clearance risk. Existing tooling treats each pass as a fresh start. ClearCut treats a screenplay as a versioned artifact with lineage: it knows what a passage was, what it became, and which evidence and human judgment still apply. That is what makes iterative pre-clearance tractable for a small team.

## What ClearCut does

1. **Parses a screenplay** (Fountain/FDX) into structured, addressable passages.
2. **Detects potential issues** across ten protected categories, creating a project-owned clearance item per finding.
3. **Researches each item** with Parallel Search and bounded Extract, recording cited source snapshots — URL, retrieval time, attributable excerpt, publisher authority, and stance.
4. **Coordinates human review** with fixed roles (owner, admin, reviewer, and members), governed decisions, referrals, rewrite review, and an immutable audit trail.
5. **Re-evaluates revisions** through the selective-rescan workflow (below).
6. **Produces immutable, version-bound clearance reports**, generated deterministically and released by an accountable human.

Evidence provenance is mandatory. A detected item may exist with **zero** evidence while research is pending, unavailable, failed, or empty — that state is *unresolved*, never *cleared*. ClearCut never invents fallback evidence.

## Revision and selective rescan

This is the workflow that makes ClearCut worth using across a real production's revision cycle.

- **Immutable versions.** Uploading a revised screenplay commits it as the next version (Version 2, 3, …) with its predecessor and committing actor recorded. Earlier versions are never overwritten, so any report stays reproducible against the exact draft it described.
- **Deterministic diff.** ClearCut computes a passage-level diff classifying every element as *unchanged*, *moved*, *modified*, *added*, or *removed*, using conservative, deterministic matching — no model call, same result every time. Ambiguous matches fail safe to added/removed rather than guessing.
- **Human-triggered rescan.** After reviewing the diff and its impact summary, an authorized reviewer (owner, admin, or reviewer) explicitly starts a selective rescan. Governed, potentially paid work never starts on its own.
- **Only what changed is re-evaluated.** Modified and added passages get fresh detection and research. Unchanged and moved passages carry their items and evidence forward **by reference to the original provenance** — nothing is cloned or fabricated.
- **Decisions stay accountable.** A prior human clearance decision is preserved as history on the earlier version; the carried-forward item is marked *carried forward — confirmation required*. Carried evidence never silently becomes a new clearance.
- **Durable and reload-safe.** The rescan runs as a durable, checkpointed job. Closing the tab or reloading reconstructs live progress from persisted state; retries never duplicate work, items, or provider calls. Typed provider failures surface as visible, unresolved review — never as fake evidence.

The full journey — import v1, attach evidence, revise to v2, diff, confirm, rescan, and reload-safe completion — is proven end to end by a provider-free browser test across Chromium, Firefox, WebKit, and mobile. See `apps/web/tests/e2e/revision-rescan.spec.ts` and the honesty ledger in `apps/web/tests/e2e/TESTING.md`.

## Implemented runtime

- FastAPI modular monolith with organization and project scope enforcement.
- TanStack Start workspace and Astro public site, both compiled into one `clearcut` image.
- FastAPI as the sole public process: Astro routes remain public, `/app/*` serves the workspace, `/api/*` serves the application API, and `/api/internal/*` is protected service delivery.
- PostgreSQL-compatible SQLAlchemy/Alembic persistence and PostgreSQL 17 in local Compose.
- Filesystem, GCS, and S3-compatible object-storage adapters behind typed ports.
- Local dispatch plus authenticated Cloud Tasks delivery and reconciliation.
- Immutable screenplay versions with deterministic lineage, persisted adjacent-version diffs, and durable human-triggered selective rescan.
- Evidence claims bound to cited source snapshots; zero evidence remains unresolved.
- Human-governed decisions, collaboration, referrals, rewrite review, and immutable audit events.
- Deterministic report generation, separate human release, and authorized download.
- OpenAPI generation plus unit, API, contract, and browser coverage.

The root `Dockerfile` builds the portable application package used by every profile. The migration job reuses the exact application image digest and runs Alembic explicitly; application startup never migrates. This source contract is not evidence that a container was built or deployed in a hosted environment.

## Architecture at a glance

ClearCut is a modular monolith with bounded modules — identity, scripts, detection, research, decisions, collaboration, monitoring, evaluation, export, and operations — behind typed application services and events. Modules never read each other's storage; cross-module work flows through typed ports. External systems (Parallel, Gemini/ADK, object storage, Cloud Tasks) sit behind typed provider ports that return typed results or typed errors — never booleans, `None`, or raw dictionaries. The whole product ships as one immutable `clearcut` image that serves the public site, the workspace, and the API from a single process.

## Deployment profiles

| Profile         | Intended use                   | Storage and jobs                                                                                | Current boundary                                                                                  |
| --------------- | ------------------------------ | ----------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Local           | Evaluation and development     | Filesystem storage, local dispatch, Compose PostgreSQL                                          | Implemented; Docker smoke depends on a local Docker engine                                        |
| Portable Server | Existing Linux/container host  | Existing PostgreSQL, filesystem or S3-compatible storage                                        | Application adapters exist; PostgreSQL durable dispatch is not yet wired into runtime composition |
| GCP Starter     | Low-cost hosted starting point | One public Cloud Run service, GCS, Cloud Tasks, Secret Manager, optional acknowledged Cloud SQL | Release contract implemented; infrastructure remains unapplied and hosted proof is absent         |

Built-in opaque server sessions are the default identity mode. Firebase/Identity Platform settings are validated as an optional boundary, but Firebase runtime composition is not yet wired. Do not advertise that adapter as operational.

**Durable jobs and rescan progression.** Detection, research, and selective rescan run as durable jobs. On GCP, Cloud Tasks pulls and executes enqueued child jobs. The local single-container profile has no background queue-draining worker, so a deployed local profile needs such a worker for rescan child jobs to progress on their own; the provider-free browser test drives them through a clearly-labelled, authenticated test-only endpoint. This is an operational dependency, not a correctness gap.

## Provider and cost controls

Gemini and Parallel are disabled by default. Enabling either requires explicit cost acknowledgement and a positive per-provider concurrency limit. Live Gemini and Parallel Search/Extract calls also require authorized credentials and quota. Missing credentials or provider failures create visible unresolved review work; ClearCut does not invent fallback evidence. Parallel Monitor remains disabled without a recorded human GO decision and deployed signed-webhook proof.

Files under `infra/gcp/` and `.github/workflows/` are unapplied deployment controls. They do not prove that cloud resources, hosted URLs, backups, alerts, or image digests exist. Cloud usage can incur charges; no zero-cost guarantee is made.

## Prerequisites

For repository development:

- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- Node.js 20+ with Corepack
- pnpm 9.15.0
- Bun for repository verification scripts

For the local container profile, install Docker Desktop or another Docker Engine with Compose. Provider credentials are optional for local UI/API development and required only for authorized live calls.

## Clean-clone install and verification

```bash
git clone https://github.com/captjay98/clearcut.git
cd clearcut
corepack enable
corepack prepare pnpm@9.15.0 --activate
pnpm install --frozen-lockfile
uv sync --all-packages --dev
pnpm verify
uv run pytest services/api/tests -q
pnpm --filter clearcut-web test
pnpm build
bun scripts/verify-submission.mjs
```

Browser tests additionally require Playwright browsers:

```bash
pnpm exec playwright install
pnpm --filter clearcut-web test:e2e -- --workers=1
```

These commands validate a checkout; they do not establish remote-SHA parity, deployed-image provenance, or live-provider proof.

## Run locally with Docker

```bash
./clearcut start
```

This starts PostgreSQL, runs the explicit one-shot migration service, runs the opt-in seed service (a no-op by default), and starts the combined web/API runtime at `http://localhost:8000`.

To load the clearly synthetic local demo dataset:

```bash
CLEARCUT_SEED_DEMO=true ./clearcut start
```

The demo seed is not provider evidence and must not be presented as a Gemini or Parallel receipt. Stop the environment with `./clearcut stop`.

## Manual development

> After pulling changes that add or change dependencies, reinstall first: `pnpm install --frozen-lockfile`. A stale `node_modules` (for example, missing `tailwindcss`) causes the web build to fail with `Cannot find module 'tailwindcss'`.

Run migrations explicitly before starting the API. Alembic configuration lives in `services/api`, so run it from there (or pass `-c services/api/alembic.ini`):

```bash
# from the repository root
uv run alembic -c services/api/alembic.ini upgrade head
uv run uvicorn clearcut.main:app --app-dir services/api/src --reload --port 8000
```

The API defaults to a local SQLite database at `/tmp/clearcut.db`. Override it with `DATABASE_URL` (for example `DATABASE_URL="sqlite+aiosqlite:////tmp/clearcut-dev.db"`).

In another terminal:

```bash
pnpm --filter clearcut-web dev -- --host 127.0.0.1
```

## Security and provenance boundaries

- Evidence claims require an attributable source snapshot, retrieval time, excerpt, authority classification, stance, research identity, and provenance.
- Governed decisions, selective rescans, and report generation/release require authorized human actions and authoritative audit events.
- Organization records use authenticated organization scope; project records additionally require project scope.
- Provider ports return typed results or typed errors. Failures are visible and never become silent evidence.
- Protected policy, permissions, category, authority, retention, privacy, and legal-boundary rules are human-only.

## Submission evidence

- Truthful readiness ledger: `docs/submission/manifest.yaml`
- Known boundaries: `docs/submission/limitations.md`
- Conditional demo runbook: `demo/runbook.md`
- Draft submission copy: `docs/submission/devpost-copy.md`

## License

Released under the [MIT License](LICENSE).

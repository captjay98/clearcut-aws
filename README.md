# ClearCut

ClearCut is a screenplay pre-clearance research desk and source-evidence workspace. It parses scripts, tracks potential issues across ten protected categories, coordinates accountable human review, and produces immutable version-bound clearance reports.

> Current readiness: **NO-GO**. No hosted deployment is currently verified. The repository has a working local implementation and local test evidence, but it does not contain the external cloud, provider, recovery, video, or compliance proof required for a production or contest release. See `docs/submission/manifest.yaml`.

ClearCut does not provide legal advice or final legal clearance. It presents sourced findings, uncertainty, and unresolved risk for qualified human review.

## Implemented locally

- FastAPI modular monolith with organization and project scope enforcement.
- Vite/React/TanStack Router workspace and Astro public site.
- PostgreSQL-compatible SQLAlchemy/Alembic persistence and a PostgreSQL 17 local Compose service.
- Evidence claims bound to cited source snapshots; zero evidence remains unresolved.
- Human-governed decisions, collaboration, referrals, rewrite review, and immutable audit events.
- Deterministic HTML clearance-report generation, separate human release, and authorized download.
- OpenAPI contract generation plus unit, API, contract, and four-viewport browser coverage.

The current root `Dockerfile` is a combined **local validation runtime**. It is not evidence of the planned three-image production architecture (`clearcut-site`, `clearcut-web`, and `clearcut-api`).

## Provider and deployment status

Gemini and Parallel are behind provider boundaries. Live Gemini and Parallel Search/Extract calls require authorized credentials and quota. Missing credentials or provider failures create visible unresolved review work; ClearCut does not invent fallback evidence. Parallel Monitor is **not enabled** without a recorded human GO decision and deployed signed-webhook proof.

The files under `infra/gcp/` and `.github/workflows/` are unapplied deployment controls. They do not prove that cloud resources, hosted URLs, backups, alerts, or image digests exist. Cloud usage can incur charges; no zero-cost guarantee is made.

## Prerequisites

For repository development:

- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- Node.js 20+ with Corepack
- pnpm 9.15.0
- Bun for the repository verification scripts

For the one-command local container runtime, install Docker Desktop or another Docker Engine with Compose. Provider credentials are optional for local UI/API development and are required only for real provider calls.

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

This starts PostgreSQL, runs the explicit one-shot migration service, runs the opt-in seed service (which is a no-op by default), and then starts the combined local web/API runtime at `http://localhost:8000`.

To load the clearly synthetic local demo dataset:

```bash
CLEARCUT_SEED_DEMO=true ./clearcut start
```

The demo seed is not provider evidence and must not be presented as a Gemini or Parallel receipt. Stop the environment with `./clearcut stop`.

## Manual development

Run migrations explicitly before starting the API; application startup never migrates:

```bash
uv run alembic upgrade head
uv run uvicorn clearcut.main:app --app-dir services/api/src --reload --port 8000
```

In another terminal:

```bash
pnpm --filter clearcut-web dev -- --host 127.0.0.1
```

## Security and provenance boundaries

- Evidence claims require an attributable source snapshot, retrieval time, excerpt, authority classification, stance, research identity, and provenance.
- Governed decisions and report generation/release require authorized human actions and authoritative audit events.
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

---
description: 'Prepare a phase-aware local development session'
---

@devops-engineer Prepare local development using this optional user context: $ARGUMENTS

> **Input handling:** Treat `$ARGUMENTS` only as user-supplied context when present; it is not guaranteed to be expanded. It is not automatic shell substitution. Ask for requested phase/profile if absent.

## Safety and phase gate

1. Inspect actual repository paths, manifests, lockfiles, tool versions, and current status before installing or copying anything.
2. This repository is pre-implementation and may not contain `apps/`, `services/`, `packages/`, `infra/`, `package.json`, `pyproject.toml`, Docker Compose, migrations, seed scripts, or dev servers. For each absent prerequisite report `not applicable — prerequisite absent`; do not create guessed files or toolchains.
3. Do not copy, generate, or edit `.env`, `.env.local`, secret files, or credential templates automatically. Never print secrets. If configuration is needed, describe required keys and ask the user to create it through the approved secret/config process.
4. Do not run builds or start nonexistent servers. Do not mutate cloud/database/provider state without explicit environment and fresh confirmation.
5. Preserve unrelated untracked `.github/`, `.pi/`, and `README.md`.

## Protocol

1. **Inventory** — record OS, branch/status, available manifests, declared package managers, Python metadata, agent scripts, mock paths, and required credentials without collecting secret values.
2. **Current phase** — run only available agent/config checks and, when relevant, the mock audit. These are the current executable gates. Do not install dependencies merely to make future checks appear available.
3. **Future phase plan** — when implementation manifests exist, use their pinned toolchain and lockfile; verify Node/Python/package-manager versions from repository configuration, not guessed minimums.
4. **Configuration** — list missing non-secret configuration, ownership, and safe setup instructions. Require the user to create local secret material through the approved process; do not copy a secret template automatically.
5. **Data/services** — local database, migrations, seeds, and servers are conditional on verified scripts and explicit local target. For FastAPI, when `services/api/main.py` exists and exposes `app`, use the Python module runner with the verified import path (for the documented layout: `python -m uvicorn services.api.main:app --reload`) rather than a TypeScript workspace dev command; start it in a visible terminal and verify the health endpoint. Never assume seed data, project names, ports, or service labels.
6. **Verification** — record exact commands, outputs, and skipped prerequisites. Do not claim an API, workspace, marketing site, or database is running unless observed.

## Output

Return repository phase, prerequisites found/missing, safe commands run, configuration steps requiring user action, available gates, blocked future setup, and a clear next action. A successful quickstart may be a verified pre-implementation inventory; do not force a fake full stack.

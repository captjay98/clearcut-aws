---
description: 'Initialize a session with verified ClearCut context'
---

@fullstack-engineer Prime this session using this optional user context: $ARGUMENTS

> **Input handling:** Treat `$ARGUMENTS` only as user-supplied context when present. It is not guaranteed to be expanded. If absent, prime from repository evidence and state the selected focus.

## Protocol

1. Read canonical `.agents/guide-header.md`, relevant `.agents/steering/`, `.agents/memory/project-memory.md`, and root `AGENTS.md` only if present. Never treat generated `.kiro/` as the source of truth.
2. Inspect actual top-level paths and `git status --short --untracked-files=all`. Preserve unrelated untracked `.github/`, `.pi/`, and `README.md`.
3. Read the feature ledger/product plan/baseline only when present and relevant; report missing artifacts rather than assuming them.
4. Check recent history with `git log --oneline -20` only when a Git history exists.
5. Do not edit agent autonomy or permission policy while priming: preserve `tools: ["@builtin"]` and `includeMcpJson: true` for every Kiro agent, with safety enforced by user-level `~/.kiro/settings/permissions.yaml`.
6. Identify current phase, active work, available executable gates, protected decisions, and blockers. In the current pre-implementation phase, agent/config checks and the mock audit are the only expected executable gates.
7. Do not edit files, install dependencies, call providers, run builds, or regenerate `.kiro/` during priming.

## Output

- **Project** — purpose and users, sourced from available docs.
- **Stack and phase** — actual versus planned technologies.
- **Repository state** — branch/status/history and preserved unrelated work.
- **Invariants** — evidence provenance, human governance, tenant scope, immutability, prompt-injection boundary, job durability, and report reproducibility.
- **Available now** — safe checks and concrete tasks.
- **Blocked/future** — missing artifacts and prerequisites.
- **Ready for** — a concise set of actionable next steps.

Do not report planned infrastructure or absent directories as implemented.

---
description: 'Synchronize documentation with verified repository state'
---

@fullstack-engineer Sync documentation for this optional user context: $ARGUMENTS

> **Input handling:** Treat `$ARGUMENTS` only as user-supplied context when present; it is not guaranteed to be expanded. If no scope is given, audit the repository docs and canonical `.agents/` sources.

## Guardrails

- Read before editing. Do not generate claims from the product plan when implementation is absent.
- Canonical agent sources are `.agents/`; do not edit `.kiro/` directly. Preserve the deliberate Kiro autonomy configuration (`tools: ["@builtin"]` and `includeMcpJson: true`) for every Kiro agent; safety belongs to user-level `~/.kiro/settings/permissions.yaml`. Regeneration is a separate, explicitly requested action.
- Do not create `CHANGELOG.md`, `DEVLOG.md`, API docs, architecture docs, or README sections merely because they are expected. If a file is missing, report it and ask whether to create it with a dated, clearly scoped entry.
- Do not run builds. Do not add tests. Preserve unrelated untracked `.github/`, `.pi/`, and `README.md` unless the user explicitly includes a requested README update.

## Protocol

1. Inventory available docs, code/config paths, feature ledger, steering, memory, and generated-source relationships.
2. Compare setup, architecture, API, security, UI, deployment, and phase claims against actual files. Mark planned/future material clearly.
3. Check `CHANGELOG.md` and `DEVLOG.md` if present. If absent, report `missing — no edit made`; do not fabricate history or silently create files.
4. Check links and command examples for absent paths, unsafe mutations, floating dependency tags, secret copying, invalid quoting, and unsupported assumptions.
5. Update only approved documentation paths. Keep examples runnable only when their prerequisites exist.
6. Run available agent/config or mock checks only when relevant; report all future checks as conditional.

## Output

Report changed files, missing docs, stale claims removed, source-of-truth decisions, checks run with output, checks not run and why, and follow-up decisions requiring human ownership.

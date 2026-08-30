---
description: 'Prepare a conventional commit plan without committing'
---

@fullstack-engineer Prepare a commit plan for this optional user context: $ARGUMENTS

> **Input handling:** Treat `$ARGUMENTS` only as user-supplied context when present. It is not guaranteed to be expanded. If no scope is supplied, use the working tree and staged diff as evidence.

## Guardrails

- This command plans; it never runs `git commit`, push, reset, clean, or other destructive Git operations.
- Inspect `git status --short`, `git diff --cached --stat`, `git diff --stat`, and relevant diffs. Preserve unrelated user work unless the user explicitly includes it.
- Do not stage files, modify files, regenerate `.kiro/`, or create missing artifacts.
- If there are no changes, report that no commit plan can be formed.

## Protocol

1. Establish the requested scope and current phase. Call out pre-implementation paths that are absent rather than assuming future files.
2. Separate staged, tracked-but-unstaged, and untracked changes. Identify generated output and canonical-source relationships.
3. Group only logically independent changes. Do not split a single contract/schema change from its required generated outputs when those outputs exist.
4. Check each group for security, tenant isolation, evidence provenance, transactional audit, and user-facing documentation implications.
5. Propose ordered conventional messages using `type(scope): imperative description`.

## Output

For each proposed commit, provide files, message, rationale, dependencies, verification to run, and any files that must remain out of scope. Include a `requires explicit authorization` note before any future commit action. This command must not claim that a commit was created.

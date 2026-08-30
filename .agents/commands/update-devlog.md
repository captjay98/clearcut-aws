---
description: 'Record verified development activity in DEVLOG.md'
---

@fullstack-engineer Update the development log using this optional user context: $ARGUMENTS

> **Input handling:** Treat `$ARGUMENTS` only as user-supplied context when present; it is not guaranteed to be expanded. If absent, use verified Git history and current changes, not memory or assumptions.

## Guardrails

- Inspect `git status --short --untracked-files=all` and recent history before writing. Preserve unrelated untracked `.github/`, `.pi/`, and `README.md`.
- If `DEVLOG.md` is absent, report `missing — no edit made` and ask for explicit approval before creating it. Never fabricate historical entries or imply work happened because it was planned.
- Do not rewrite old entries unless explicitly requested. Do not edit `.kiro/`, code, tests, or generated artifacts.
- Keep secrets, credentials, personal data, and raw provider responses out of the log.

## Protocol

1. Establish date, scope, author/context, and whether the entry is for current uncommitted work.
2. Read the existing log format and determine its observed ordering before writing. Insert one reverse-chronological entry at the position required by that ordering; do not append by default. Append only when the existing log demonstrates that appending preserves chronology.
3. Record only verified changes, decisions, checks, known limitations, and next steps. Distinguish planned/future work from implemented work.
4. Mention checks by exact command and result; include `not run` reasons rather than invented results.

## Entry format

```markdown
## YYYY-MM-DD

### What changed
- Verified change or explicitly stated current work.

### Decisions made
- Decision and rationale.

### Checks
- `command` — pass/fail/not run (reason)

### Known issues
- Verified limitation or `None recorded`.

### Next steps
- [ ] Explicit follow-up.
```

## Output

Report whether `DEVLOG.md` was updated, the entry date, changed file, insertion position, source evidence, and any missing-file or authorization decision. Do not claim an entry was written if it was not.

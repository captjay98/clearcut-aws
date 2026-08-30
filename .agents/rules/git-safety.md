---
trigger: before_commit
---

# Git Safety

Before any commit, verify that no sensitive data or unrelated work is included. Create a commit only when the user explicitly requests it; otherwise leave the reviewed changes uncommitted.

## Pre-Commit Checklist

1. Run `git status --short` and identify every staged and untracked path.
2. Stage only files within the requested scope; preserve unrelated user work.
3. Review `git diff --cached` and confirm generated files are expected.
4. Check for API keys, passwords, credentials, `.env` values, private keys, access tokens, screenplay text, and private evidence.
5. Do not commit generated `.kiro/` output unless explicitly requested by the repository workflow.

## Build Artifacts to Exclude

- `.env`, `.env.*` with real values
- `*.pem`, `*.key`, `credentials.json`, `serviceAccount.json`
- `node_modules/`, `vendor/`, `.venv/`
- `build/`, `dist/`, `.next/`, `.output/`
- `*.log`

If sensitive data or unrelated work is detected, stop and warn the user. Never bypass hooks with `--no-verify`, amend, force-push, or reset destructive work.

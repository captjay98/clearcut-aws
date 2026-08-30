---
description: 'Execute an approved plan with phase-aware verification'
---

@builder Execute this optional user-approved task: $ARGUMENTS

> **Input handling:** Treat `$ARGUMENTS` only as user-supplied context when present; it is not guaranteed to be expanded. If a plan, scope, or approval is missing, stop and request it. Do not infer approval from a literal or empty argument.

## Guardrails

- Read the plan and actual repository state before editing. Never create guessed files or toolchains for absent future phases.
- Do not edit `.kiro/`; canonical `.agents/` changes are regenerated later. Preserve the deliberate Kiro autonomy configuration (`tools: ["@builtin"]` and `includeMcpJson: true`) for every Kiro agent; safety belongs to user-level `~/.kiro/settings/permissions.yaml`, not command-level reversal.
- Tests for changed behavior are required when an applicable test harness exists. Add focused tests when needed to exercise the changed contract; if no harness or safe test path exists, report `not applicable — prerequisite absent` and the resulting risk rather than silently skipping it.
- Do not call live providers or mutate cloud/database state without explicit, fresh human authorization and a displayed target/environment.
- Consequential ClearCut actions must remain human-governed and transactionally audited. Preserve tenant scope and immutable version bindings.

## Protocol

1. **Preflight** — record phase, branch, status, scope, prerequisites, and absent artifacts. Preserve unrelated untracked `.github/`, `.pi/`, and `README.md`.
2. **Plan check** — identify dependencies, contracts, migrations, rollback, and acceptance criteria before writing.
3. **Implement** — make the smallest coherent change, following existing patterns and typed boundaries.
4. **Review locally** — inspect the diff for secrets, prompt-injection paths, cross-tenant queries, bypassed approvals, and generated-output edits.
5. **Re-evaluate after edits** — inspect the resulting files and phase again. Newly created manifests, applications, test suites, build targets, contracts, or generated-source pairs can make previously absent checks applicable; update the verification set before running it.
6. **Verify by phase and changed behavior**:
   - Run tests for every changed behavior when the corresponding test tooling exists; add a focused regression test when the contract lacks coverage and the test path is safe.
   - Run builds when the edited files and declared project configuration make a build applicable, even if the repository was pre-implementation at preflight. Do not run a build merely because it is customary or when its prerequisites remain absent.
   - Current repository: run available agent/config checks and the mock audit when relevant. Discover exact scripts before running them.
   - Future backend/frontend phases: run documented ruff/pyright/pytest or pnpm checks only after their files/configuration exist.
   - Contract, E2E, deployment, and provider checks are conditional on their prerequisites; report `not applicable`, never fabricate a pass.
7. **Report** — changed files, commands and outputs, acceptance criteria, skipped checks with reasons, and remaining risks.

Never claim completion from intent alone; evidence must come from the actual diff and checks.

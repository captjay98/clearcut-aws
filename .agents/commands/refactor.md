---
description: 'Plan and execute a behavior-preserving refactor'
---

@fullstack-engineer Refactor this optional user-described scope: $ARGUMENTS

> **Input handling:** Treat `$ARGUMENTS` only as user-supplied context when present; if scope or approval is unclear, stop for clarification.

## Guardrails

- Read actual code and neighboring patterns before proposing edits. Do not create absent modules, configs, tests, or toolchains.
- A refactor must preserve observable behavior and must not silently alter evidence, governance, tenant scope, immutable versions, provider contracts, or report reproducibility.
- Do not combine a feature, bug fix, migration, dependency update, or policy change with a refactor. If the requested change alters behavior, stop and re-scope it as a feature or fix rather than completing it as a refactor.
- Establish characterization coverage before changing behaviorally relevant code. Add focused characterization tests when an applicable harness exists; if coverage cannot be added safely, obtain and record an explicit risk decision before mutating the code. Do not treat caller omission of tests as permission to proceed uncovered.
- Do not run builds in the current pre-implementation phase. Do not edit generated `.kiro/`.

## Protocol

1. Define in-scope and out-of-scope behavior, affected files, invariants, rollback, and the explicit behavior-preservation claim.
2. Capture a baseline using only available, prerequisite-backed checks. Current phase: agent/config checks and mock audit when relevant.
3. Establish characterization coverage for each behavior at risk; stop for an explicit risk decision if an applicable test path is absent or cannot be added safely.
4. Identify dependency order and make small coherent edits. Preserve public contracts, stable identifiers, audit semantics, and error behavior.
5. Inspect the diff for accidental scope expansion, secrets, raw provider data, cross-tenant access, and hidden capability bypasses.
6. Verify characterization tests and targeted existing checks, then phase-gated checks when the corresponding app/toolchain exists. Never report absent checks as passed.
7. If behavior changed or the preservation evidence is insufficient, do not complete the work as a refactor; report the required feature/fix re-scope or risk decision.
8. Summarize behavior preserved, changed files, verification output, skipped checks, and remaining risk.

A refactor is complete only when the requested behavior is unchanged and the evidence supports that claim.

---
description: 'Run phase-aware ClearCut release gates'
---

@triager Run release-readiness for this optional user context: $ARGUMENTS

> **Input handling:** Treat `$ARGUMENTS` only as user-supplied context when present; it is not guaranteed to be expanded. If release target, commit, account, or environment is absent, inspect the repository and ask before any deployment-affecting action.

## Gate policy

- Establish the implementation phase and actual prerequisites before running a gate. The repository is currently pre-implementation: only available agent/config checks and the mock audit are expected executable gates. Do not run builds, install dependencies, call live providers, or invent absent paths.
- Every gate is `pass`, `fail`, `not applicable — prerequisite absent`, or `not run — authorization/configuration missing`. Never convert missing implementation into a pass.
- This command is verification only. It never deploys, migrates, releases or generates a report, changes policy, commits, or mutates generated output. Use non-mutating drift checks; if drift is found, report that canonical regeneration is required and stop rather than rebuilding here.

## Blocking gates

A release is blocked by any failure or unresolved `not run` in a gate applicable to the target phase. In addition to tooling checks, require evidence for all of the following:

1. **Legal boundary** — product language presents sourced pre-clearance findings and unresolved risk, never legal conclusions or implied final clearance; specialist referral and human accountability are visible.
2. **Parallel provenance** — every evidence claim has a Parallel source URL, retrieval time, excerpt, authority rank, stance, confidence basis, and provenance/tool receipt. Provider failure never creates invented fallback evidence.
3. **Conflict visibility** — disagreeing, stale, missing, low-authority, or ambiguous sources remain visible with resolution state; no silent synthesis erases conflict.
4. **Tenant isolation** — organization-owned paths scope authenticated `org_id`; project-owned paths scope `org_id` + `project_id` with membership/ownership checks; explicitly global catalogs are allowlisted and contain no tenant content. Role/capability checks are server-side and cross-tenant attempts fail closed.
5. **Human governance** — evidence decisions, rewrites, referrals, dispositions, dossier generation, and report release require the accountable role; gated controls explain restrictions.
6. **Transactional audit** — each consequential decision commits with its authoritative `AuditEvent` in one transaction, including actor, timestamp, effect, evidence/version references, and failure behavior; any Receipt is a redacted projection of that event.
7. **Prompt injection defense** — screenplay/source/model text is untrusted data; it cannot alter agent policy, permissions, tools, protected rules, or approval boundaries; malicious fixtures are covered.
8. **Job durability** — research and monitoring jobs are idempotent, leased/checkpointed, retry with bounded backoff, reconcile safely, and expose permanent failures as review items.
9. **Report reproducibility** — exports bind exact script snapshot, evidence/source retrievals, policy, prompts, rubric/judge versions, decisions, receipts, and generation metadata; repeated generation is explainable.

## Phase-gated technical checks

Run only when the corresponding files/config exist and the user has authorized local verification:

- canonical agent source checks, including `bun .agents/scripts/check-generated.mjs`; do not use a mutating rebuild as a release-readiness check;
- canonical sign-off: `bun .agents/scripts/signoff.mjs` whenever generated output is expected to be current. A missing, failed, or drifted sign-off blocks readiness;
- mock structural audit (`node misc/clearcut-flow/mockup-audit.mjs`, expected 366/366);
- backend ruff/format/pyright/pytest and integration suites;
- frontend pnpm lint/typecheck/test and accessibility/E2E;
- OpenAPI generation plus generated-client drift checks;
- migration dry-run/schema checks;
- dependency supply-chain/security scans;
- deployment smoke and observability checks.

If `check-generated` reports drift, record `regeneration required` and do not invoke `build.mjs` or otherwise mutate `.kiro/`. Do not invoke undeclared package runners; run `pip-audit` only when Python project metadata and the tool are present, and never assume a missing command exists.

## Report

Return phase, target, each gate with evidence/command/output/status, blockers, deferred future gates, drift/regeneration status, sign-off evidence, and release recommendation (`blocked`, `ready for next phase`, or `ready`). A mock audit pass cannot substitute for the blocking ClearCut gates above.

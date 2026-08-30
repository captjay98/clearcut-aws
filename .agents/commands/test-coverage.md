---
description: 'Analyze behavior coverage and prioritize meaningful gaps'
---

@qa-engineer Analyze coverage using this optional user context: $ARGUMENTS

> **Input handling:** Treat `$ARGUMENTS` only as user-supplied context when present; it is not guaranteed to be expanded. If no target exists, inventory the repository and report that coverage is not yet measurable.

## Guardrails

- Discover actual test runners, configs, and source paths before running commands. The repository is currently pre-implementation; do not assume `services/api`, `apps`, `packages`, coverage plugins, or benchmark paths.
- Do not add tests in this command. Do not fabricate coverage percentages or evidence fixtures.
- Do not call live Parallel. Integration evidence must use approved recorded responses with real provenance when that suite exists.
- Current executable gates are agent/config checks and the mock audit, not product coverage commands.

## Protocol

1. Inventory source and test paths, configuration, existing reports, and CI commands.
2. Run only prerequisite-backed coverage commands. If no test project exists, return `not measurable — prerequisite absent`.
3. Evaluate behavior contracts, not implementation lines alone. Prioritize:
   - evidence provenance, authority, stance, confidence, and visible conflicts (90%+ target when implemented);
   - human-governed decisions, receipts, and transactional audit (85%+);
   - paste/Fountain/PDF/FDX parser identity stability (80%+);
   - API contracts (75%+) and UI behavior (60%+);
   - tenant isolation, role boundaries, prompt-injection attempts, provider failures, idempotent jobs, selective re-scan, monitoring deduplication, and report reproducibility.
4. Compare positive, negative, ambiguous, stale, conflicting, low-authority, unsafe-rewrite, narrow-revision, and monitoring no-op cases.
5. Report gaps by risk and recommended behavior test. Do not chase 100% line coverage.

## Output

Return command/output, coverage status by area, missing prerequisites, high-risk uncovered behavior, and an ordered test plan. Distinguish `not run`, `not measurable`, `pass`, and `fail`; never convert unavailable coverage into a pass.

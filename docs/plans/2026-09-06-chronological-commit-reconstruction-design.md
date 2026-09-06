# Chronological Commit Reconstruction Design

**Date:** 2026-09-06
**Branch:** `feat/rebuild-a`
**Base:** `f17765fa61d15eba0e55ad6ba1fc634bad7a768b`

## Goal

Convert the completed uncommitted ClearCut implementation into a dependency-ordered, reviewable Git history that reflects the evidence-backed implementation days from September 1 through September 6, 2026.

## Date policy

Both `GIT_AUTHOR_DATE` and `GIT_COMMITTER_DATE` will use the reconstructed implementation timeline. The calendar dates are grounded in repository plans, review records, file history, and semantic-review timestamps. Exact times are normalized WAT (`+01:00`) ordering values and are not represented as exact implementation-minute evidence.

## Commit sequence

1. `2026-09-01T12:20:00+01:00` — `docs: update rebuild remediation status`
2. `2026-09-02T10:00:00+01:00` — `fix(api): make Alembic the runtime schema authority`
3. `2026-09-02T11:00:00+01:00` — `feat(identity): persist signup and scoped sessions`
4. `2026-09-02T12:00:00+01:00` — `feat(scripts): persist screenplay import and versions`
5. `2026-09-02T14:00:00+01:00` — `feat(ai): persist detection and evaluation provenance`
6. `2026-09-02T16:00:00+01:00` — `feat(research): execute scoped Parallel research jobs`
7. `2026-09-03T10:00:00+01:00` — `feat(operations): add durable jobs and production details`
8. `2026-09-03T14:00:00+01:00` — `feat(contracts): align canonical API and generated clients`
9. `2026-09-03T18:00:00+01:00` — `feat(web): add authenticated import and clearance flow`
10. `2026-09-04T23:25:00+01:00` — `feat(collaboration): add governed schema and command kernel`
11. `2026-09-05T00:15:00+01:00` — `feat(collaboration): persist decisions assignments and dispositions`
12. `2026-09-05T02:00:00+01:00` — `feat(collaboration): add referrals comments mentions and outbox`
13. `2026-09-05T14:00:00+01:00` — `feat(web): connect governed evidence collaboration`
14. `2026-09-05T20:00:00+01:00` — `test(e2e): add deterministic multi-user evidence matrix`
15. `2026-09-06T07:30:00+01:00` — `feat(reports): add immutable report release and download`
16. `2026-09-06T09:00:00+01:00` — `chore(release): add fail-closed submission readiness gates`

## Staging rules

- Stage explicit paths only; never use `git add .` or `git add -A`.
- Never inspect, stage, or commit `.clearcut/` or `services/api/.clearcut/`.
- Pair generated clients with the OpenAPI/generator changes that produced them.
- Split shared files by hunk only when the boundary is unambiguous and the staged diff can be reviewed completely.
- If a hunk cannot be reconstructed safely, move the whole file to the latest dependent commit instead of manufacturing an intermediate state.
- Preserve hooks and create a new commit after any hook failure; do not amend.
- Keep `semantic-review/` quarantined until it is checked locally for secrets and relevance. Include it only as a separate evidence commit if safe and useful.

## Verification strategy

Before every commit:

1. Inspect `git diff --cached --stat` and the complete cached diff.
2. Run `git diff --cached --check`.
3. Run the narrow tests appropriate to the staged domain.
4. Confirm no protected paths or unrelated files are staged.

Run broader checkpoints after the canonical contract, browser evidence matrix, report flow, and release-readiness commits. After the final commit, run root verification, the complete API suite, web units, lint, builds, the four-project Playwright matrix, and final Git status/diff checks.

## Safety and rollback

The working tree remains the source of truth while commits are reconstructed. Staging and committing must not discard unstaged changes. If a split is unsafe, stop and regroup instead of using reset, stash, clean, revert, force push, or history rewriting. No remote push or pull request is part of this operation unless separately requested.

# Active ClearCut Implementation Plans

**Status:** planning only; no plan authorizes implementation by itself.

## Operating rules

1. Start only after explicit owner authorization.
2. Execute in dependency order from `docs/IMPLEMENTATION_PLAN.md`.
3. Treat files in this directory as roadmap summaries. Execute only the granular packets in `docs/plans/implementation/`.
4. Do not claim paths/commands exist before Plan 01 creates and verifies them.
5. Stop at each review checkpoint for evidence-backed sign-off.
6. Archive a plan only after every exit criterion has objective evidence and the owner approves the checkpoint.
7. Evidence packs state exact SHA/tree status and what the evidence does **not** prove.

## Plan index

| Plan | Scope | Depends on |
|---|---|---|
| 01 | repository, toolchains, boundaries, OpenAPI/schemas, generated clients | authorization |
| 02 | sessions, identity adapters, organizations, invitations, membership/RBAC | 01 |
| 03 | object storage, four imports, parsing, immutable versions/elements | 01, 02 |
| 04 | ten-category detection, ADK orchestration, deterministic gates, judge | 01, 03 |
| 05 | mandatory Parallel Search, bounded Extract, source snapshots, claims/conflicts/confidence, traces | 04 |
| 06 | mock-derived design system, Astro/TanStack shells, router/state foundation | 01; contracts from 02–05 as available |
| 07 | project/workspace/items/item, collaboration and governed decisions | 02, 05, 06 |
| 08 | maker/checker rewrite, immutable v2+, diff, affected-only re-scan | 03, 05, 07 |
| 09 | scheduled Search/Extract watch, conditional Monitor signals, governed review, notifications | 07, 08 |
| 10 | Trust, Records, protected configuration, bounded learning, deletion | 04, 05, 07, 09 |
| 11 | report snapshot, release, export/print/reproducibility | 08, 09, 10 |
| 12 | GCP, migrations, operations, demo, hosted proof, submission | all; foundation work may begin after 01 |

## Required plan artifacts

Every plan produces:

- failing-then-passing tests;
- contract/generated-client changes when applicable;
- implementation and migration changes;
- updated operator/developer docs;
- a dated review evidence pack;
- feature-coverage evidence links;
- explicit residual risks and non-claims.

## Executable packets

The implementation packet graph, frozen paths, and task protocol live in `docs/plans/implementation/README.md`. Every feature has one accountable packet in `FEATURE_COVERAGE.md`. If a roadmap summary conflicts with a packet or accepted decision, stop and correct the documentation before implementation.

## Execution choice

When implementation is authorized, use a dedicated worktree and execute one packet at a time with checkpoint review. Use subagent-driven development only if the user explicitly asks for subagents. Do not fan out packets that share contracts/migrations before their accountable packet freezes the seam.

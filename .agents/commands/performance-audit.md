---
description: 'Audit performance using available evidence and phase-appropriate paths'
---

@fullstack-engineer Run a performance audit using this optional user context: $ARGUMENTS

> **Input handling:** Treat `$ARGUMENTS` only as user-supplied context when present; it is not guaranteed to be expanded. If no target, environment, dataset, and acceptance threshold are provided, inventory them before measuring.

## Guardrails

- Discover actual source, benchmark, test, app, and deployment paths first. The repository is pre-implementation; do not assume `services/api/tests/perf`, benchmark scripts, endpoints, `apps/`, or local servers.
- Do not create benchmark files, install tools, run builds, call live Parallel, or mutate production data as part of an audit. Use recorded provider responses and approved synthetic fixtures when those prerequisites exist.
- Current executable gates are agent/config checks and the mock audit; performance measurements are `not applicable` until an implementation and measurement harness exist.
- Never log secrets, screenplay text, source contents, or tenant data. Report p50/p95/p99 with sample size and environment, not unsupported point claims.

## Proposed performance budgets

The following values are restored from the authoritative prior performance plan as **proposed baselines**, not approved release gates. An audit may compare measurements with them, but must label any result provisional until an accountable person approves the budgets. If no approved threshold exists for a workload, stop pass/fail classification and report `threshold approval required` rather than inventing one.

- Project list, flag list, and report: **under 200 ms P95**.
- Evidence detail with sources: **under 500 ms P95**.
- Research-run dispatch: **under 1 s** to queue the job without waiting for completion.
- Workspace initial JavaScript: **under 200 KB gzipped**.
- Static marketing site output: **under 50 KB total**.
- Individual Parallel search: **under 3 s P95**.
- Full ten-flag research run with parallel searches: **under 15 s total**.
- Judge evaluation: **under 5 s**.
- Database queries: **no query over 100 ms without a documented index rationale**.
- Report generation aggregation: **under 500 ms**.
- Core Web Vitals: **LCP under 2.5 s, INP under 200 ms, CLS under 0.1**.

These are measurement targets only; they do not authorize new benchmark paths or executable commands.

## Phase-aware protocol

1. Define workload, tenant/project isolation, dataset size, concurrency, cold/warm state, region, provider mode, and success threshold. Use an approved budget above only as a provisional comparison unless an authoritative approved budget is supplied.
2. Inventory existing measurements and run only configured, prerequisite-backed checks. Use `pnpm exec` or declared tools only when their project manifest/config exists; never invoke an undeclared package runner or guessed benchmark path.
3. For future implementations measure separately:
   - API list/detail/report latency and queue-dispatch latency;
   - frontend route load, bundle sizes, LCP/INP/CLS, and responsive rendering;
   - Parallel research latency, retries, rate limits, tool-call duration, and cost using recorded or approved provider tests;
   - database query plans, tenant-scoped indexes, lock time, and report aggregation;
   - Cloud Run/task queue saturation and error budgets.
4. Check ClearCut-specific risks: no whole-script re-scan when only affected items changed, durable checkpoints, bounded retries, visible failures, and reproducible report generation.
5. For every regression identify evidence, root cause, blast radius, safe optimization, and correctness/security tradeoff. Never optimize away provenance, conflicts, approvals, or tenant filters.

## Report

Return environment/workload, measurements with sample size, target, result, command/output, phase/prerequisite status, bottleneck hypothesis, budget approval status, and prioritized follow-up. Mark unavailable paths `not measured — prerequisite absent` rather than inventing results.

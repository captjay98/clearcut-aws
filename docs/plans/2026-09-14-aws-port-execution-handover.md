# ClearCut AWS Port — Execution Handover

**Written:** 2026-09-14, after Task 0 (baseline stabilization) completed.
**For:** an execution agent picking up the AWS port with no prior session context.
**Canonical plan:** `docs/plans/2026-09-12-aws-port.md` (Tasks 0–16, gates G0–G4). That document defines scope, invariants, and acceptance. This handover adds the live repository state, task-by-task deltas learned during Task 0, and the failure modes already hit. On any conflict: the canonical plan and `.agents/` rules win; re-read the current checkout before editing.

**Working rules that do not change:** follow `AGENTS.md` and `.agents/rules/git-safety.md`. Commit only when the user explicitly authorizes it (as of writing: not yet authorized — Task 0 fixes are uncommitted). Never absorb, stage, or revert unrelated work-in-progress. Never point the test suite at a real database. Paid providers (Bedrock, Parallel) stay fail-closed until the user enables them with cost acknowledgement.

---

## 1. Exact current state

### Candidate and dirty tree

- Branch `main` at `a2dc4e8`. The Task 0 fixes below are **uncommitted working-tree changes** (plus new files). Everything else dirty in `git status` predates this work and is **not yours to touch**: `apps/web/.../workspace.tsx` (modified), `apps/web/src/features/operations/DetectionRecovery.tsx` + `apps/web/tests/unit/detection-recovery.test.tsx` (untracked), demo videos at repo root, `demo-out/`, `scripts/record-demo.mjs`, `.clearcut/`, `.salvage-from-b/`, `.semantic-review/`, `.playwright-mcp/`, `docs/plans/2026-09-09-*`, `docs/reviews/2026-09-12-*`.

### Task 0 fixes sitting uncommitted (all regression-tested)

1. **Invitation acceptance security** (`services/api/src/clearcut/organizations/delivery/http.py`; new `services/api/tests/organizations/test_invitation_http.py`): the accept route now compares the session user's email with the invitation's email (403 on mismatch) and consumes the invitation atomically (guarded `UPDATE ... WHERE status='pending'`, 409 on lost race).
2. **Honest monitoring rechecks** (`services/api/src/clearcut/monitoring/application/run_scheduled_watch.py` rewritten; new `services/api/src/clearcut/monitoring/adapters/unavailable_providers.py`; `monitoring/delivery/http.py` composition; `sql_watch_repository.py` `persist_recheck` now takes `snapshot: SourceSnapshot | None`): rechecks retrieve through the real extract/search ports; provider failure, missing watch target, or a raised error produce a FAILED run with the reason and no snapshot; a query-watch with zero results completes honestly with no snapshot. Production wiring uses fail-closed `Unavailable*Adapter`s; hermetic adapters are test-only seams now.
3. **Local child-job drainer** (`services/api/src/clearcut/main.py`: `_drain_due_local_jobs`, `_local_job_maintenance_loop`, startup drain in `lifespan`; `operations/adapters/sql_job_repository.py`: `dequeue_due_local_jobs`): queued/awaiting-retry child jobs enqueued outside HTTP dispatch now execute in local mode, immediately at startup and on an interval. Selection mirrors `claim()` so nothing double-executes.
4. **Rescan targeting correctness** (`rescan/application/models.py` adds `RevisionPlan.modified_after_element_ids`; `scripts/adapters/sql_revision_plan.py` collects the after-side ids; `main.py` coordinator gains `detect_modified_items` and drops `request_detection`; `rescan/application/run_rescan_job.py` DETECTING stage rewritten): modified passages get ONE scoped detection child (`elementIds`, key `selective_rescan:detect-modified:{version}`) run to completion; research targets the NEW after-version items only; previously-unflagged modified passages are no longer skipped. Test fakes updated to match: `tests/operations/test_selective_rescan_job.py`, `tests/rescan/test_rescan_recovery.py`, `tests/e2e/test_revision_selective_rescan.py` (its `_ChildWorkCoordinator` mirrors production — keep it in sync), new `tests/operations/test_local_queue_drain.py`.

### Verification status

- Full API suite on SQLite: **1171 passed** (`uv run pytest services/api/tests -q`, ~6 min).
- Web unit: **95 passed** (`pnpm --filter clearcut-web test`).
- Rescan e2e (API-level): **11 passed**. Drain tests: **4 passed**.
- **Full API suite on PostgreSQL: NOT green** — 447 passed, 50 failed, 672 errors on a disposable Postgres 17. Single root cause: `asyncpg` "Task got Future attached to a different loop" — the engine is created at import time in `clearcut/database.py`, pytest-asyncio strict mode runs each test in a fresh loop, and asyncpg connections outlive loops. This is a harness problem, not product. Fix direction in §2.
- Web Playwright suites: `monitoring-cadence.spec.ts` verified passing after the monitoring change; the full browser suite has not been re-run since Task 0 landed — run it as part of §2.

### Environment facts

- Docker Desktop was found stopped mid-session and was restarted; the user's stack auto-recovered and must not be disturbed: `clearcut-app` (host port 18080), `clearcut-db` (unpublished), `headroom-default`. Never `docker compose down -v` against it.
- A **disposable** Postgres 17 container `clearcut-aws-port-test-pg` runs on host port 15433 (`clearcut` / `disposable_test`, db `clearcut_test`). It exists only for test runs; remove it (`docker rm -f clearcut-aws-port-test-pg`) when the PG work is done or recreate as needed.
- Toolchain: `uv` for Python, `pnpm` for web, `bun` for `.agents`/contract scripts. Postgres driver is **asyncpg** — PG URLs must be `postgresql+asyncpg://...`.
- Test DB defaults to SQLite (file) via conftest; `DATABASE_URL` switches the engine. The conftest autouse fixture **wipes all runtime tables** — only ever point it at disposable databases.

---

## 2. First work items — close Task 0

1. **Fix the PostgreSQL test harness.** Make the full API suite green on the disposable PG. Likely shape: give PG runs a loop-scoped engine (engine created/disposed per event loop, or a session-scoped loop for DB-bound tests) without changing SQLite behavior. `services/api/tests/conftest.py` is the seam; the canonical plan's Task 1 explicitly anticipates "PostgreSQL-safe cleanup" there. Reproduce with:
   `DATABASE_URL="postgresql+asyncpg://clearcut:disposable_test@localhost:15433/clearcut_test" uv run pytest services/api/tests -q`
2. **Re-run the web browser suite** (`pnpm --filter clearcut-web test:e2e`) — the monitoring and rescan behaviors changed; the specs passed before, verify nothing regressed.
3. **Write `docs/testing/aws-port-baseline.md`**: candidate (commit + uncommitted-file list), exact commands, results (SQLite, PG, web unit, browser), exclusions (no Docker/GCP/provider claims), and the remaining nonblocking backlog (below).
4. **Remove the disposable PG container** (or leave documented if more PG runs are imminent).
5. **Commits:** ask the user. When authorized: one commit per Task 0 fix (invitations / monitoring / drainer / rescan-targeting), tests included, then the baseline doc separately. Do not mix with port work.

**Known nonblocking backlog** (record, don't fix unprompted): parent rescan job reports orchestration success while child research is still queued (children now execute, but parent/child completion semantics are deferred to canonical Tasks 8–10); monitoring cadence persistence (Sep-12 review finding 5, P2); Secret Manager ↔ research credential wiring (finding 6, P2); release automation absent from checkout (finding 7 — canonical Task 12).

---

## 3. Tasks 1–16: order, deltas, done-when

Execute strictly in order; the canonical doc has the file-level detail. Deltas below are what Task 0 taught that the canonical doc doesn't say.

**Task 1 — isolated AWS runtime harness.** Delta: the conftest PG-loop fix (§2.1) IS most of "extend conftest for PostgreSQL-safe cleanup" — land it here if not already. Done-when: `scripts/test_aws_runtime.py` + the runtime Playwright config run the image against real PostgreSQL with typed provider doubles, and a production-profile test provider selector is rejected.

**Task 2 — extract app/worker composition.** Delta: `main.py` has module-level `app = ...` side effects and grows the coordinator classes inline; the e2e file mirrors them. Extract without behavior change; update the e2e mirror in the same change. Done-when: processors compose for web and worker entry points without importing `main.py`, verified by `tests/bootstrap/test_runtime_composition.py`.

**Task 3 — AWS settings/profile.** Delta: model names are environment-driven, not code constants — `docker-compose.yml` defaults detection to `gemini-3.8-flash`, code default is `gemini-3.7-flash`; keep that distinction when adding the `aws` profile and Bedrock model ids. Done-when: `tests/bootstrap/test_aws_profile.py` + profile tests pass; hosted AWS mode rejects SQLite/local dispatch/static keys/emulator endpoints.

**Task 4 — secrets + S3.** Reuse the existing S3 adapter (`scripts/adapters/remote_storage.py`). Done-when: Parallel clients resolve from the injected resolver (no `PARALLEL_API_KEY` read inside runtime factories); missing object/denied/missing-bucket are distinct outcomes.

**Task 5 — cost controls for Strands/Bedrock.** One shared permit pool across sync/async; budgets persisted so restart can't reset them; orchestrator's own model calls counted; no nested-acquire deadlock (release the model permit before tools that call models).

**Task 6 — four Bedrock capability adapters.** Delta: the four capabilities are detection, research planning, **claim synthesis**, and judge (`ai/model_roles.py`; synthesis currently rides the planning role — bind it explicitly). Hermetic doubles exist for all four and are the test seams. `returned_model=None` stays truthful; never copy requested into returned. Done-when: capability tests pass with injected responses including throttle/deny/invalid-JSON/timeout.

**Task 7 — bounded Strands orchestration.** The contest's core criterion: real model/tool decisions, persisted step receipts, server-side scope validation, deterministic completion validator (agent "done" can't skip required search/evaluation or clear unresolved items), no governed-write tools. Done-when: instrumented tests show actual tool selection; prompt-injection attempts fail to widen scope.

**Tasks 8–10 — outbox → SQS → worker.** Delta from Task 0: the local drainer (§1 fix 3) is the local-profile analog; don't regress it while building the SQS path. The acknowledgment matrix in canonical Task 9 is the contract. Done-when: two-publisher races, crash windows, duplicate delivery, lease loss all tested on PostgreSQL.

**Tasks 11–12 — Terraform + release.** Terraform validate/test with mocks only until deployment is authorized; digest-bound releases, worker pause/drain/start/resume sequence, rollback rehearsed.

**Tasks 13–14 — cutover + live verification.** User decisions required (fresh demo data vs migration; account/region/budget). Do not enable paid providers without explicit user cost acknowledgement.

**Task 15 — Agents for Humans.** Deadline 2026-09-14 17:00 PT will have passed; skip unless the user says otherwise and gates close in time. The realistic target is **Build Ship Shape, Oct 23** (canonical Task 16, Alexa+ track).

**Task 16 — Alexa+ extension.** Dedicated follow-up plan required first; reuses Task 7's tools.

---

## 4. Invariants (condensed; canonical §3 + AGENTS.md are authoritative)

Zero evidence = unresolved, never clearance; no fallback evidence. Governed actions stay human-triggered with same-transaction audit. Tenant scope from server composition, never model-selected arguments. No exactly-once claims — idempotent effects, bounded repeats. Paid providers fail-closed. Protected schemas/policies never auto-changed. Old evidence/report bytes and historical Gemini provenance are immutable. Real PostgreSQL for durability acceptance; hermetic tests labeled.

## 5. Full verification gate (run at each task boundary; all must pass)

```bash
uv run pytest services/api/tests -q                                    # SQLite
DATABASE_URL="postgresql+asyncpg://clearcut:disposable_test@localhost:15433/clearcut_test" \
  uv run pytest services/api/tests -q                                  # disposable PG
uv run pytest tests/foundation tests/contracts services/api/tests/architecture -q
uv run ruff check services/api/src services/api/tests
pnpm contract:check
pnpm --filter clearcut-web test
pnpm --filter clearcut-web test:e2e
pnpm build
```

## 6. Traps already hit (don't rediscover these)

- `tuple(await f(x) for x in rows)` compiles into an async generator `tuple()` cannot iterate — use an explicit loop. Hit in `dequeue_due_local_jobs`.
- `EnqueueJob` needs real tenant rows (org/project/actor FKs). Create scope through the app first — copy the `_create_scope` pattern from `tests/operations/test_local_job_lifecycle.py`.
- Long suites die at the 10-minute background-task timeout with buffered output lost — redirect output to a file and chunk, or foreground.
- zsh aborts commands on unmatched globs (`rm -f x*` fails when nothing matches).
- The e2e `_ChildWorkCoordinator`/`_CountingChildWork` mirror production; any coordinator change must update them in the same commit or the e2e fails with attribute errors.
- `monitoring-cadence.spec.ts` passes because of seeded pending-signal data, NOT live rechecks — with fail-closed delivery composition the live recheck produces FAILED runs and zero signals, which is correct.
- The full API suite is ~6 minutes on SQLite; PG is slower — budget test time and don't kill runs early.
- Docker Desktop on this Mac sometimes stops; `open -a Docker` restores the user's auto-starting stack.

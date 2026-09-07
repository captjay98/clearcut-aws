# Revision and Selective Rescan Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver one provider-free-verifiable workflow that commits a complete revised screenplay as the next immutable version, persists deterministic lineage and a diff, carries unaffected evidence by reference, and runs an accountable durable selective rescan for affected material only.

**Architecture:** Extend the existing persistent import transaction to own versions, element lineage, and adjacent diffs. Add typed module-owned ports for item/evidence lineage and coordinate them through the existing operations job kernel; the parent rescan job is the durable status authority. Expose generated OpenAPI clients and a reload-safe Versions UI without changing deployment topology or protected policy/evidence definitions.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy/SQLite/PostgreSQL, Alembic, Pydantic, pytest, OpenAPI 3.1, generated TypeScript/Python clients, React 19, TanStack Router/Query, Vitest, Playwright, pnpm, Bun.

---

## Guardrails

- Work only in `feat/portable-single-service` and preserve a linear history.
- Never inspect or modify `.clearcut/`, `services/api/.clearcut/`, `semantic-review/`, or `.salvage-from-b/`.
- Do not change role/capability definitions, approval policy, categories, authority tiers, evidence schemas, blocking rules, retention/privacy, or legal-boundary language.
- Do not call Gemini, Parallel, cloud APIs, Terraform mutation commands, or paid providers.
- Keep zero evidence unresolved. Never copy a prior clearance decision or present carried evidence as newly verified.
- Write a failing test before each behavior, observe the intended failure, implement minimally, rerun, then commit the exact files.

### Task 1: Deterministic adjacent-version lineage engine

**Files:**
- Modify: `services/api/src/clearcut/scripts/domain/diff.py`
- Modify: `services/api/src/clearcut/scripts/application/materialize_revision.py`
- Modify: `services/api/tests/versions/test_diff_properties.py`
- Modify: `services/api/tests/versions/test_atomic_materialization.py`

**Step 1: Write failing lineage tests**

Add cases that construct separate before/after element IDs and assert all five classifications, exact moved matching, duplicate-context disambiguation, conservative similarity, ambiguous removed+added fallback, deterministic ordering, and derived carry/rescan sets.

```python
diff = compute_script_diff(before, after)
assert diff.algorithm_version == "element-lineage-v1"
assert {row.classification for row in diff.elements} == {
    ChangeClassification.UNCHANGED,
    ChangeClassification.MOVED,
    ChangeClassification.MODIFIED,
    ChangeClassification.ADDED,
    ChangeClassification.REMOVED,
}
assert diff.rescan_element_ids == (modified_after_id, added_after_id)
assert diff.carry_forward_element_ids == (unchanged_after_id, moved_after_id)
```

**Step 2: Run the RED tests**

Run:

```bash
uv run pytest services/api/tests/versions/test_diff_properties.py services/api/tests/versions/test_atomic_materialization.py -q
```

Expected: FAIL because before/after IDs, confidence, moved matching, and deterministic derived sets are absent.

**Step 3: Implement the pure matcher**

Add `LineageConfidence`, separate nullable before/after IDs and ordinals, `MATCHING_ALGORITHM_VERSION`, canonical text normalization, unique exact matching, neighbor-context matching, exact moved matching, mutual unique same-type similarity with a strict threshold/margin, and deterministic output sorting. Similar/ambiguous/added material is affected; only exact/contextual unchanged or moved material is carryable.

**Step 4: Run GREEN tests and lint**

```bash
uv run pytest services/api/tests/versions/test_diff_properties.py services/api/tests/versions/test_atomic_materialization.py -q
uv run ruff check services/api/src/clearcut/scripts/domain/diff.py services/api/src/clearcut/scripts/application/materialize_revision.py services/api/tests/versions
```

Expected: PASS and no lint findings.

**Step 5: Commit**

```bash
git add services/api/src/clearcut/scripts/domain/diff.py services/api/src/clearcut/scripts/application/materialize_revision.py services/api/tests/versions/test_diff_properties.py services/api/tests/versions/test_atomic_materialization.py
git commit -m "feat(scripts): add deterministic revision lineage"
```

### Task 2: Additive revision, carry-forward, and checkpoint schema

**Files:**
- Create: `services/api/alembic/versions/0035_revision_selective_rescan.py`
- Modify: `services/api/tests/architecture/test_migrated_runtime_schema.py`
- Modify: `services/api/tests/architecture/test_governed_collaboration_schema.py`

**Step 1: Write failing schema tests**

Assert migration head includes:

- `script_versions.predecessor_version_id` and committing actor.
- One scoped adjacent `script_diffs` row and normalized `script_element_lineage` rows.
- `clearance_items.predecessor_item_id`, lineage kind, and confirmation-required carry status.
- `evidence_carry_forwards` referencing original claim/snapshot/run/query/provider provenance.
- `selective_rescan_checkpoints` keyed by scoped job/stage/item.
- Cross-project predecessors, endpoints, items, and evidence references fail closed.

**Step 2: Run RED schema tests**

```bash
uv run pytest services/api/tests/architecture/test_migrated_runtime_schema.py services/api/tests/architecture/test_governed_collaboration_schema.py -q
```

Expected: FAIL because migration `0035_revision_selective_rescan` and its columns/tables do not exist.

**Step 3: Implement migration 0035**

Use `down_revision = "0034_report_artifacts"`. Strengthen the existing `script_diffs` table additively; leave legacy `rescan_jobs` unused. Add tenant/project/script-scoped foreign keys and uniqueness for ordinals, adjacent diffs, lineage endpoints, item predecessor mappings, evidence carry references, and checkpoint replay identity. Preserve all existing evidence provenance constraints.

**Step 4: Run migration tests and Terraform-independent schema validation**

```bash
uv run pytest services/api/tests/architecture/test_migrated_runtime_schema.py services/api/tests/architecture/test_governed_collaboration_schema.py -q
uv run ruff check services/api/alembic/versions/0035_revision_selective_rescan.py services/api/tests/architecture
```

Expected: PASS.

**Step 5: Commit**

```bash
git add services/api/alembic/versions/0035_revision_selective_rescan.py services/api/tests/architecture/test_migrated_runtime_schema.py services/api/tests/architecture/test_governed_collaboration_schema.py
git commit -m "feat(database): persist revision and rescan lineage"
```

### Task 3: Commit complete uploads as immutable next versions

**Files:**
- Modify: `services/api/src/clearcut/scripts/adapters/sql_import_repository.py`
- Modify: `services/api/src/clearcut/scripts/application/import_script.py`
- Modify: `services/api/src/clearcut/scripts/delivery/http.py`
- Modify: `services/api/tests/scripts/test_import_pipeline_http.py`
- Create: `services/api/tests/scripts/test_revision_persistence.py`

**Step 1: Write failing persistent revision tests**

Through public upload/paste, parse, warning acceptance, and commit endpoints, prove:

```python
assert version_one.ordinal == 1
assert version_two.ordinal == 2
assert version_two.predecessor_version_id == version_one.id
assert reloaded_version_one.source_sha256 == original_digest
assert persisted_diff.after_version_id == version_two.id
```

Also assert same-parse-run replay returns the same v2, concurrent stale revision commits return one typed conflict, injected diff failure rolls back v2 and elements, and foreign scope returns neutral 404.

**Step 2: Run RED persistence tests**

```bash
uv run pytest services/api/tests/scripts/test_revision_persistence.py services/api/tests/scripts/test_import_pipeline_http.py -q
```

Expected: FAIL because the repository rejects every second version and no persisted diff API exists.

**Step 3: Generalize the scripts transaction**

Replace the v1-only implementation with `commit_version(...)` while retaining a compatibility wrapper if required. Pass `scope.user_id`. Within one `session_scope`: replay by parse run, lock/CAS project version sequence, load predecessor elements, allocate the next ordinal, preallocate new element IDs, compute lineage, and insert version/elements/diff/lineage atomically. On an integrity race reload only the same parse-run winner; otherwise return typed conflict.

Add scoped typed `get_adjacent_diff(org_id, project_id, after_version_id)` and immutable views. Every query includes authenticated org/project scope.

**Step 4: Run GREEN persistence tests, Ruff, and scoped Pyright**

```bash
uv run pytest services/api/tests/scripts/test_revision_persistence.py services/api/tests/scripts/test_import_pipeline_http.py services/api/tests/versions -q
uv run ruff check services/api/src/clearcut/scripts services/api/tests/scripts services/api/tests/versions
uv run pyright services/api/src/clearcut/scripts
```

Expected: PASS; scoped type check has zero errors.

**Step 5: Commit**

```bash
git add services/api/src/clearcut/scripts services/api/tests/scripts services/api/tests/versions
git commit -m "feat(scripts): persist immutable screenplay revisions"
```

### Task 4: Complete OpenAPI revision and rescan contracts

**Files:**
- Modify: `packages/contracts/openapi.yaml`
- Modify: `scripts/generate-clients.mjs`
- Regenerate: `packages/contracts/generated/typescript/index.ts`
- Regenerate: `packages/contracts/generated/python/__init__.py`
- Modify: `tests/contracts/test_operation_inventory.py`
- Modify: `tests/contracts/test_mounted_operation_ids.py`
- Modify: `tests/contracts/fixtures/generated-client-usage.ts`

**Step 1: Write failing contract assertions**

Require `getScriptVersionDiff`, mounted `startSelectiveRescan`, required idempotency header, server-derived affected scope with no `itemIds`, five change kinds, confidence, impact summary, and generated client methods.

**Step 2: Run RED contract tests**

```bash
uv run pytest tests/contracts/test_operation_inventory.py tests/contracts/test_mounted_operation_ids.py -q
```

Expected: FAIL for the missing diff operation and stale rescan request shape.

**Step 3: Update OpenAPI and generator**

Add `GET .../script-versions/{versionId}/diff`; retain `POST .../{versionId}:startSelectiveRescan`; return the existing durable `Job`; add typed diff/summary/element schemas; remove client-selected item scope; require `Idempotency-Key`. Implement the FastAPI diff read and reserve rescan operation ID for the mounted rescan router.

Regenerate only through:

```bash
bun scripts/generate-clients.mjs
```

**Step 4: Run contract drift and usage checks**

```bash
bun scripts/check-contract-drift.mjs
```

Expected: valid OpenAPI, mounted parity, generated usage compilation, and zero drift.

**Step 5: Commit**

```bash
git add packages/contracts/openapi.yaml scripts/generate-clients.mjs packages/contracts/generated tests/contracts services/api/src/clearcut/scripts/delivery/http.py
git commit -m "feat(contracts): expose revision diff and selective rescan"
```

### Task 5: Persist safe item and evidence carry-forward

**Files:**
- Create: `services/api/src/clearcut/rescan/ports/revision_plan.py`
- Create: `services/api/src/clearcut/rescan/ports/item_lineage.py`
- Create: `services/api/src/clearcut/rescan/ports/evidence_lineage.py`
- Create: `services/api/src/clearcut/scripts/adapters/sql_revision_plan.py`
- Create: `services/api/src/clearcut/detection/application/materialize_item_lineage.py`
- Create: `services/api/src/clearcut/detection/adapters/sql_rescan_lineage.py`
- Create: `services/api/src/clearcut/research/application/carry_forward_evidence.py`
- Create: `services/api/src/clearcut/research/adapters/sql_evidence_lineage.py`
- Modify: `services/api/tests/rescan/test_selective_calls.py`
- Modify: `services/api/tests/research/test_snapshot_provenance.py`
- Modify: `services/api/tests/decisions/test_governed_evidence_decision.py`
- Modify: `services/api/tests/architecture/test_boundaries.py`

**Step 1: Write RED port and provenance tests**

Use frozen typed DTOs. Assert unchanged/moved exact/contextual items receive new unresolved successor items and carry associations; modified/added receive no carry; removed remain historical; original evidence provenance is unchanged; prior decisions are not copied; direct new-item claim count remains zero; retries return the same item/carry IDs.

**Step 2: Observe failures**

```bash
uv run pytest services/api/tests/rescan/test_selective_calls.py services/api/tests/research/test_snapshot_provenance.py services/api/tests/decisions/test_governed_evidence_decision.py services/api/tests/architecture/test_boundaries.py -q
```

Expected: FAIL because typed ports/adapters and carry tables are unused.

**Step 3: Implement owning-module adapters**

Scripts returns a scoped immutable revision plan. Detection creates successor item projections with predecessor ID, confirmation-required status, null new candidate provenance, no copied assignment/disposition/decision, and `ON CONFLICT` replay. Research stores references to original claim/snapshot/run/query/attempt provenance and exposes them separately from direct claims. The coordinator imports ports only, never SQL adapters.

**Step 4: Run GREEN tests and boundaries**

```bash
uv run pytest services/api/tests/rescan/test_selective_calls.py services/api/tests/research/test_snapshot_provenance.py services/api/tests/decisions/test_governed_evidence_decision.py services/api/tests/architecture/test_boundaries.py -q
uv run ruff check services/api/src/clearcut/rescan services/api/src/clearcut/detection services/api/src/clearcut/research
uv run pyright services/api/src/clearcut/rescan services/api/src/clearcut/detection/application/materialize_item_lineage.py services/api/src/clearcut/research/application/carry_forward_evidence.py
```

Expected: PASS and no cross-module adapter imports.

**Step 5: Commit**

```bash
git add services/api/src/clearcut/rescan services/api/src/clearcut/scripts/adapters/sql_revision_plan.py services/api/src/clearcut/detection services/api/src/clearcut/research services/api/tests/rescan services/api/tests/research services/api/tests/decisions services/api/tests/architecture/test_boundaries.py
git commit -m "feat(rescan): preserve item and evidence lineage"
```

### Task 6: Add accountable durable selective-rescan execution

**Files:**
- Create: `services/api/src/clearcut/rescan/application/start_rescan.py`
- Create: `services/api/src/clearcut/rescan/application/run_rescan_job.py`
- Create: `services/api/src/clearcut/rescan/ports/repository.py`
- Create: `services/api/src/clearcut/rescan/adapters/sql_repository.py`
- Create: `services/api/src/clearcut/rescan/delivery/http.py`
- Modify: `services/api/src/clearcut/operations/ports/job_repository.py`
- Modify: `services/api/src/clearcut/operations/application/run_job.py`
- Modify: `services/api/src/clearcut/main.py`
- Create: `services/api/tests/operations/test_selective_rescan_job.py`
- Create: `services/api/tests/rescan/test_selective_rescan_http.py`
- Modify: `services/api/tests/operations/test_local_job_lifecycle.py`
- Modify: `services/api/tests/operations/test_cloud_task_delivery.py`
- Modify: `services/api/tests/operations/test_reconciliation.py`

**Step 1: Write RED job/start tests**

Assert strict target projection, CSRF/auth/scope validation before repository access, required idempotency, one atomic start audit/job, dispatch only when created, persisted stages, stable checkpoint keys across retries, affected-only detection/research calls, typed failure persistence, no later stage after failure, reload recovery, and no duplicate provider fake calls.

**Step 2: Observe failures**

```bash
uv run pytest services/api/tests/operations/test_selective_rescan_job.py services/api/tests/rescan/test_selective_rescan_http.py -q
```

Expected: FAIL because the job kind, processor, checkpoint repository, and mounted route do not exist.

**Step 3: Implement start and processor**

Map `selective_rescan -> script_version` in the strict job target contract. Start through `SqlJobRepository.enqueue()` with actor, scoped target, `selective_rescan.started` audit, and stable diff-based idempotency. Dispatch after commit only.

Process persisted stages: materialize lineage, carry evidence, detect changed/added elements, research resulting affected items, and await confirmation. Persist a checkpoint before advancing. Reuse existing typed provider gates/results; no fallback evidence. Use generic local/Cloud Tasks execution and reconciliation without job-kind branching.

If child jobs are used, never block the single local worker: defer the parent through a typed retry-wait transition and resume after child terminal state. Parent/child idempotency keys must be stable across human retries.

**Step 4: Run GREEN operation suites**

```bash
uv run pytest services/api/tests/operations/test_selective_rescan_job.py services/api/tests/rescan/test_selective_rescan_http.py services/api/tests/operations/test_local_job_lifecycle.py services/api/tests/operations/test_cloud_tasks_dispatch.py services/api/tests/operations/test_cloud_task_delivery.py services/api/tests/operations/test_reconciliation.py -q
uv run ruff check services/api/src/clearcut/rescan services/api/src/clearcut/operations services/api/src/clearcut/main.py
uv run pyright services/api/src/clearcut/rescan services/api/src/clearcut/operations/application/run_job.py
```

Expected: PASS without network or credentials.

**Step 5: Commit**

```bash
git add services/api/src/clearcut/rescan services/api/src/clearcut/operations services/api/src/clearcut/main.py services/api/tests/operations services/api/tests/rescan
git commit -m "feat(rescan): run durable selective rescans"
```

### Task 7: Wire the reload-safe Versions UI

**Files:**
- Create: `apps/web/src/queries/scriptVersions.ts`
- Create: `apps/web/src/mutations/scriptVersionCommands.ts`
- Modify: `apps/web/src/features/scripts/ScriptUploadModal.tsx`
- Modify: `apps/web/src/features/versions/VersionDiffViewer.tsx`
- Modify: `apps/web/src/features/versions/RescanProgress.tsx`
- Create: `apps/web/src/features/versions/SelectiveRescanDialog.tsx`
- Modify: `apps/web/src/routes/o/$orgSlug/projects/$projectId/versions.tsx`
- Create: `apps/web/src/features/versions/__tests__/revisionRescan.test.tsx`

**Step 1: Write RED component/query tests**

Assert tenant-scoped query keys, revision-purpose upload copy, all five diff kinds, explicit confirmation before mutation, required idempotency key, nonterminal-only polling, persisted job error/progress rendering, and URL search restoration for `versionId`/`rescanJobId`.

**Step 2: Observe failures**

```bash
pnpm --filter clearcut-web test -- --run apps/web/src/features/versions/__tests__/revisionRescan.test.tsx
```

Expected: FAIL because query/mutation modules and integrated controls are absent.

**Step 3: Implement generated-client state and UI**

Use TanStack Query and generated methods only. Add `purpose="revision"` to the existing import modal. Remove fake default rows and timers. Render persisted timeline, diff, impact, explicit rescan confirmation, durable job stages, carried-confirmation state, newly researched items, removed history, and typed failures. Put selected version/job IDs in route search so reload calls `getJob` rather than restarting work.

**Step 4: Run GREEN web tests and type/build checks**

```bash
pnpm --filter clearcut-web test -- --run
pnpm --filter clearcut-web exec tsc --noEmit
pnpm --filter clearcut-web build
```

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/web/src/queries/scriptVersions.ts apps/web/src/mutations/scriptVersionCommands.ts apps/web/src/features/scripts/ScriptUploadModal.tsx apps/web/src/features/versions apps/web/src/routes/o/\$orgSlug/projects/\$projectId/versions.tsx
git commit -m "feat(web): connect revision and rescan workflow"
```

### Task 8: Add one honest provider-free end-to-end proof

**Files:**
- Create: `apps/web/tests/fixtures/revision-v1.fountain`
- Create: `apps/web/tests/fixtures/revision-v2.fountain`
- Modify: `apps/web/tests/support/e2e_api.py`
- Create: `apps/web/tests/e2e/revision-rescan.spec.ts`
- Modify: `apps/web/tests/e2e/version-diff-lineage.spec.ts`
- Modify: `apps/web/tests/e2e/TESTING.md`
- Create: `services/api/tests/e2e/test_revision_selective_rescan.py`

**Step 1: Write the RED provider-free acceptance tests**

The API acceptance test and Chromium E2E must create/import v1, attach complete synthetic E2E provenance, upload full-file v2 containing all five change kinds, start rescan explicitly, reload, and assert only changed/added passages and resulting items reached recording fake providers. Assert carry references preserve source data, prior decisions are historical, removed work is inactive, retries do not duplicate work, and zero/failure paths remain unresolved.

**Step 2: Observe failures**

```bash
uv run pytest services/api/tests/e2e/test_revision_selective_rescan.py -q
pnpm --filter clearcut-web exec playwright test tests/e2e/revision-rescan.spec.ts --project=chromium-desktop-1440
```

Expected: FAIL until the complete API and browser flow is connected.

**Step 3: Implement hermetic E2E composition**

Inject typed planner/Search/Extract/detection/judge fakes only in `apps/web/tests/support/e2e_api.py`. Add a schema-hidden authenticated fixture helper for cited predecessor evidence with explicit E2E identities. Production composition remains configured providers and never falls back to hermetic adapters.

Replace the prior negative lineage expectation with the positive persisted workflow. Update the honesty ledger to state that this proves local provider-free behavior, not hosted durability, live Parallel quality, legal clearance, or paid-provider reliability.

**Step 4: Run GREEN E2E matrix**

```bash
uv run pytest services/api/tests/e2e/test_revision_selective_rescan.py -q
pnpm --filter clearcut-web exec playwright test tests/e2e/revision-rescan.spec.ts --project=chromium-desktop-1440
pnpm --filter clearcut-web exec playwright test tests/e2e/revision-rescan.spec.ts
```

Expected: PASS across configured Chromium, Firefox, WebKit, tablet, and mobile projects.

**Step 5: Commit**

```bash
git add apps/web/tests/fixtures apps/web/tests/support/e2e_api.py apps/web/tests/e2e services/api/tests/e2e/test_revision_selective_rescan.py
git commit -m "test(e2e): prove durable revision selective rescan"
```

### Task 9: Complete provider-free verification and review

**Files:**
- Modify only if a confirmed P0/P1 requires a TDD fix.

**Step 1: Run focused gates**

```bash
bun scripts/check-contract-drift.mjs
uv run pytest services/api/tests/scripts services/api/tests/versions services/api/tests/rescan services/api/tests/operations services/api/tests/research services/api/tests/decisions services/api/tests/e2e/test_revision_selective_rescan.py tests/contracts -q
pnpm --filter clearcut-web test -- --run
pnpm --filter clearcut-web exec tsc --noEmit
pnpm --filter clearcut-web build
pnpm --filter clearcut-web exec playwright test tests/e2e/revision-rescan.spec.ts
```

Expected: all pass without provider/network/cloud access.

**Step 2: Run repository gates**

```bash
pnpm verify
uv run ruff check services/api/src services/api/tests
uv run pyright services/api/src/clearcut/scripts services/api/src/clearcut/rescan services/api/src/clearcut/operations services/api/src/clearcut/detection services/api/src/clearcut/research
pnpm build
git diff --check -- . ':(exclude).clearcut/**' ':(exclude)services/api/.clearcut/**' ':(exclude)semantic-review/**' ':(exclude).salvage-from-b/**'
```

Record any pre-existing broad debt separately; changed-source checks must be clean.

**Step 3: Request independent exact-range review**

Review the exact implementation range from `b03ed43` to final SHA. Require severity-ranked findings and explicit confirmation of tenant scoping, evidence provenance, no copied decisions, idempotency, affected-only provider calls, generated-client parity, and reload-safe UI. Fix confirmed P0/P1 with RED/GREEN tests.

**Step 4: Final status**

Verify unprotected tracked/untracked status is clean and report exact commits, passing counts, unavailable tools, and the unchanged hosted/provider NO-GO boundary. Do not merge, push, deploy, or delete worktrees without explicit authorization.

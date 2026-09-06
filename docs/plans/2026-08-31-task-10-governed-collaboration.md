# Task 10 Governed Collaboration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the complete authoritative Task 10 evidence-workspace collaboration path: governed evidence decisions and dispositions, operational assignments, referrals and acknowledgements, persisted comments/replies/revisions/mentions, transactional audit/outbox records, generated-client UI integration, and multi-user browser proof.

**Architecture:** A shared typed command kernel validates scope, capability, expected version, intent, and idempotency while bounded decisions, items, and collaboration modules own their application services and storage. Each accepted command writes domain state, command identity, and `authoritative_audit_events` in one transaction; collaboration notifications also write the outbox in that transaction. The browser uses canonical generated operations, TanStack Query, no optimistic governed state, and authoritative refetch after success.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, SQLAlchemy async, Alembic, PostgreSQL/SQLite test dialects, React 19, TanStack Router/Query, TypeScript, generated OpenAPI clients, pytest, Ruff, Pyright, Playwright.

**Constraints:** Do not commit. Do not call paid providers. Do not inspect or modify either `.clearcut` directory. Do not fabricate evidence, comments, referrals, audit receipts, or successful state. Do not make legal conclusions. Every production behavior requires a witnessed failing test first.

**Design:** `docs/plans/2026-08-31-task-10-governed-collaboration-design.md`

---

## Execution rules

For every task below:

1. Add only the named failing test or contract assertion.
2. Run the narrow command and confirm it fails for the expected missing behavior.
3. Add the minimum production change.
4. Run the narrow command and confirm it passes.
5. Run the listed neighboring regression suite.
6. Record RED and GREEN output in the session evidence; do not commit.

Do not combine independent RED cases into one production edit. If a test passes before production changes, strengthen it until it proves the missing behavior.

### Task 1: Normalize the canonical Task 10 contract

**Files:**
- Modify: `packages/contracts/openapi.yaml`
- Modify through generation: `packages/contracts/generated/typescript/index.ts`
- Modify through generation: `packages/contracts/generated/python/__init__.py`
- Modify if generation requires it: `scripts/generate-clients.mjs`
- Test: `tests/contracts/test_generated_clients.py`
- Test: `tests/contracts/test_mounted_operation_ids.py`
- Create fixture if needed: `tests/contracts/fixtures/task-10-generated-client-usage.ts`

**Step 1: Add failing contract assertions for canonical command inputs**

Assert that `recordEvidenceDecision`, `setDisposition`, `referClearanceItem`, `acknowledgeReferral`, `assignClearanceItem`, `addComment`, `replyToComment`, and `reviseComment` use canonical `/clearance-items/...` paths. Assert required `Idempotency-Key`, `expectedVersion`, and `intentHash` for versioned/idempotent commands and required rationale for governed commands.

```python
def test_task_10_commands_require_version_intent_and_idempotency(openapi_document):
    operation = openapi_document["paths"][DECISION_PATH]["post"]
    assert any(parameter["$ref"].endswith("IdempotencyKey") for parameter in operation["parameters"])
    schema = resolve_request_schema(openapi_document, operation)
    assert {"decision", "rationale", "expectedVersion", "intentHash"} <= set(schema["required"])
```

**Step 2: Run the RED contract test**

Run:

```bash
uv run pytest tests/contracts/test_generated_clients.py -k 'task_10 or governed or decision' -q
```

Expected: FAIL because required headers/fields or canonical schemas are absent/inconsistent.

**Step 3: Normalize contract schemas**

Use one decision vocabulary across OpenAPI and the domain. Define request schemas with strict required fields and response schemas that include current/resulting item version. Add typed shared 403, safe 404, stale/idempotency 409, and 422 responses.

Attach `Idempotency-Key` to all approved versioned commands. Keep assignment operational but still versioned and idempotent. Do not add legal-clearance language.

**Step 4: Add failing generated-client usage assertions**

Compile representative calls that must include header and body fields and consume typed result/error values.

```typescript
await api.recordEvidenceDecision({
  params: { orgId, projectId, itemId },
  headers: { "Idempotency-Key": key },
  body: { decision, rationale, expectedVersion, intentHash },
});
```

Run:

```bash
pnpm contract:generate
uv run pytest tests/contracts/test_generated_clients.py -q
```

Expected before the contract/generator is complete: FAIL from missing generated fields or drift.

**Step 5: Regenerate clients and reach GREEN**

Run:

```bash
pnpm contract:generate
pnpm contract:check
```

Expected: valid OpenAPI 3.1, generated headers verified, zero drift, contract tests pass.

**Step 6: Run mounted-operation regression tests**

```bash
uv run pytest tests/contracts/test_mounted_operation_ids.py tests/contracts/test_generated_clients.py -q
```

Expected: PASS.

### Task 2: Add governed collaboration persistence and migration invariants

**Files:**
- Create: `services/api/alembic/versions/0030_governed_collaboration.py`
- Modify: `services/api/src/clearcut/init_db.py` only if runtime schema declarations require alignment
- Test: `services/api/tests/architecture/test_migrated_runtime_schema.py`
- Create: `services/api/tests/architecture/test_governed_collaboration_schema.py`

**Step 1: Add a failing migration-head and schema test**

Assert:

- Alembic head is `0030_governed_collaboration`;
- `clearance_items.version` is non-null with a safe existing-row default;
- command identity is unique by `(org_id, project_id, actor_id, operation, idempotency_key)`;
- referrals/comments/revisions/mentions/outbox rows carry organization/project ownership;
- comments preserve parent identity and revisions are append-only rows;
- scoped indexes support item history and outbox delivery.

Run:

```bash
uv run pytest services/api/tests/architecture/test_governed_collaboration_schema.py -q
```

Expected: FAIL because revision `0030` and required columns/tables/constraints do not exist.

**Step 2: Implement the additive upgrade**

Create `0030_governed_collaboration.py` revising `0029_job_list_pagination`. Use batch alterations where SQLite requires them. Prefer new canonical tables over mutating legacy tables when legacy ownership cannot be made safe without ambiguity.

Required persistence includes:

- item version;
- scoped command receipts/identity;
- versioned decision/disposition records;
- scoped referral lifecycle;
- scoped comments;
- immutable comment revisions;
- mention recipients;
- versioned/deduplicated outbox events.

Use composite ownership constraints where supported by the current schema. Do not create another audit table.

**Step 3: Implement a dependency-safe downgrade**

Drop indexes, foreign keys, child tables, command tables, and item version changes in reverse dependency order.

**Step 4: Run focused GREEN migration tests**

```bash
uv run pytest services/api/tests/architecture/test_governed_collaboration_schema.py services/api/tests/architecture/test_migrated_runtime_schema.py -q
```

Expected: PASS on fresh upgrade.

**Step 5: Prove downgrade and re-upgrade**

Add a test that upgrades to head, downgrades to `0029_job_list_pagination`, and upgrades to head again.

Run:

```bash
uv run pytest services/api/tests/architecture/test_governed_collaboration_schema.py -k 'downgrade or round_trip' -q
```

Expected: PASS without data fabrication or migration errors.

### Task 3: Build the shared typed command kernel

**Files:**
- Create: `services/api/src/clearcut/commanding/__init__.py`
- Create: `services/api/src/clearcut/commanding/domain.py`
- Create: `services/api/src/clearcut/commanding/errors.py`
- Create: `services/api/src/clearcut/commanding/sql.py`
- Create: `services/api/tests/commanding/test_governed_command_kernel.py`

**Step 1: Write failing domain tests**

Define wished-for typed APIs:

```python
envelope = CommandEnvelope(
    org_id=org_id,
    project_id=project_id,
    actor_id=actor_id,
    operation="record_evidence_decision",
    idempotency_key=key,
    intent_hash=intent_hash,
    expected_version=3,
)
```

Test:

- blank/malformed key or intent rejection;
- immutable dataclass behavior;
- same-key/same-intent replay classification;
- same-key/different-intent conflict;
- stale expected version conflict;
- safe typed forbidden/not-found/conflict errors.

Run:

```bash
uv run pytest services/api/tests/commanding/test_governed_command_kernel.py -q
```

Expected: FAIL because the commanding package does not exist.

**Step 2: Implement minimal immutable types and errors**

Use frozen dataclasses or strict Pydantic models. Errors carry safe machine codes and messages but no foreign-resource details.

**Step 3: Add failing SQL transaction tests**

Test command receipt lookup/insert under complete tenant scope. Inject an exception after a provisional domain write and prove no command receipt commits.

**Step 4: Implement session-bound SQL helpers**

Helpers accept an existing `AsyncSession`; they must not open their own transaction. Implement:

- scoped command lookup;
- replay/intent conflict classification;
- command receipt insertion;
- authoritative audit insertion using an accountable actor and correlation ID.

Do not read or write another module’s domain tables.

**Step 5: Run GREEN and static checks**

```bash
uv run pytest services/api/tests/commanding/test_governed_command_kernel.py -q
uv run ruff check services/api/src/clearcut/commanding services/api/tests/commanding
uv run pyright services/api/src/clearcut/commanding services/api/tests/commanding
```

Expected: PASS with zero type errors.

### Task 4: Implement the evidence-decision vertical slice

**Files:**
- Create: `services/api/src/clearcut/decisions/ports/repository.py`
- Create: `services/api/src/clearcut/decisions/adapters/sql_repository.py`
- Create: `services/api/src/clearcut/decisions/application/record_evidence_decision.py`
- Modify: `services/api/src/clearcut/decisions/delivery/http.py`
- Modify: `services/api/src/clearcut/main.py`
- Modify: `services/api/src/clearcut/items/delivery/http.py`
- Test: `services/api/tests/decisions/test_decision_audit_pipeline.py`
- Create: `services/api/tests/decisions/test_governed_evidence_decision.py`

**Step 1: Write the failing role/scope tests**

Cover Owner/Admin/Reviewer success; Editor and Viewer denial; deactivated membership; unknown item; foreign organization/project safe parity.

Run:

```bash
uv run pytest services/api/tests/decisions/test_governed_evidence_decision.py -k 'role or scope or membership' -q
```

Expected: FAIL because the canonical endpoint lacks complete command semantics.

**Step 2: Write the failing evidence and validation tests**

Cover canonical decision values, required rationale, required version/intent/key, and zero-evidence rejection for clearance-like outcomes. Prove escalation/further-review remains possible with zero claims.

**Step 3: Write failing concurrency/idempotency tests**

Cover:

- same key and same intent returns the original persisted result;
- same key and different intent returns 409;
- two actors/requests using the same expected version yield one success and one stale 409;
- stale failure does not write a decision or audit event.

**Step 4: Write the failing audit rollback test**

Inject authoritative audit insertion failure and assert item version/status, decision row, and command receipt all roll back.

**Step 5: Implement the port, SQL repository, and service**

The service receives authenticated scope and typed request data. The SQL repository owns exact decision/item writes and uses the existing session-bound command helpers. It must:

1. load the exact item under organization/project scope;
2. verify current capability from server scope;
3. validate evidence policy;
4. classify idempotent replay;
5. compare expected version;
6. insert immutable decision;
7. conditionally advance item state/version;
8. insert command receipt and authoritative audit;
9. return a typed persisted result.

**Step 6: Replace the public handler**

Mount exactly the canonical `:recordEvidenceDecision` operation. Retire the mismatched `/items/{item}/decisions` public behavior instead of preserving two command routes.

**Step 7: Run GREEN suites**

```bash
uv run pytest services/api/tests/decisions/test_governed_evidence_decision.py services/api/tests/decisions/test_decision_audit_pipeline.py services/api/tests/items -q
```

Expected: PASS.

### Task 5: Implement assignment as an operational versioned command

**Files:**
- Create: `services/api/src/clearcut/items/ports/command_repository.py`
- Create: `services/api/src/clearcut/items/adapters/sql_command_repository.py`
- Create: `services/api/src/clearcut/items/application/assign_item.py`
- Modify: `services/api/src/clearcut/items/delivery/http.py`
- Create: `services/api/tests/items/test_item_assignment_commands.py`

**Step 1: Write failing authorization and assignee tests**

Cover Owner/Admin/Editor/Reviewer success, Viewer denial, inactive/foreign assignee rejection, exact-item scope, and safe not-found parity.

**Step 2: Write failing version/idempotency/audit tests**

Cover stale version, replay, key/intent mismatch, no-row update, and audit failure rollback.

Run:

```bash
uv run pytest services/api/tests/items/test_item_assignment_commands.py -q
```

Expected: FAIL because assignment is currently direct SQL without these invariants.

**Step 3: Implement minimal application service and repository**

Validate active project membership for the assignee. Persist assignment, item version, command receipt, and authoritative audit atomically.

**Step 4: Replace the direct-SQL handler and reach GREEN**

```bash
uv run pytest services/api/tests/items/test_item_assignment_commands.py services/api/tests/items/test_items_http.py -q
```

Expected: PASS.

### Task 6: Implement governed disposition

**Files:**
- Create: `services/api/src/clearcut/decisions/application/set_disposition.py`
- Modify: `services/api/src/clearcut/decisions/ports/repository.py`
- Modify: `services/api/src/clearcut/decisions/adapters/sql_repository.py`
- Modify: `services/api/src/clearcut/items/delivery/http.py` or move canonical delivery to `decisions/delivery/http.py`
- Create: `services/api/tests/decisions/test_governed_disposition.py`

**Step 1: Write failing role, rationale, evidence, and legal-boundary tests**

Cover Owner/Admin/Reviewer success, Editor/Viewer denial, required rationale, canonical enum validation, zero-evidence protection, and response language that never claims legal clearance.

**Step 2: Write failing concurrency/idempotency/rollback tests**

Use the same invariant matrix as decisions.

Run:

```bash
uv run pytest services/api/tests/decisions/test_governed_disposition.py -q
```

Expected: FAIL because the existing disposition path is direct SQL and accepts arbitrary values.

**Step 3: Implement and mount the canonical command**

Reuse the command kernel; do not duplicate receipt/audit logic. Persist disposition and item transition/version atomically.

**Step 4: Run GREEN**

```bash
uv run pytest services/api/tests/decisions/test_governed_disposition.py services/api/tests/decisions -q
```

Expected: PASS.

### Task 7: Implement referral and acknowledgement

**Files:**
- Create: `services/api/src/clearcut/collaboration/ports/repository.py`
- Create: `services/api/src/clearcut/collaboration/adapters/sql_repository.py`
- Create: `services/api/src/clearcut/collaboration/application/referrals.py`
- Create: `services/api/src/clearcut/collaboration/delivery/http.py`
- Modify: `services/api/src/clearcut/main.py`
- Create: `services/api/tests/collaboration/test_referral_commands.py`

**Step 1: Write failing draft/submit/acknowledge role tests**

Cover:

- Editor may draft but not submit;
- Owner/Admin/Reviewer may submit;
- acknowledgement requires an active authorized target actor;
- transitions are scoped, versioned, and attributable.

**Step 2: Write failing idempotency, stale, audit, and outbox tests**

Assert referral state, command receipt, audit, and outbox commit together. Inject audit and outbox failures separately and prove rollback.

Run:

```bash
uv run pytest services/api/tests/collaboration/test_referral_commands.py -q
```

Expected: FAIL because no persistent canonical referral delivery exists.

**Step 3: Implement repository and application services**

Keep draft, submit, and acknowledge as explicit transitions. Use one transaction per accepted command.

**Step 4: Mount canonical generated operations and reach GREEN**

```bash
uv run pytest services/api/tests/collaboration/test_referral_commands.py tests/contracts/test_mounted_operation_ids.py -q
```

Expected: PASS.

### Task 8: Implement comments, replies, revisions, mentions, and outbox

**Files:**
- Create: `services/api/src/clearcut/collaboration/application/comments.py`
- Modify: `services/api/src/clearcut/collaboration/ports/repository.py`
- Modify: `services/api/src/clearcut/collaboration/adapters/sql_repository.py`
- Modify: `services/api/src/clearcut/collaboration/delivery/http.py`
- Create: `services/api/tests/collaboration/test_comment_commands.py`
- Create: `services/api/tests/collaboration/test_comment_outbox.py`

**Step 1: Write failing comment and reply-depth tests**

Cover exact item scope, active member requirement, blank content, one-level reply success, reply-to-reply rejection, and immutable parent identity.

**Step 2: Write failing revision-history tests**

Assert revisions append immutable records and preserve attributable author/time/history.

**Step 3: Write failing mention tests**

Cover active scoped recipients, actor exclusion, foreign/inactive recipients, duplicate IDs, and no username parsing as authority.

**Step 4: Write failing outbox transaction tests**

Assert source comment/revision, mention rows, audit, and deduplicated outbox rows commit together. Inject failure and prove total rollback.

Run:

```bash
uv run pytest services/api/tests/collaboration/test_comment_commands.py services/api/tests/collaboration/test_comment_outbox.py -q
```

Expected: FAIL because runtime comments/outbox are in-memory.

**Step 5: Implement minimal persisted services and delivery**

Retire process-local `CommentService` and `OutboxEventService` from runtime composition. Keep typed ports/results; no raw dictionaries across application boundaries.

**Step 6: Run GREEN**

```bash
uv run pytest services/api/tests/collaboration -q
```

Expected: PASS.

### Task 9: Expand the authoritative item detail projection

**Files:**
- Modify: `services/api/src/clearcut/items/delivery/http.py`
- Create or modify: `services/api/src/clearcut/items/application/read_models.py`
- Create or modify: `services/api/src/clearcut/items/adapters/sql_read_repository.py`
- Modify: `services/api/tests/items/test_items_http.py`
- Create: `services/api/tests/items/test_item_collaboration_projection.py`

**Step 1: Write failing projection tests**

Require item detail to return:

- exact scoped item and current version;
- persisted claims and source snapshots;
- explicit zero-evidence state;
- evidence conflicts;
- decision/disposition history;
- assignment;
- referral lifecycle;
- comments, replies, revisions, and mention recipient IDs;
- server-derived capabilities and explanations.

Corrupt ownership dimensions in test fixtures and prove no cross-tenant history/claims/comments are projected.

**Step 2: Run RED**

```bash
uv run pytest services/api/tests/items/test_item_collaboration_projection.py -q
```

Expected: FAIL because detail currently returns incomplete shapes and `comments: []`.

**Step 3: Implement a typed read model and scoped SQL repository**

Avoid N+1 queries. Use page/item-bounded bulk reads and repeat complete organization/project/item predicates on child records. Return zero evidence as an explicit persisted state, never fallback claims.

**Step 4: Run GREEN and query-count regression**

```bash
uv run pytest services/api/tests/items/test_item_collaboration_projection.py services/api/tests/items/test_items_http.py -q
```

Expected: PASS with bounded query count.

### Task 10: Replace frontend fallbacks with authoritative queries and mutations

**Files:**
- Create: `apps/web/src/queries/clearanceItems.ts`
- Create: `apps/web/src/mutations/clearanceItemCommands.ts`
- Modify: `apps/web/src/routes/o/$orgSlug/projects/$projectId/items/index.tsx`
- Modify: `apps/web/src/routes/o/$orgSlug/projects/$projectId/items/$itemId.tsx`
- Modify: `apps/web/src/routes/o/$orgSlug/projects/$projectId/workspace.tsx`
- Modify: `apps/web/src/features/clearance/EvidenceDrawer.tsx`
- Modify or replace: `apps/web/src/features/collaboration/CommentThread.tsx`
- Modify: `apps/web/src/features/collaboration/ReferralCard.tsx`
- Create: `apps/web/tests/unit/task-10-item-state.test.tsx` if the current unit harness supports it

**Step 1: Add failing source/runtime boundary tests**

Assert production code contains no fixed USPTO/California fallback claims, seeded Sarah Chen comment, `Date.now()` collaboration identity, browser-local referral completion, or fallback-to-first-item selection.

Run the narrow frontend/foundation test command available in the repository. If no React unit harness exists, add these assertions to an existing foundation test before production edits.

Expected: FAIL on the current fallback code.

**Step 2: Add failing interaction tests for authoritative mutation behavior**

Cover:

- no optimistic state transition;
- mutation retry disabled;
- success invalidates/refetches exact queries;
- stale 409 preserves form input;
- capability explanation is visible/focusable;
- direct item identity is preserved.

**Step 3: Implement shared query and mutation adapters**

Use generated clients only. Convert typed API errors consistently. Keep command inputs in component state only until accepted; persisted domain state remains query-owned.

**Step 4: Replace local/fabricated UI behavior**

Render explicit zero evidence, persisted history, comments/referrals, and typed failures. Remove all Task 10 fallback data and local success state.

**Step 5: Run GREEN and build**

```bash
pnpm --filter clearcut-web build
```

Run the focused frontend/foundation tests and expect PASS.

### Task 11: Add API-connected multi-user Task 10 Playwright coverage

**Files:**
- Create: `apps/web/tests/e2e/evidence-workspace.spec.ts`
- Create: `apps/web/tests/e2e/evidence-access.spec.ts`
- Modify: `apps/web/tests/support/e2e_api.py`
- Modify only if required: `apps/web/playwright.config.ts`
- Modify: `tests/foundation/test_web_runtime_boundary.py`

**Step 1: Write one failing Reviewer decision browser test**

Exercise a direct item deep link, persisted cited/zero-evidence state, decision form, generated API command, and authoritative post-success refresh. Confirm the UI never displays a legal-clearance guarantee.

Run:

```bash
PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=mac15-arm64 pnpm --filter clearcut-web exec playwright test tests/e2e/evidence-workspace.spec.ts --project=chromium-desktop-1440
```

Expected: FAIL because the authoritative Task 10 UI/backend flow is not complete.

**Step 2: Reach GREEN for the Reviewer decision**

Make only the minimum support/runtime changes required by the test.

**Step 3: Add RED/GREEN browser cases incrementally**

One test at a time:

1. two-user stale conflict retains input;
2. assignment and disposition;
3. referral and acknowledgement;
4. comment, one-level reply, revision, authorized mention;
5. role denial and capability explanation;
6. exact deep link and unknown/foreign safe parity;
7. zero-evidence behavior;
8. keyboard/focus restoration.

Run each focused test to RED, implement minimally, then rerun to GREEN.

**Step 4: Run the serial four-engine matrix**

```bash
PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=mac15-arm64 pnpm --filter clearcut-web exec playwright test tests/e2e/evidence-workspace.spec.ts tests/e2e/evidence-access.spec.ts
```

Expected: all tests pass using the checked-in one worker.

### Task 12: Final Task 10 verification and review

**Files:**
- Modify only if verification exposes an attributable defect.
- Update evidence/status documentation only after all gates are green.

**Step 1: Run focused backend suites**

```bash
uv run pytest services/api/tests/commanding services/api/tests/decisions services/api/tests/items services/api/tests/collaboration services/api/tests/organizations/test_tenant_isolation.py services/api/tests/architecture/test_governed_collaboration_schema.py services/api/tests/architecture/test_migrated_runtime_schema.py -q
```

Expected: PASS.

**Step 2: Run contract checks**

```bash
pnpm contract:check
```

Expected: valid OpenAPI 3.1, generated headers, zero drift, all contract tests pass.

**Step 3: Run web build and Task 10 Playwright**

```bash
pnpm --filter clearcut-web build
PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=mac15-arm64 pnpm --filter clearcut-web exec playwright test tests/e2e/evidence-workspace.spec.ts tests/e2e/evidence-access.spec.ts
```

Expected: build succeeds; browser matrix passes using one worker.

**Step 4: Run exact attributable static checks**

```bash
uv run ruff format --check <task-10-python-files>
uv run ruff check <task-10-python-files>
uv run pyright <task-10-python-files>
node --check scripts/generate-clients.mjs
git diff --check -- apps/web packages/contracts scripts/generate-clients.mjs services/api/alembic/versions services/api/src services/api/tests tests ':(exclude)services/api/.clearcut/**'
```

Expected: all commands exit 0. Do not reformat unrelated working-tree debt.

**Step 5: Perform security and integrity self-review**

Verify explicitly:

- every project-owned read/write carries organization and project scope;
- the actor and capabilities are server-derived;
- protected rules are unchanged;
- governed writes and authoritative audit events are transactional;
- idempotency and stale conflicts cannot partially write;
- referrals/comments and outbox events are scoped and attributable;
- zero evidence remains unresolved;
- no fabricated evidence or collaboration state remains;
- no legal conclusion is presented;
- migrations upgrade and downgrade safely;
- generated artifacts match OpenAPI;
- frontend mutations are non-optimistic and exact-item preserving.

**Step 6: Request independent reviews and resolve material findings test-first**

Obtain semantic and targeted code-quality review. For every P0/P1/P2 finding, add a failing regression test before the fix, record RED/GREEN, and rerun the relevant final gates.

**Step 7: Record completion without committing**

Report exact RED/GREEN evidence, validation outputs, changed files, known unrelated debt, and observed constraints. Do not create a commit unless the user explicitly requests one.

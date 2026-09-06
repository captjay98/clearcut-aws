# Testable AI and Records Flow Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a truthful local browser flow from signup and screenplay import through Gemini detection/judging, Parallel research, AI Trust, Records, and governed report receipts, while preserving production-ready job semantics.

**Architecture:** Alembic is the schema authority. HTTP handlers transact scoped intent, jobs, and audit state; local FastAPI background tasks and production Cloud Tasks call the same application services. Gemini uses role-based routing (3.7 Flash detection, 3.1 Flash-Lite planning, 3.1 Pro Preview judging). Parallel Search is mandatory and Extract is bounded to Search-authorized URLs. Trust and Records read persisted evaluation, provider-attempt, policy, operation, and audit data—never defaults.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy/asyncpg, Alembic, PostgreSQL 17, google-genai/Vertex AI global, Parallel Search/Extract over httpx, React 18, TanStack Router/Query, generated OpenAPI clients, Vite 7, Vitest 4, Playwright 1.62, Docker Compose.

---

## Execution rules

- Follow red → green → refactor for every behavior change.
- Run provider calls outside database transactions.
- Preserve tenant scope in every query and foreign-key relationship.
- Never add a production hermetic fallback or fabricated UI success.
- Do not expose credentials, raw provider payloads, complete screenplay text, signed URLs, or hidden model reasoning in Records.
- Make narrow commits only after the relevant focused and regression tests pass.
- Do not run live paid provider tests unless the environment explicitly enables them.

### Task 1: Make Alembic the single schema authority

**Files:**
- Create: `services/api/alembic/versions/0022_runtime_alignment.py`
- Modify: `services/api/src/clearcut/init_db.py`
- Modify: `services/api/tests/conftest.py`
- Create: `services/api/tests/architecture/test_migrated_runtime_schema.py`
- Modify: `services/api/tests/detection/test_detection_endpoint.py`
- Modify: `services/api/tests/research/test_research_endpoint.py`

**Step 1: Write the failing migration-shape tests**

Add tests that migrate an empty database to head and assert one canonical `jobs` shape: scoped IDs, type, status, idempotency key, JSON payload/result, error, progress/stage, actor/correlation IDs, attempt count, available/created/updated timestamps, and lease fields. Assert required research/evaluation/audit/report tables exist. Exercise both enqueue endpoints against the migrated schema.

**Step 2: Verify red**

Run:

```bash
uv run pytest services/api/tests/architecture/test_migrated_runtime_schema.py services/api/tests/detection/test_detection_endpoint.py services/api/tests/research/test_research_endpoint.py -q
```

Expected: failures showing `target_id/progress` endpoint SQL is incompatible with migration 0006 and runtime bootstrap owns competing DDL.

**Step 3: Implement the alignment migration**

Create revision 0022 without rewriting historical migrations. Add/rename columns and constraints required by the canonical job, provider-attempt, provenance, evaluation, authoritative-audit, and report models. Add scoped idempotency and claim/provenance constraints. Preserve existing data with explicit backfills before adding non-null constraints.

**Step 4: Remove competing runtime DDL**

Reduce `init_db.py` to development/test orchestration that invokes migrations and optional idempotent seed services. It must not define alternate production table shapes or swallow schema failures.

**Step 5: Update tests and endpoint SQL to canonical columns**

Use typed payloads for target IDs rather than ad-hoc incompatible columns. Include actor and correlation IDs in job/audit records.

**Step 6: Verify green**

Run the focused tests, then:

```bash
uv run pytest tests/contracts tests/foundation services/api/tests -q
```

**Step 7: Commit**

```bash
git add services/api/alembic/versions/0022_runtime_alignment.py services/api/src/clearcut/init_db.py services/api/tests

git commit -m "fix(api): align runtime with canonical migrations"
```

### Task 2: Restore one API contract and generated client

**Files:**
- Modify: `packages/contracts/openapi.yaml`
- Modify: `services/api/src/clearcut/main.py`
- Modify: mounted delivery routers under `services/api/src/clearcut/*/delivery/http.py`
- Create: `services/api/src/clearcut/operations/delivery/http.py`
- Regenerate: `packages/contracts/generated/typescript/index.ts`
- Regenerate: `packages/contracts/generated/python/__init__.py`
- Create: `tests/contracts/test_mounted_operation_ids.py`
- Create: `tests/contracts/fixtures/generated-client-usage.ts`
- Modify: `scripts/check-contract-drift.mjs`

**Step 1: Write the failing canonical inventory test**

Load `packages/contracts/openapi.yaml` and assert exact method/path/operation-ID entries for the approved vertical slice:

- identity/entry: `registerUser`, `createSession`, `getSessionContext`, `deleteCurrentSession`, organization entry, and project list/create/read;
- script lifecycle: project script read, upload/finalize/paste/parse/warning acceptance/version commit/version list/version read, detection, and research;
- project jobs: `listJobs`, `getJob`, `retryJob`, and `cancelJob`;
- project Trust: `listTrustEvaluations` and `getTrustEvaluation`;
- organization Records: `listRecords` with required `view`, `getRecord`, and `getProviderAttempt`;
- reports: `previewReport`, `generateReportSnapshot`, `releaseReport`, `listReportHistory`, and `getReportDownloadMetadata`.

Use camelCase path parameters in every canonical template. Assert operation IDs are globally unique.

**Step 2: Write the failing mounted-parity test**

Build an inventory from FastAPI `APIRoute` instances and assert every required operation is mounted exactly once with explicit matching method, path, and `operation_id`. Ignore the conditional SPA catch-all. Assert incomplete later-task boundaries return HTTP 503 with the standard `capability_unavailable` error envelope rather than fabricated successful data.

**Step 3: Write the failing generated-client compile fixture**

Compile representative generated calls that use:

```ts
const result = await api.getJob({ params: { orgId, projectId, jobId } })
if (result.ok) {
  consume(result.value)
  consume(result.meta)
}
```

Include body/query examples and report release. Calls using `path`, snake_case parameter keys, or `result.value.data` must not be the supported convention.

**Step 4: Verify red**

```bash
uv run pytest tests/contracts/test_mounted_operation_ids.py -q
bun scripts/check-contract-drift.mjs
```

Expected: failures for missing registration/job/Trust/Records/report operations, generated FastAPI operation IDs, snake_case path templates, side-effecting drift checks, and missing generated-client metadata typing.

**Step 5: Normalize the contract and mount truthful boundaries**

Use `/api/v1/organizations/{orgId}/projects/{projectId}` consistently. Add explicit FastAPI `operation_id` declarations. Preserve existing real handlers where their request/response semantics are authoritative; otherwise return typed HTTP 503 `capability_unavailable` until the owning later task supplies the repository/application service. Remove hard-coded Trust scores, seeded Records rows, synthetic report receipts, and other placeholder success behavior from canonical operations.

Canonical later-task resource shapes are:

- jobs: `/jobs`, `/jobs/{jobId}`, `/jobs/{jobId}:retry`, `/jobs/{jobId}:cancel`;
- Trust: `/evaluations`, `/evaluations/{evaluationId}`;
- Records: `/records?view=activity|runsAndTools|evaluations|policies|operations`, `/records/{recordId}`, `/provider-attempts/{attemptId}`;
- reports: `/report-preview`, `/report-snapshots`, `/report-snapshots/{snapshotId}:release`, `/report-history`, `/report-releases/{releaseId}/artifact-metadata`.

**Step 6: Regenerate clients without hand edits**

Update the generator so successful envelope payloads remain unwrapped as `result.value` while optional envelope metadata is exposed as `result.meta`. Make contract drift checking non-mutating by generating to temporary output or comparing in memory.

```bash
pnpm contract:generate
```

**Step 7: Verify green**

```bash
uv run pytest tests/contracts -q
pnpm contract:check
pnpm --filter clearcut-web build
```

Do not create a commit unless the user explicitly authorizes one.

### Task 3: Implement truthful signup and local sessions

**Files:**
- Modify: `services/api/src/clearcut/identity/delivery/http.py`
- Modify: `services/api/scripts/seed_db.py`
- Create: `apps/web/src/routes/auth/sign-up.tsx`
- Modify: `apps/web/src/routes/auth/sign-in.tsx`
- Modify: `apps/web/src/routeTree.gen.ts` only through router generation
- Create: `services/api/tests/identity/test_registration_http.py`
- Create: `apps/web/tests/e2e/signup-onboarding.spec.ts`

**Step 1: Write failing HTTP tests**

Test registration, duplicate email, password validation, persisted credentials, session-context lookup, logout, and local cookie acceptance. Assert local HTTP uses `clearcut_session` or another valid non-`__Host` cookie; HTTPS production uses `__Host-clearcut_session` with `Secure`, `Path=/`, and no Domain.

**Step 2: Verify red**

```bash
uv run pytest services/api/tests/identity/test_registration_http.py -q
```

**Step 3: Implement cookie/environment policy and idempotent seed behavior**

Stop reseeding from truncating users, credentials, and sessions on every startup. Gate demo seed with `CLEARCUT_SEED_DEMO`; make it idempotent.

**Step 4: Write the failing browser test**

The Playwright test signs up, reloads, reaches onboarding, creates an organization, and remains authenticated.

**Step 5: Implement signup UI with generated client only**

Add loading, duplicate-account, validation, and provider-unavailable states. Fix sign-in’s unwrapped organization-entry handling. Add a visible signup link.

**Step 6: Verify green**

```bash
uv run pytest services/api/tests/identity -q
pnpm --filter clearcut-web build
pnpm --filter clearcut-web test:e2e -- signup-onboarding.spec.ts
```

**Step 7: Commit**

```bash
git add services/api/src/clearcut/identity services/api/scripts/seed_db.py services/api/tests/identity apps/web/src/routes/auth apps/web/tests/e2e/signup-onboarding.spec.ts

git commit -m "feat(identity): add truthful local signup flow"
```

### Task 4: Implement persistent screenplay import and version one

**Files:**
- Modify: `services/api/src/clearcut/scripts/delivery/http.py`
- Create: `services/api/src/clearcut/scripts/application/import_script.py`
- Create: `services/api/src/clearcut/scripts/adapters/sql_import_repository.py`
- Modify: existing parsers under `services/api/src/clearcut/scripts/`
- Modify: `apps/web/src/features/scripts/ScriptUploadModal.tsx`
- Modify: `apps/web/src/routes/o/$orgSlug/projects/$projectId/workspace.tsx`
- Create: `demo/original-screenplay/clearcut_test.fountain`
- Create: `services/api/tests/scripts/test_import_pipeline_http.py`
- Create: `apps/web/tests/e2e/script-import.spec.ts`

**Step 1: Write failing import tests**

Cover paste and multipart upload, hash/size/type validation, persistent artifact creation, Fountain parse diagnostics, explicit warning acceptance, immutable version commit, element persistence, duplicate commit/idempotency, and scoped script readback.

**Step 2: Verify red**

```bash
uv run pytest services/api/tests/scripts/test_import_pipeline_http.py -q
```

**Step 3: Implement the application service and SQL repository**

Persist the original artifact, parse result, warnings, accepted-warning record, script version, and elements. Use object-storage abstraction for bytes and SQL for metadata. Do not store paste input only in process memory.

**Step 4: Create the original Fountain screenplay**

Write six to eight scenes with valid headings, action, dialogue, transitions, and original narrative. Include realistic references across protected categories without copying screenplay material.

**Step 5: Write failing browser import test**

Create a project, import the Fountain file through the UI, acknowledge real warnings, commit v1, reload, and assert persisted scenes—not “Borrowed Light” fallback content—are visible.

**Step 6: Replace mocked UI behavior**

Remove fabricated counts and fallback scenes. Use generated import/parse/accept/commit/read operations and explicit empty/error states.

**Step 7: Verify green and commit**

```bash
uv run pytest services/api/tests/scripts -q
pnpm --filter clearcut-web build
pnpm --filter clearcut-web test:e2e -- script-import.spec.ts
```

```bash
git add services/api/src/clearcut/scripts services/api/tests/scripts apps/web/src/features/scripts apps/web/src/routes/o demo/original-screenplay/clearcut_test.fountain

git commit -m "feat(scripts): persist imported screenplay versions"
```

### Task 5: Add observable jobs and local background dispatch

**Files:**
- Create: `services/api/src/clearcut/operations/ports/job_repository.py`
- Create: `services/api/src/clearcut/operations/adapters/sql_job_repository.py`
- Create: `services/api/src/clearcut/operations/application/run_job.py`
- Create: `services/api/src/clearcut/operations/application/local_dispatcher.py`
- Create: `services/api/src/clearcut/operations/delivery/http.py`
- Modify: `services/api/src/clearcut/main.py`
- Modify: detection/research start handlers
- Create: `services/api/tests/operations/test_local_job_lifecycle.py`
- Create: `services/api/tests/operations/test_job_http.py`

**Step 1: Write failing lifecycle tests**

Test enqueue idempotency, post-commit dispatch, queued → running → succeeded, typed failure, retry, cancel, attempt history, cross-tenant access, and startup conversion of stale local running jobs to manual-retry/interrupted.

**Step 2: Verify red**

```bash
uv run pytest services/api/tests/operations -q
```

**Step 3: Implement repository and application service**

Claim and transition jobs in short transactions. Never hold a transaction during provider work. Enforce allowed transitions and attempt linkage.

**Step 4: Implement local dispatcher**

Wrap FastAPI `BackgroundTasks`. Refuse local mode when configured for more than one process. Label local dispatch non-durable in health/readiness metadata.

**Step 5: Implement scoped read/retry/cancel endpoints**

Return safe progress, stage, terminal result summary, typed safe error, and attempt history.

**Step 6: Verify green and commit**

```bash
uv run pytest services/api/tests/operations services/api/tests/detection/test_detection_endpoint.py services/api/tests/research/test_research_endpoint.py -q
```

```bash
git add services/api/src/clearcut/operations services/api/src/clearcut/main.py services/api/src/clearcut/detection/delivery/http.py services/api/src/clearcut/research/delivery/http.py services/api/tests

git commit -m "feat(operations): execute observable local background jobs"
```

### Task 6: Configure Gemini roles and production Pro judge

**Files:**
- Create: `services/api/src/clearcut/ai/model_roles.py`
- Modify: `services/api/src/clearcut/detection/adapters/vertex_runtime.py`
- Create: `services/api/src/clearcut/evaluation/ports/judge.py`
- Create: `services/api/src/clearcut/evaluation/adapters/vertex_judge.py`
- Create: `services/api/src/clearcut/evaluation/adapters/sql_evaluation_repository.py`
- Modify: `services/api/src/clearcut/detection/runtime_provider.py`
- Create: `services/api/tests/ai/test_model_role_configuration.py`
- Create: `services/api/tests/evaluation/test_vertex_judge_contract.py`

**Step 1: Write failing role tests**

Assert defaults are 3.7 Flash detection, 3.1 Flash-Lite research planning, and 3.1 Pro Preview judge. Assert returned model versions are persisted and provider failure does not silently switch models.

**Step 2: Write failing judge-boundary tests**

Use sanitized/hermetic responses to prove the judge emits dimension scores and critique but cannot create a decision, claim, policy mutation, or clearance state. Assert one repair pass maximum.

**Step 3: Verify red**

```bash
uv run pytest services/api/tests/ai services/api/tests/evaluation -q
```

**Step 4: Implement typed role configuration and judge adapter**

Use structured JSON schema. Persist rubric/prompt/policy/model/input bindings, usage, latency, response ID, and safe error. Do not persist hidden reasoning.

**Step 5: Verify green and commit**

```bash
uv run pytest services/api/tests/ai services/api/tests/evaluation services/api/tests/conformance/test_provider_selection.py -q
```

```bash
git add services/api/src/clearcut/ai services/api/src/clearcut/detection services/api/src/clearcut/evaluation services/api/tests/ai services/api/tests/evaluation

git commit -m "feat(ai): route Gemini detection planning and judging roles"
```

### Task 7: Execute and persist detection jobs

**Files:**
- Create: `services/api/src/clearcut/detection/application/run_detection_job.py`
- Create: `services/api/src/clearcut/detection/adapters/sql_candidate_repository.py`
- Modify: `services/api/src/clearcut/detection/delivery/http.py`
- Modify: `services/api/src/clearcut/operations/application/run_job.py`
- Create: `services/api/tests/detection/test_detection_job_execution.py`

**Step 1: Write failing execution test**

Import a committed script, enqueue detection, run the local job, and assert every non-empty element is offered to 3.7 Flash; candidates retain span/rationale/uncertainty and version/model provenance; deterministic gates and Pro verdict persist; terminal summary is truthful.

Add failure cases for malformed structured output, retryable provider error, policy-invalid category, judge rejection, one bounded repair pass, and zero candidates.

**Step 2: Verify red, implement minimal service, verify green**

```bash
uv run pytest services/api/tests/detection/test_detection_job_execution.py -q
```

The service loads scoped version/elements, records attempts, calls outside transactions, validates outputs, persists unresolved clearance items, runs the judge, and commits terminal state idempotently.

**Step 3: Regression and commit**

```bash
uv run pytest services/api/tests/detection services/api/tests/operations services/api/tests/evaluation -q
```

```bash
git add services/api/src/clearcut/detection services/api/src/clearcut/operations services/api/tests/detection

git commit -m "feat(detection): execute Gemini detection and judge jobs"
```

### Task 8: Execute Parallel Search and bounded Extract research

**Files:**
- Modify: `services/api/src/clearcut/research/ports/web_search.py`
- Modify: `services/api/src/clearcut/research/adapters/parallel_search.py`
- Modify: `services/api/src/clearcut/research/adapters/parallel_extract.py`
- Create: `services/api/src/clearcut/research/application/run_research_job.py`
- Create: `services/api/src/clearcut/research/adapters/sql_research_repository.py`
- Modify: `services/api/src/clearcut/research/delivery/http.py`
- Create: `services/api/tests/research/test_research_job_execution.py`
- Create: `services/api/tests/research/test_parallel_adapter_contract.py`

**Step 1: Write failing planning/provider tests**

Assert Flash-Lite produces one objective plus two or three bounded queries. Search receives exact persisted queries and correlation metadata. Extract is skipped on Search failure/empty results and accepts at most three canonical HTTPS URLs from the same persisted Search run.

Assert raw Extract error dictionaries are normalized to typed `ExtractedPageError` objects.

**Step 2: Verify red**

```bash
uv run pytest services/api/tests/research/test_research_job_execution.py services/api/tests/research/test_parallel_adapter_contract.py -q
```

**Step 3: Implement research orchestration**

Persist run/query/attempt before external calls, authentic provider IDs, warnings, usage, timing, per-URL outcomes, immutable snapshots, Search authorization links, and zero-evidence unresolved outcomes. Admission must verify exact attributable excerpt and tenant/item/version/run/query/attempt scope.

**Step 4: Run Pro research judge**

Judge only after deterministic provenance gates. Permit one bounded wording/query repair without adding uncited facts. Persist dimension verdicts separately from claims.

**Step 5: Verify green and commit**

```bash
uv run pytest services/api/tests/research services/api/tests/evidence services/api/tests/evaluation -q
```

```bash
git add services/api/src/clearcut/research services/api/tests/research

git commit -m "feat(research): execute cited Parallel research jobs"
```

### Task 9: Implement the mock’s New Clearance progress flow

**Files:**
- Modify: `apps/web/src/routes/o/$orgSlug/projects/new.tsx`
- Modify/create components under `apps/web/src/features/scripts/`
- Create: `apps/web/src/features/operations/JobProgress.tsx`
- Create: `apps/web/tests/e2e/new-clearance-flow.spec.ts`

**Step 1: Write failing Playwright flow**

Cover Describe production → Bring in script → Check script. Assert actual counts and stages come from job/version data, cancel invokes the API, partial results are not shown as complete, and actions navigate to persisted screenplay/items/Records.

**Step 2: Verify red**

```bash
pnpm --filter clearcut-web test:e2e -- new-clearance-flow.spec.ts
```

**Step 3: Implement against generated operations**

Use TanStack Query polling with terminal-state stop conditions. Render explicit loading, unavailable, failed, cancelled, unresolved, and succeeded states. Never estimate/fabricate counts.

**Step 4: Verify green and commit**

```bash
pnpm --filter clearcut-web build
pnpm --filter clearcut-web test:e2e -- new-clearance-flow.spec.ts
```

```bash
git add apps/web/src/routes/o apps/web/src/features apps/web/tests/e2e/new-clearance-flow.spec.ts

git commit -m "feat(web): implement truthful clearance run progress"
```

### Task 10: Back AI Trust with persisted evaluation data

**Files:**
- Modify: `services/api/src/clearcut/evaluation/delivery/http.py`
- Create: `services/api/src/clearcut/evaluation/application/read_trust.py`
- Modify: `apps/web/src/routes/o/$orgSlug/trust.tsx`
- Modify: Trust components under `apps/web/src/features/`
- Create: `services/api/tests/evaluation/test_trust_http.py`
- Replace/modify: `apps/web/tests/e2e/trust-center-learning.spec.ts`

**Step 1: Write failing API tests**

Assert Trust reads persisted gates/verdicts/bindings for a scoped run and returns empty/unavailable rather than defaults. Test ten dimensions, weakest dimension, version bindings, latency/cost, and cross-tenant rejection.

**Step 2: Write failing browser tests**

Prove displayed scores match persisted evaluations. Prove no evaluation yields an honest empty state. Learning promote/rollback must require a real candidate, authorization, governed transaction, and Records event.

**Step 3: Implement read model and UI**

Remove `RubricVisualizer`, protected-config, and learning-candidate defaults. Keep protected changes human-only.

**Step 4: Verify and commit**

```bash
uv run pytest services/api/tests/evaluation -q
pnpm --filter clearcut-web build
pnpm --filter clearcut-web test:e2e -- trust-center-learning.spec.ts
```

```bash
git add services/api/src/clearcut/evaluation services/api/tests/evaluation apps/web/src/routes/o apps/web/src/features apps/web/tests/e2e/trust-center-learning.spec.ts

git commit -m "feat(trust): render persisted gates and judge evaluations"
```

### Task 11: Implement all five Records views

**Files:**
- Modify: `services/api/src/clearcut/records/delivery/http.py`
- Create: `services/api/src/clearcut/records/adapters/sql_records_repository.py`
- Create: `services/api/src/clearcut/records/application/read_records.py`
- Modify: `apps/web/src/routes/o/$orgSlug/records.tsx`
- Create components under `apps/web/src/features/records/`
- Create: `services/api/tests/records/test_records_http.py`
- Create: `apps/web/tests/e2e/records.spec.ts`

**Step 1: Write failing API tests**

Cover Activity, Runs & tools, Evaluations, Policies, Operations, cursors/filters, record detail, attempt detail, retry/cancel authorization, redaction, and cross-tenant isolation. Read `authoritative_audit_events`, not disconnected legacy projections.

**Step 2: Verify red**

```bash
uv run pytest services/api/tests/records/test_records_http.py -q
```

**Step 3: Implement repository/read models**

Join only through scoped IDs. Redact secrets, raw payloads, complete source bodies, screenplay text, signed URLs, and hidden reasoning. Include attributable excerpts and hashes only where policy allows.

**Step 4: Write failing browser test and implement tabs**

Match the mock’s five-tab vocabulary and ledger dialog. Remove all seeded local rows and demo failure toggles.

```bash
pnpm --filter clearcut-web test:e2e -- records.spec.ts
```

**Step 5: Verify and commit**

```bash
uv run pytest services/api/tests/records -q
pnpm --filter clearcut-web build
pnpm --filter clearcut-web test:e2e -- records.spec.ts
```

```bash
git add services/api/src/clearcut/records services/api/tests/records apps/web/src/routes/o apps/web/src/features/records apps/web/tests/e2e/records.spec.ts

git commit -m "feat(records): expose authoritative AI operation records"
```

### Task 12: Complete governed report receipts and export history

**Files:**
- Modify: `services/api/src/clearcut/export/delivery/http.py`
- Create: `services/api/src/clearcut/export/application/report_service.py`
- Create: `services/api/src/clearcut/export/adapters/sql_report_repository.py`
- Modify: report route under `apps/web/src/routes/o/$orgSlug/projects/$projectId/`
- Modify: `apps/web/src/features/reports/ReportReceiptView.tsx`
- Modify/create backend export tests
- Create: `apps/web/tests/e2e/report-release.spec.ts`

**Step 1: Write failing transactional tests**

Generation must commit snapshot plus authoritative audit atomically. Release must commit release row, immutable release audit, and redacted receipt atomically. Roll back all on any failure. Assert complete manifest bindings and export-history metadata.

**Step 2: Remove fabricated UI success**

Write a failing browser test proving failed generation/release does not display Released, PostgreSQL matched, or a default receipt.

**Step 3: Implement services and UI states**

Add preview → generate frozen snapshot → accountable release confirmation → released receipt/history. Authorize artifact metadata/download separately.

**Step 4: Verify and commit**

```bash
uv run pytest services/api/tests/export -q
pnpm --filter clearcut-web build
pnpm --filter clearcut-web test:e2e -- report-release.spec.ts
```

```bash
git add services/api/src/clearcut/export services/api/tests/export apps/web/src apps/web/tests/e2e/report-release.spec.ts

git commit -m "feat(export): create authoritative report receipts"
```

### Task 13: Add production Cloud Tasks dispatch and Scheduler reconciliation

**Files:**
- Create: `services/api/src/clearcut/operations/ports/job_dispatcher.py`
- Create: `services/api/src/clearcut/operations/adapters/cloud_tasks_dispatcher.py`
- Create: `services/api/src/clearcut/operations/delivery/tasks_http.py`
- Create: `services/api/src/clearcut/operations/application/reconcile_jobs.py`
- Modify: infrastructure under `infra/`
- Create: `services/api/tests/operations/test_cloud_task_delivery.py`
- Create: `services/api/tests/operations/test_reconciliation.py`

**Step 1: Write failing duplicate-delivery/auth tests**

Assert OIDC/private task authentication, idempotent duplicate delivery, lease claim, expired-lease recovery, and outbox replay.

**Step 2: Implement adapter and handler**

Cloud Tasks dispatches user jobs. Scheduler calls only reconciliation and recurring monitoring entry points. Application services remain identical to local mode.

**Step 3: Verify and commit**

```bash
uv run pytest services/api/tests/operations -q
```

```bash
git add services/api/src/clearcut/operations services/api/tests/operations infra

git commit -m "feat(operations): add Cloud Tasks production dispatch"
```

### Task 14: Configure and run the local live test environment

**Files:**
- Modify: `docker-compose.yml`
- Modify: `scripts/start_local.sh`
- Modify: `.env.example`
- Create: `docs/guides/local-live-provider-testing.md`
- Modify: `apps/web/tests/e2e/` journey specs as required

**Step 1: Write configuration/startup checks**

Assert Compose uses one Uvicorn worker, migrations run before startup, seed is opt-in, provider role variables are passed, ADC is available without embedding credentials in images, and secrets are never committed.

**Step 2: Configure local environment**

Use:

```text
GOOGLE_CLOUD_PROJECT=clearcut-workspace
CLEARCUT_VERTEX_LOCATION=global
CLEARCUT_GEMINI_DETECTION_MODEL=gemini-3.7-flash
CLEARCUT_GEMINI_RESEARCH_MODEL=gemini-3.1-flash-lite
CLEARCUT_GEMINI_JUDGE_MODEL=gemini-3.1-pro-preview
PARALLEL_API_KEY=<local secret>
CLEARCUT_JOB_DISPATCH=background
CLEARCUT_SEED_DEMO=false
```

Set the ADC quota project on the host. Mount/read ADC for local development without copying it into the repository or image.

**Step 3: Start and verify servers**

```bash
./clearcut start
curl --fail http://localhost:8000/api/v1/healthz
```

Confirm startup output, migration head, single worker, SPA loading, and provider-readiness status.

**Step 4: Run explicit live smoke tests**

Run one bounded call for each configured Gemini role and one bounded Parallel Search/Extract flow. Persist and inspect attempts. Do not print secrets or raw screenplay/provider payloads.

**Step 5: Run the browser journey**

```bash
pnpm --filter clearcut-web test:e2e -- signup-onboarding.spec.ts script-import.spec.ts new-clearance-flow.spec.ts records.spec.ts
```

Manually verify signup → project → imported script → detection → research → Trust → Records against the mock vocabulary.

**Step 6: Run the full gate**

```bash
uv run pytest tests/contracts tests/foundation services/api/tests -q
pnpm contract:check
pnpm check:no-legacy
pnpm --filter clearcut-web test
pnpm --filter clearcut-web build
pnpm --filter clearcut-web test:e2e
```

Expected: all commands pass; live tests report exact provider model versions/attempt IDs; no fabricated fallbacks remain.

**Step 7: Commit documentation/configuration only after secret review**

```bash
git diff --check
git diff --cached
```

Confirm no API key, token, ADC file, raw provider response, or private screenplay content is staged.

```bash
git add docker-compose.yml scripts/start_local.sh .env.example docs/guides/local-live-provider-testing.md

git commit -m "chore(local): configure live provider test environment"
```

## Completion gate

Before declaring the feature ready:

- Re-read `docs/plans/2026-08-31-testable-ai-records-flow-design.md` acceptance criteria.
- Prove the full browser flow uses persisted data.
- Prove all three Gemini roles and both Parallel operations through stored attempts.
- Prove Trust and Records are empty/error truthful when data is absent.
- Prove zero evidence remains unresolved.
- Prove local restart interruption is visible.
- Prove production duplicate delivery is idempotent.
- Prove report generation/release and their authoritative audit events commit atomically.
- Run the full gate from Task 14 and record exact output in the remediation status document.

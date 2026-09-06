# Testable AI and Records Flow Design

**Status:** Approved

**Date:** 2026-08-31

**Scope:** Local signup through script import, Gemini detection and judging, Parallel research, persisted provenance, AI Trust, Records, and production dispatch boundaries.

## Objective

Deliver a truthful local vertical slice in which a new user can sign up, create an organization and project, import an original screenplay, trigger detection and research, observe real job state, inspect cited evidence and evaluations, and trace every operation through Records. The local application uses in-process background execution for speed. Production keeps the same application services but dispatches user jobs through Cloud Tasks.

ClearCut gathers evidence and coordinates accountable human review. It does not provide legal advice or declare legal clearance.

## Current-State Audit

The canonical visual and interaction source is the 20-surface mock at `/Users/captjay98/projects/clearcut/misc/clearcut-flow`. That directory is absent from the rebuild worktree, so the sibling canonical copy was used for comparison.

No AI Trust or Records feature is currently real end-to-end:

- `#new` is a three-stage describe → import → check experience in the mock. Production only has a project form, mocked script parsing, and enqueue-only detection/research handlers.
- `#trust` is backed by broken client calls and default rubric/configuration data. Evaluation is in-memory and hermetic; no production Gemini judge runs or persists verdicts.
- `#records` has Activity, Runs & tools, Evaluations, Policies, and Operations views. Production has a broken flat audit list and no run/tool/evaluation/policy/operation detail APIs.
- Provider attempts and richer evaluation/audit tables exist in migrations but have no complete repositories or runtime write paths.
- Report release displays fabricated receipt data and can report success after API failure. Authoritative generation/release receipts, artifacts, history, and download authorization are incomplete.
- Generated client operation names, path parameters, and response-envelope expectations differ from route usage throughout the frontend.
- Runtime bootstrap DDL and Alembic define incompatible job and provenance schemas.

The first implementation principle is therefore: build authoritative data paths before recreating dashboard visuals.

## Design Decisions

### Model routing

ClearCut uses deterministic role-based routing rather than a Lite-first cascade. A cheaper prefilter must never suppress screenplay material before the primary detector sees it.

| Model | Role | Allowed output |
| --- | --- | --- |
| `gemini-3.7-flash` | Primary detection over every non-empty script element | Structured candidate proposals with category, span, rationale, and uncertainty |
| `gemini-3.1-flash-lite` | Bounded research-query planning and later monitoring assistance | Two or three validated queries, objective suggestions, and advisory materiality summaries |
| `gemini-3.1-pro-preview` | Judge at detection and research checkpoints; difficult-case escalation | Dimension scores, critique, missing-risk suggestions, and advisory repair instructions |

All three exact IDs were live-verified against Vertex AI `locations/global` in project `clearcut-workspace` and returned HTTP 200 with matching `modelVersion`.

Configuration uses role-specific variables:

```text
CLEARCUT_GEMINI_DETECTION_MODEL=gemini-3.7-flash
CLEARCUT_GEMINI_RESEARCH_MODEL=gemini-3.1-flash-lite
CLEARCUT_GEMINI_JUDGE_MODEL=gemini-3.1-pro-preview
CLEARCUT_VERTEX_LOCATION=global
GOOGLE_CLOUD_PROJECT=clearcut-workspace
```

`CLEARCUT_GEMINI_MODEL` may remain temporarily as a backward-compatible detection override.

Every model attempt records requested model, returned model version, response ID, prompt version, rubric or policy version where applicable, input hash, timing, token usage, status, and typed error. Provider failure never silently selects another model.

### Pro judge

The Pro judge runs at two checkpoints:

1. **Detection:** 3.7 Flash output → deterministic schema/category/span checks → Pro judge.
2. **Research:** Parallel snapshots and proposed claims → deterministic provenance/admission gates → Pro judge.

The judge evaluates the applicable subset of the ten protected dimensions: detection recall, grounding, provenance, authority/freshness, conflict identification, uncertainty, rewrite usefulness, rescan correctness, legal boundary, and tool efficiency.

A failed judge verdict may produce one bounded repair pass. Detection repair returns the judge critique to 3.7 Flash. Research repair may revise query wording or claim wording, but it cannot invent a source or bypass admission gates. A second failure creates visible human-review work. There is no unbounded model loop.

Judge output is an immutable advisory `EvaluationResult`. It cannot:

- mark an item legally cleared;
- change protected categories, permissions, safety rules, retention, or legal-boundary text;
- admit a claim without an immutable cited Parallel snapshot;
- override scope, excerpt, authority, or Search-before-Extract gates;
- approve its own escalation without deterministic validation;
- replace accountable human review.

### Parallel capabilities

| Capability | Decision |
| --- | --- |
| Search | Required first provider operation for every item research run |
| Extract | Optional enrichment of at most three URLs returned by the same successful Search run |
| Monitor | Deferred, owner-gated production feature; a signal must trigger fresh Search/Extract before evidence changes |
| Task | Excluded because it overlaps ClearCut orchestration and weakens bounded reproducibility |
| FindAll | Excluded because dataset construction is outside item-level research |
| Responses | Excluded because conversational state is unnecessary and less reproducible |
| Interactions | Excluded because opaque multi-step website state is unnecessary |
| Deep Research | Excluded because it is too broad, slow, and difficult to bind to the item-level evidence contract |

The research sequence is:

1. Flash-Lite proposes one objective and two or three queries.
2. Deterministic rules validate query count, length, scope, and prohibited language.
3. ClearCut persists the run, exact queries, and Search provider attempt before the call.
4. Parallel Search runs once with bounded character limits.
5. ClearCut persists normalized attributable Search snapshots, warnings, usage, authentic provider IDs, and empty/failure outcomes.
6. Only successful same-run Search URLs are eligible for Extract; at most three canonical HTTPS targets are selected.
7. ClearCut persists each Extract outcome as a new immutable snapshot linked to its authorizing Search result.
8. Deterministic admission rules may persist cited evidence claims.
9. Empty results, failures, inaccessible sources, or incomplete provenance create zero claims and leave the item unresolved.

### Local job execution

Local testing uses FastAPI background tasks and exactly one Uvicorn worker:

1. Authenticate and authorize organization/project/target scope.
2. In one transaction, insert or reuse an idempotent queued job and insert the immutable human-trigger audit event.
3. Commit before dispatch.
4. Schedule the background application service.
5. In a short transaction, claim the job and mark it running.
6. Load scoped inputs, then call providers outside any database transaction.
7. In a new transaction, persist normalized outputs, attempts, snapshots/evaluations, and terminal status.
8. The web client polls scoped job status and refreshes affected resources.

Local background tasks are explicitly non-durable. Startup reconciliation marks stale running jobs interrupted/manual-retry; it never claims they succeeded. Retry creates a linked attempt while preserving prior history.

### Production dispatch

Cloud Tasks dispatches user-triggered jobs to a private authenticated Cloud Run endpoint. Cloud Scheduler does not act as the user queue; it triggers recurring monitoring, outbox reconciliation, and expired-lease recovery. Cloud Run Jobs remain optional for bounded administrative batch work.

Both dispatch modes call the same application service:

```text
FastAPI BackgroundTasks (local) ─┐
                                 ├──> job application service
Cloud Tasks handler (production) ┘
```

Production enqueue atomically writes job, human-trigger audit event, and outbox event. An outbox dispatcher creates the Cloud Task after commit. Database idempotency and leases make duplicate delivery safe.

## Canonical Persistence

Alembic is the only schema authority. Runtime bootstrap must stop creating reduced competing table definitions.

The implementation needs repository-backed records for:

- jobs, attempts, leases, results, errors, idempotency, and correlation;
- script import artifacts, warnings, immutable versions, elements, and hashes;
- clearance candidates/items with spans, rationale, uncertainty, model/input provenance, and script version;
- research runs, exact queries, provider attempts, Search authorization, snapshots, and claims;
- deterministic gate results and Pro judge evaluations;
- protected policy/prompt/rubric/model bindings;
- authoritative audit events and redacted receipt projections;
- report snapshots, releases, artifacts, and export history.

Database constraints must enforce tenant ownership and cross-record provenance. Application-only dictionary checks are insufficient.

## Browser Journey

The implemented journey follows the mock’s interaction vocabulary without fabricated fallback data:

1. Sign up with local email/password.
2. Receive a valid same-origin local session.
3. Create an organization.
4. Describe and create a project.
5. Upload or paste an original Fountain screenplay.
6. Parse it and review actual warnings.
7. Commit immutable script version 1.
8. View the persisted screenplay rather than hard-coded scenes.
9. Trigger detection and observe queued → running → succeeded/failed.
10. Review 3.7 Flash candidates and the Pro judge evaluation.
11. Trigger research for an item.
12. Observe Flash-Lite planning, Parallel Search, and bounded Extract attempts.
13. Review immutable snapshots, cited claims, conflicts, and unresolved states.
14. Open AI Trust to inspect real gate and judge bindings.
15. Open Records to inspect activity, runs/tools, evaluations, policies, and operations.

The original test screenplay will use valid Fountain syntax, six to eight scenes, original narrative/dialogue, and realistic references across the protected categories. It enters through the real import path, never direct fixture insertion.

## AI Trust and Records

### Canonical API contract boundary

The canonical OpenAPI contract is the stable browser boundary and uses explicit camelCase `operationId` values and path parameters. FastAPI routes must declare the same IDs and templates; generated callers pass path values under `params` and read successful envelope payloads directly from `result.value`. Successful envelope metadata remains available as `result.meta` so cursor-based Records views do not lose pagination state.

Task 2 registers the complete vertical-slice operation surface before later application services are implemented. An operation without its authoritative repository/service returns the standard error envelope with HTTP 503, code `capability_unavailable`, and `retryable: false`. It must not return demo rows, default scores, synthetic receipts, successful empty jobs, or any other placeholder success. Later tasks replace these truthful boundary handlers without changing generated client signatures.

The canonical vertical-slice operations are:

- Identity and entry: `registerUser`, `createSession`, `getSessionContext`, `deleteCurrentSession`, `listOrganizations`, `createOrganization`, `resolveOrganizationEntry`, `listProjects`, `createProject`, and `getProject`.
- Script lifecycle: `getProjectScript`, `createUploadCapability`, `finalizeImportArtifact`, `createPasteImport`, `parseImportArtifact`, `acceptParseWarnings`, `commitScriptVersion`, `listProjectVersions`, `getProjectVersion`, `startDetection`, and `startResearch`.
- Jobs: project-scoped `listJobs`, `getJob`, `retryJob`, and `cancelJob`.
- Trust: project-scoped `listTrustEvaluations` and `getTrustEvaluation`; run/job filters are query parameters rather than alternate route shapes.
- Records: organization-scoped `listRecords` with a required `view` enum (`activity`, `runsAndTools`, `evaluations`, `policies`, `operations`), `getRecord`, and `getProviderAttempt`.
- Reports: `previewReport`, `generateReportSnapshot`, `releaseReport`, `listReportHistory`, and `getReportDownloadMetadata`.

Resource templates consistently use `/api/v1/organizations/{orgId}/projects/{projectId}`. Job and evaluation resources remain project-scoped. Records remain organization-scoped because they can aggregate authorized projects, while each query still enforces organization ownership. Report release is `POST .../report-snapshots/{snapshotId}:release`; download metadata is `GET .../report-releases/{releaseId}/artifact-metadata` and never exposes an artifact or signed URL without Task 12 authorization.

### AI Trust

The Trust route reads persisted evaluations; it has no default scores. It displays:

- overall score and weakest dimension;
- deterministic gate pass/warn/fail states;
- ten-dimension Pro verdicts where applicable;
- exact rubric, prompt, policy, model/version, timing, and cost bindings;
- learning candidates only when they exist in the governed candidate lifecycle.

Protected configurations remain human-only. Automated learning may propose only allowed query/prompt/preference refinements through candidate → shadow/canary → promote/rollback. Every governed transition writes an authoritative audit event in the same transaction.

### Records

Records implements the five mock views against authoritative data:

1. **Activity:** immutable accountable actions and redacted receipts.
2. **Runs & tools:** jobs, research runs, provider attempts, redacted inputs/outputs, duration, usage, cost, status, and visible exceptions.
3. **Evaluations:** deterministic gates, judge dimensions, exact version bindings, and learning impact.
4. **Policies:** versioned organization-scoped configurations and human change authority.
5. **Operations:** retryable failures, recovered operations, manual-review requirements, retry/cancel actions, and attempt history.

Raw screenplay text, complete source bodies, credentials, signed URLs, and hidden model reasoning never appear in Records. Attributable excerpts and hashes remain available where required for evidence review.

### Reports and receipts

Report generation and release are separate governed actions. Each commits its domain mutation and authoritative audit event atomically. Release also creates the release record and redacted receipt projection. The binding manifest includes script version/hash, item and evidence counts, unresolved appendix, policy/prompt/rubric/model versions, judge summary, actor, timestamps, and content hash. The UI never reports release success after a failed API operation.

## Foundation Repairs

Before provider execution:

1. Reconcile OpenAPI, mounted FastAPI operation IDs, generated clients, path parameters, and response envelope behavior.
2. Make Alembic authoritative and reconcile incompatible job/research/audit/report schemas.
3. Add a real signup route and registration client operation.
4. Use a valid non-`__Host` local cookie; reserve `__Host-...; Secure` for HTTPS production.
5. Make demo seeding optional and idempotent rather than truncating credentials on startup.
6. Persist upload and paste artifacts.
7. Implement parse, warning acceptance, and version commit operations.
8. Remove hard-coded screenplay, clearance, trust, receipt, and success fallbacks.
9. Add scoped job get/list/retry/cancel operations.
10. Add repositories and read APIs before rendering Trust and Records dashboards.

## Error Handling

Provider ports return typed results or typed errors. Retryable, rate-limited, authentication, permanent, malformed-output, and policy-rejected failures remain distinct. No provider call occurs inside a database transaction. No partial output is presented as completed work. Zero evidence is unresolved. Cross-tenant references fail closed.

Local process interruption is visible. Production duplicate delivery is idempotent. Report and governed-action failures roll back both domain state and audit state.

## Verification

Implementation follows test-driven development:

1. Clean-migration PostgreSQL schema and enqueue tests.
2. Signup/session/cookie and tenant-isolation tests.
3. Upload/paste/parse/warning/commit tests.
4. Job status, idempotency, retry, cancel, interruption, and dispatch tests.
5. Model-role and judge-boundary tests for all three Gemini IDs.
6. Search-before-Extract, same-run URL authorization, typed failure, zero-evidence, and provenance tests.
7. Evaluation, authoritative audit, receipt, and report transaction tests.
8. Sanitized adapter contract tests.
9. Explicitly gated live Vertex and Parallel smoke tests.
10. Browser test: signup → project → import → detection → research → Trust → Records.
11. Full contract drift, generated client, foundation, no-legacy, API, web build, and browser gates.

## Acceptance Criteria

The slice is complete only when:

- a new browser user can sign up and remain authenticated;
- the imported original screenplay is read back from persisted version data;
- no hard-coded fallback disguises an API failure;
- detection runs 3.7 Flash, persists candidates, and persists a bounded Pro evaluation;
- research uses Flash-Lite planning, Parallel Search, and only Search-authorized bounded Extract;
- every claim cites an immutable attributable snapshot;
- jobs expose truthful progress, failure, retry, and attempt history;
- Trust displays real evaluation bindings;
- Records displays real activity, runs/tools, evaluations, policies, and operations;
- provider failure or zero results never creates fabricated evidence or clearance;
- local execution is explicitly single-worker/non-durable, while production semantics are Cloud Tasks plus database idempotency and leases.

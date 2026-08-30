# ClearCut Planning Baseline Design

**Status:** Approved  
**Date:** 2026-08-19  
**Purpose:** Define the authoritative product, architecture, governance, evaluation, and execution design for a standalone ClearCut repository before implementation begins.

## 1. Product decision

ClearCut is a screenplay pre-clearance evidence workspace for producers, screenwriters, and clearance teams. It detects potentially sensitive material, researches current evidence through Parallel, preserves provenance and uncertainty, coordinates human review, re-evaluates revisions, monitors source changes, and exports a reproducible evidence dossier.

ClearCut does not provide legal advice or issue legal-clearance certificates. It supports evidence gathering and review while leaving clearance decisions with qualified humans.

The submission targets the Parallel track of Agentic Cinema. The official submission deadline is September 9, 2026 at 2:00 PM Pacific time.

## 2. Approved scope

All 47 named feature-ledger rows are mandatory submission commitments. Implementation milestones control order, but no row is marked Defer or Remove.

The judged product includes:

- Paste, Fountain, PDF, and Final Draft XML (`.fdx`) ingestion.
- Structural screenplay parsing with stable element and span identities.
- Detection across all ten documented clearance categories.
- Live Parallel research with source-backed claims, confidence, conflicts, and provenance.
- An annotated screenplay workspace with evidence review.
- Organizations, invitations, memberships, project membership, and administration.
- Fixed Owner, Admin, Editor, Reviewer, and Viewer roles.
- Assignments, comments, due dates, and notifications.
- Human-governed evidence decisions, rewrites, specialist referrals, dispositions, and exports.
- Immutable script versions and selective affected-item re-scan.
- Manual, daily, and weekly source-change monitoring.
- Judge-driven evaluation and bounded automatic learning.
- Reproducible, version-bound dossier generation and export.
- An original entrant-owned demonstration screenplay.

## 3. Repository and authority

ClearCut becomes a standalone repository at:

```text
/Users/captjay98/projects/clearcut
```

The existing `/Users/captjay98/projects/hackathons/clearcut` documents remain migration source material until the standalone baseline is complete. The parent portfolio directory is not modified as part of this design-document step.

### 3.1 Planned repository structure

```text
clearcut/
├── README.md
├── product-plan.md
├── feature-ledger.md
├── submission-strategy.md
├── contracts/
│   ├── README.md
│   ├── openapi.yaml
│   └── schemas/
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DATA_MODEL.md
│   ├── WORKFLOWS.md
│   ├── APPROVAL_POLICY.md
│   ├── EVIDENCE_POLICY.md
│   ├── API_CONTRACT.md
│   ├── EVENTS.md
│   ├── SECURITY_AND_PRIVACY.md
│   ├── IMPLEMENTATION_PLAN.md
│   ├── SESSION_HANDOFF.md
│   ├── adr/
│   └── plans/
│       ├── active/
│       │   ├── README.md
│       │   ├── FEATURE_COVERAGE.md
│       │   └── 01–08 numbered plans
│       └── archive/
└── demo/
    ├── scripts/
    ├── fixtures/
    └── expected-results/
```

### 3.2 Authority order

When documents disagree, authority is:

1. Official competition rules.
2. Accepted ADRs, versioned contracts, approved policies, and architecture invariants.
3. The canonical 47-feature ledger.
4. The broad product plan.
5. The master implementation roadmap.
6. Numbered active plans and the feature-coverage matrix.
7. Submission and demonstration material.

Implementation stops when authorities conflict. Every feature-ledger row must have one owning plan and objective acceptance evidence.

Agent configuration and CI automation are added only after real manifests, commands, and verification procedures exist.

## 4. Application architecture

ClearCut uses a monorepo with three deployable applications.

```text
apps/
├── site/          # Astro marketing and competition-facing pages
└── web/           # TanStack Start authenticated workspace

services/
└── api/           # FastAPI modular monolith and Google ADK runtime

packages/
├── contracts/     # Generated TypeScript and Python contract clients
├── design-system/ # Shared visual primitives
└── config/        # Shared build, lint, and type configuration

infra/
└── gcp/           # Reproducible Google Cloud infrastructure
```

### 4.1 Backend modules

The FastAPI modular monolith contains bounded modules for:

- Identity, organizations, invitations, membership, and RBAC.
- Projects, scripts, versions, parsing, and normalized elements.
- Clearance-item detection and classification.
- Parallel research, evidence, provenance, authority, and conflicts.
- Rewrites, affected-item re-scan, and dispositions.
- Assignments, comments, due dates, and notifications.
- Monitoring policies, runs, and review items.
- Governed decisions and immutable audit records.
- Judge evaluations, learning proposals, promotion, and rollback.
- Dossier generation and export.

The product begins as a modular monolith. It does not introduce independent domain microservices during the hackathon.

### 4.2 Hosted topology

```text
Astro site ───────────────┐
TanStack workspace ───────┼─→ FastAPI on Cloud Run
                          │      ├─ Cloud SQL PostgreSQL
                          │      ├─ Cloud Storage
                          │      ├─ Gemini + Google ADK
                          │      ├─ Parallel Search + bounded Extract
                          │      ├─ conditional Parallel Monitor event stream
                          │      ├─ Cloud Tasks
                          │      ├─ Cloud Scheduler
                          │      ├─ Configured identity adapter (local or Firebase)
                          │      └─ Secret Manager
Cloud Scheduler ──────────┘
```

Detection, research, re-scan, monitoring, evaluation, learning-candidate testing, and export execute asynchronously through durable jobs. The same backend image may expose private task handlers while preserving module boundaries.

The API is OpenAPI-first. Generated TypeScript and Python clients are checked for drift.

## 5. Provider boundaries

External systems sit behind narrow typed ports:

- `ObjectStorage`: GCS initially; R2 after a clean post-hackathon launch.
- `WebSearchPort`: mandatory Parallel Search.
- `UrlExtractPort`: bounded Parallel Extract on Search-authorized URLs.
- `WebMonitorPort`: conditional Parallel Monitor `event_stream`; scheduled Search/Extract remains the stable watch path.
- `ModelProvider`: Gemini through Google ADK.
- `IdentityProvider`: local PostgreSQL credentials by default or Firebase/Identity Platform, selected once per deployment behind a ClearCut-owned adapter.
- `TaskDispatcher`: Cloud Tasks.
- `NotificationProvider`: deployment-selected none, SMTP, Resend, or ZeptoMail adapter plus in-app delivery.

Local authentication is the default OSS mode. A deployment may instead configure Firebase/Identity Platform, but it does not mix providers or link accounts in the initial release. Both modes resolve an internal `User` and issue the same server-side opaque, revocable ClearCut application session. The public workspace/API boundary is same-origin; a host-only `__Host-` Secure HttpOnly SameSite cookie carries the session, while state-changing requests additionally require a session-bound CSRF token and validated Origin. Browser storage never holds a long-lived API bearer token.

The object-storage port supports:

```text
put_object
get_object
head_object
delete_object
create_upload_url
create_download_url
```

Provider methods return typed results or typed errors, not ambiguous booleans, URLs, or `None` values.

The active storage implementation is selected through configuration:

```env
OBJECT_STORAGE_PROVIDER=gcs
```

A later clean production launch may use:

```env
OBJECT_STORAGE_PROVIDER=r2
```

Hackathon GCS data is disposable. The post-hackathon R2 launch starts with a fresh production database and bucket, so the initial plan does not include object migration or dual-read logic.

Uploads use expiring one-time capabilities bound to organization, project, actor, object key, maximum size, content type, content hash, and nonce.

## 6. Data model

### 6.1 Identity and collaboration

- `User`
- provider identity/local credential record
- opaque revocable `Session`
- `Organization`
- `Membership`
- `Invitation`
- `Project`
- `ProjectMember`
- `Assignment`
- `Comment` — per-ClearanceItem, unthreaded, timestamped, actor-identified.
- `Notification`

### 6.2 Script ingestion

- `Script`
- `ScriptVersion`
- `ImportArtifact`
- `ScriptElement`
- `ElementSpan`
- `ParseRun`

Every import creates an immutable version. Normalized elements preserve scenes, action, characters, dialogue, parentheticals, transitions, and source locations.

### 6.3 Detection and evidence

- `AnalysisRun`
- `DetectionRun`
- `ClearanceItem`
- `ResearchRun`
- `ResearchQuery`
- `EvidenceClaim`
- `SourceSnapshot`
- `EvidenceConflict`
- `ConfidenceAssessment`

Every claim links to its Parallel query, source metadata, retrieval time, excerpt, script version, clearance item, agent run, prompt version, and policy version.

### 6.4 Decisions and lifecycle

- `RewriteProposal`
- `EvidenceDecision`
- `DispositionDecision`
- `SpecialistReferral`
- `MonitoringPolicy`
- `MonitoringRun`
- `ReviewItem`
- `DossierExport`
- `AuditEvent` — authoritative immutable record for a consequential action.
- Receipt — redacted human-readable projection linked to authoritative events, never an independent source of truth.

### 6.5 Agent, judge, and learning records

- `AgentRun`
- `AgentToolCall`
- `AgentEvaluation`
- `JudgeVerdict`
- `LearningProposal`
- `LearningCandidate`
- `CanaryRun`
- `PromptVersion`
- `PolicyVersion`
- `RubricVersion`

Runs record model, inputs, output, trace, parent run, policy snapshot, prompt version, tool calls, tokens, latency, estimated cost, idempotency key, evaluation results, and terminal status.

## 7. Golden workflow

```text
Import script
→ parse and normalize
→ create immutable version
→ detect items across all ten categories
→ plan and execute Parallel searches
→ normalize claims, sources, conflicts, and confidence
→ annotate screenplay
→ assign and discuss items
→ accept or reject evidence
→ propose and approve rewrite
→ create new script version
→ diff stable element identifiers
→ re-scan only affected items
→ monitor sources manually, daily, or weekly
→ create review items for meaningful changes
→ approve final dispositions
→ generate a version-bound dossier
```

A rewrite never mutates its source version. Superseded evidence remains historical and linked to the new evaluation.

Monitoring cannot silently alter evidence decisions or dispositions. It creates a new run and review item when availability, authority, conflict, or confidence changes materially.

Exports are reproducible snapshots tied to exact script, evidence, decision, rubric, and policy versions.

## 8. Collaboration and authorization

ClearCut uses fixed roles:

- **Owner:** organization lifecycle, ownership, protected configuration, and all governed review/report actions.
- **Admin:** membership, projects, providers, operational settings, and all governed review/report actions; protected configuration is read-only.
- **Editor:** script, research, assignment, comments, and rewrite proposals.
- **Reviewer:** evidence decisions, referrals, dispositions, rewrite approval, export review, and governed report generation/release.
- **Viewer:** read-only access to authorized projects and released reports.

Authorization is enforced in backend repositories and services, not only in routes or UI controls. Organization and project scope are mandatory query inputs.

The configured identity adapter establishes identity: local PostgreSQL authentication is the default OSS mode, and Firebase/Identity Platform is an optional managed mode. One provider is selected per deployment. PostgreSQL remains authoritative for internal users, application sessions, organizations, invitations, memberships, roles, and permissions.

Organization membership deactivation immediately removes that organization's authorization without terminating identity sessions still needed for unrelated organizations. Account suspension and recovery can revoke all application sessions in either provider mode.

## 9. Governed actions

Tools are classified as:

- **Read:** retrieve authorized state or external evidence.
- **Draft:** propose an item, rewrite, query, assignment, or decision.
- **Governed write:** create an externally meaningful or decision-bearing state change.

Detection, research, monitoring, assignments, notifications, and draft generation may run automatically when policy allows.

Explicit human action is required to:

- Accept or reject evidence.
- Accept a rewrite.
- Refer an item to a specialist — a status change and notification, not a separate specialist-facing portal.
- Set final disposition.
- Generate or release a dossier export.

Owner, Admin, and Reviewer may trigger governed report generation/release only for projects they are authorized to access and only when the active sign-off policy permits it. Protected organization configuration remains Owner-only.

The server loads role and policy state. The model and client cannot supply or override authorization decisions.

Critical decisions and their audit events commit in the same database transaction. Best-effort audit logging is reserved for noncritical telemetry.

## 10. Durable execution and error handling

Asynchronous runs use this lifecycle:

```text
queued → claimed → running → succeeded
                           ↘ retry_wait → running
                           ↘ failed → manual_retry
                           ↘ cancelled
```

The originating transaction writes the run and outbox record together. Cloud Tasks dispatches the work. Leases, unique idempotency keys, retry counters, and reconciliation prevent duplicate or stranded execution.

Provider results distinguish:

- Accepted success.
- Retryable failure.
- Permanent failure.
- Rate limiting.
- Authentication or configuration failure.
- Invalid response or schema.

Retries use bounded exponential backoff with jitter. Permanent failures and exhausted retries create visible review items. ClearCut never converts a failed research run into invented fallback evidence.

The API uses a closed machine-readable error envelope for validation, authentication, authorization, conflict, rate limit, provider, model, rejected output, unavailable service, and internal failures.

## 11. Evidence and provenance policy

Evidence preserves:

- Source URL and title.
- Publisher and authority classification.
- Retrieval time.
- Publication or update time when available.
- Query and research-run identity.
- Short attributable excerpt.
- Source snapshot metadata.
- Confidence and uncertainty.
- Conflicts and missing evidence.
- Script, item, prompt, model, and policy versions.

Fetched content and screenplay text are untrusted data, never instructions. Source content cannot change agent policy or tool permissions.

Evidence quality does not imply provider, rights-holder, or legal acceptance. ClearCut presents sourced findings and unresolved risk without claiming legal clearance.

## 12. Judge and bounded learning

Each agent run passes through:

```text
Agent run
→ deterministic policy evaluation
→ independent LLM judge
→ persisted verdict and scores
→ learning proposal
→ offline regression evaluation
→ shadow run
→ bounded canary
→ promote or roll back
```

The judge uses a separate prompt and preferably a separate configured model alias. It scores:

- Detection recall and category correctness.
- Claim-to-source grounding.
- Citation and provenance completeness.
- Source authority and freshness.
- Conflict identification.
- Appropriate uncertainty.
- Rewrite usefulness.
- Affected-item re-scan correctness.
- Legal-boundary compliance.
- Tool efficiency, latency, and cost.

Low-scoring runs may create learning proposals for query phrasing, retrieval examples, category examples, prompt refinements, or organization-scoped preferences.

### 12.1 Automatic-promotion boundary

Low-risk learning candidates may auto-promote only when they:

1. Pass the complete deterministic corpus.
2. Introduce no new blocker or warning regression.
3. Improve the target judge score by the configured threshold.
4. Stay within tool-call, latency, and cost budgets.
5. Pass shadow evaluation.
6. Pass a bounded canary.
7. Retain an automatic rollback path.

The following never auto-promote:

- Tool permissions.
- Role permissions.
- Approval policy.
- Evidence schemas.
- Source-authority tiers.
- Deterministic blocking rules.
- Retention and privacy rules.
- Legal-boundary language.

Organization-specific learning remains tenant-scoped. Private screenplay content is not used for global learning without explicit consent and redaction.

## 13. Security and privacy

Required controls include:

- Tenant-scoped repositories and cross-tenant isolation tests.
- Short-lived signed object URLs.
- One-time upload capabilities whose finalized object generation is pinned and whose stored bytes are server-hashed.
- MIME, magic-byte, extension, and size validation.
- FDX parsing with DTD, entities, XInclude, parser networking, and schema retrieval disabled plus structural limits.
- Isolated non-networked PDF parsing with resource caps and no execution of embedded actions, scripts, links, forms, or attachments.
- SSRF protection for any server-side source retrieval.
- Prompt-injection defenses for scripts and fetched sources.
- Encryption in transit and at rest.
- Secret Manager for provider credentials.
- Core project evidence has no automatic age-based deletion; an Owner schedules whole-project or whole-organization deletion with a 30-day reversible grace period.
- Separate approved retention periods apply only to minimized operational telemetry and cannot remove the only copy of evidence provenance or governed audit.
- Final purge removes sensitive files, payloads, and blobs while retaining only minimized tombstone/audit metadata and explicitly marking lost reproducibility.
- Immutable governed-decision audit events.
- Redaction of sensitive content from logs, traces, and evaluation artifacts.

## 14. Testing and evaluation

### 14.1 Deterministic tests

- Four parser suites.
- Stable element and span identity across revisions.
- Selective affected-item re-scan.
- Ten category schemas and representative cases.
- Evidence, source, conflict, and confidence normalization.
- Role and tenant isolation.
- Invitation and membership lifecycle.
- Approval and disposition state machines.
- Monitoring cadence and deduplication.
- Job idempotency, retries, leases, and reconciliation.
- Dossier reproducibility.
- Shared provider contract tests for GCS and R2.

### 14.2 Evaluation corpus

The corpus includes:

- Positive and negative cases for all ten categories.
- Ambiguous and overlapping items.
- Conflicting, missing, stale, and low-authority sources.
- Script and source prompt-injection attempts.
- Unsupported legal certainty.
- Safe and unsafe rewrite suggestions.
- Narrow and broad revision impact.
- Monitoring changes that should and should not open review.

Baselines track blocker and warning sets, rubric scores, latency, tool count, token usage, and cost. CI reports false positives, false negatives, severity drift, and score regressions.

### 14.3 End-to-end validation

Playwright covers organization creation, invitation, role enforcement, all import paths, detection, Parallel research, evidence review, rewrite, selective re-scan, monitoring, and export. Accessibility checks cover keyboard navigation, focus management, dialogs, responsive layouts, and landmarks.

Security tests cover role escalation, cross-tenant access, upload replay, malformed files, malicious XML/PDF, source prompt injection, SSRF boundaries, expired URLs, secret leakage, and audit completeness.

## 15. Observability

OpenTelemetry links HTTP requests, background jobs, agent runs, Parallel queries, tool calls, judge evaluations, learning candidates, and exports.

Operational metrics include:

- Run success and terminal-state rates.
- Evidence coverage and citation completeness.
- Blocked-output and warning rates.
- Provider failures and retries.
- Queue and execution latency.
- Tool calls, model tokens, and estimated cost.
- Monitoring changes and review conversion.
- Judge score trends.
- Canary promotion and rollback outcomes.

Logs and traces must redact screenplay text, evidence excerpts, credentials, invitation tokens, and other sensitive content.

## 16. Implementation roadmap

### Plan 01 — Repository, toolchain, and contracts

Initialize the standalone monorepo, pin toolchains, define OpenAPI and schemas, establish domain values and provider ports, and add truthful CI gates.

**Exit:** generated TypeScript and Python clients agree with versioned contracts.

### Plan 02 — Identity, collaboration, storage, and ingestion

Implement the local PostgreSQL identity adapter and optional Firebase/Identity Platform adapter, same-origin opaque application sessions and CSRF defense, organizations, five-state invitations, fixed roles, project membership, configurable email delivery, GCS, signed uploads, all four parser paths, immutable script versions, and normalized elements.

**Exit:** an authorized organization member imports every format into an isolated project.

### Plan 03 — Detection, Parallel research, and evaluation spine

Implement all ten categories, ADK orchestration, structured outputs, mandatory Parallel Search, bounded Extract, evidence records, agent/tool ledgers, deterministic gates, and the first judge. Keep Task, FindAll, Responses/Chat, Interactions, Deep Research, snapshot Monitor, alternate providers, and fallbacks out of the contest runtime.

**Exit:** one imported script produces traceable, evaluated evidence cards with live Parallel provenance.

### Plan 04 — Annotated workspace

Implement the TanStack shell, screenplay annotation, evidence cards, source details, run progress, retry and failure UX, trace views, Astro marketing site, live text search, worklist sort (severity, confidence, scene, due), grouping (scene, category, severity, status), deep-link filtering, and bulk operations (bulk assign, bulk clear).

**Exit:** the evidence loop is usable on desktop and mobile web.

### Plan 05 — Collaboration and governed decisions

Implement assignments, comments, due dates, notifications, evidence decisions, referrals, dispositions, role-aware controls, and transactional audit.

**Exit:** a multi-user review completes without bypassing policy.

### Plan 06 — Rewrites, revisions, re-scan, and dossiers

Implement rewrite approval, new script versions, stable-element diffing, selective re-scan, evidence lineage, and version-bound export.

**Exit:** the original demo script completes the revision-to-export lifecycle.

### Plan 07 — Monitoring and bounded learning

Implement configurable monitoring, change review, judge history, learning proposals, regression evaluation, shadow runs, canaries, promotion, rollback, protected human gates, Owner-governed protected configuration (rubric, prompt versions, sign-off policy), and Admin-manageable operational settings.

**Exit:** ClearCut safely improves an allowlisted low-risk behavior without weakening any baseline. An Owner can version, validate, and activate protected configuration with reauthentication, confirmation, rationale, and audit; an Admin can inspect it and manage only operational settings.

### Plan 08 — Production, hardening, and submission

Provision Google Cloud services, harden security and privacy, establish recovery and observability, finalize the original demo, run hosted verification, and prepare all submission evidence.

**Exit:** all 47 rows have passing acceptance evidence and a clean environment reproduces the submission.

Review gates occur after Plans 01, 03, 05, 07, and 08. A dependent plan does not start until predecessor exit criteria and coverage evidence pass.

## 17. Lessons adopted from Farmhand AI

ClearCut adopts these proven patterns from Farmhand AI without copying its code or domain behavior:

- First-class agent runs, tool calls, evaluations, traces, model metadata, and cost records.
- Transactional outbox execution for durable asynchronous work.
- Deterministic `block`, `warn`, and `info` gates before output acceptance.
- Golden-scenario regression reports.
- Server-owned autonomy decisions and action classification.
- Scoped, expiring upload capabilities.
- Closed machine-readable errors.
- Governed learning proposals connected to evaluation evidence.

ClearCut deliberately diverges where Farmhand patterns are unsuitable:

- Provider calls return typed results and errors rather than ambiguous booleans or `None`.
- Critical decision audits are transactional, not best-effort.
- Private scripts cannot become global learning data by default.
- The initial architecture remains a bounded modular monolith rather than reproducing Farmhand’s domain breadth.

## 18. Baseline completion criteria

The planning baseline is complete when:

- The four migrated root documents agree on the 47-feature count, scope, deadline, inputs, and golden path.
- Architecture, data model, workflows, approval, evidence, security, API, and event documents are accepted.
- ADRs record every consequential decision in this design.
- OpenAPI and JSON Schemas define stable v1 seams.
- Every feature row maps to one plan and acceptance artifact.
- Plans 01–08 have dependency, scope, tasks, verification, invariants, and exit criteria.
- Session handoff points to the exact next gated action.
- No tool command is documented before the corresponding toolchain exists.

This design authorizes planning-document creation. It does not authorize application implementation or a Git commit without a separate explicit instruction.

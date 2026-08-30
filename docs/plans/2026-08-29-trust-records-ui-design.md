# Trust & Records UI Design

**Date:** 2026-08-29
**Status:** Approved consolidation
**Surfaces:** `#trust`, `#records`

## Purpose

This design records the production semantics for AI Trust and Records that were approved during the surface review but were previously represented only by the mock and its verification memo. It defines what each surface may claim, which records are authoritative, how organization and project scope is enforced, who may act, and how sensitive run data is redacted.

The mock at `misc/clearcut-flow/` remains the visual and interaction source of truth. This document corrects production semantics without authorizing mock changes or treating simulated receipts, scores, or provider calls as production records.

## Approved decisions

1. AI Trust is an organization-owned read surface. Every active organization member may inspect the current trust posture; only an Owner may manually start a canary, promote, pause, or roll back an organization-scoped learning candidate.
2. Eligible low-risk candidates may still auto-promote through the approved regression → shadow → bounded canary → promotion path. Manual Owner controls are overrides, not a way to bypass gates.
3. Permissions, approval policy, category definitions, source-authority tiers, evidence requirements, deterministic blockers, retention/privacy settings, and legal-boundary language are never learning-candidate outputs and never auto-promote.
4. The judge evaluates quality; it does not establish legal safety, approve evidence, or issue clearance. Deterministic blockers and warnings remain separate from judge scores.
5. `AuditEvent` is the authoritative immutable record of a consequential domain action. A Receipt is a human-readable, redacted projection that links to one or more authoritative events; it is not a second source of truth.
6. Durable runs, tool calls, evaluations, learning records, provider attempts, and security events remain distinct from governed-action audit events even when Records presents them in one chronology.
7. Organization records require active authenticated `org_id` scope. Project records additionally require `project_id` and current project authorization. Organization scope is never a shortcut around project authorization.
8. Records never exposes secrets, live tokens, credentials, unrestricted provider payloads, hidden model reasoning, or raw screenplay/source bodies. It shows redacted arguments and result summaries plus authorized links to bounded source snapshots.
9. An `EvidenceClaim` is valid only when it cites a Parallel `SourceSnapshot` with URL, retrieval time, attributable excerpt, publisher/authority classification, stance, query/run identity, and provenance. Zero evidence remains unresolved.
10. Trust and Records use URL-addressable views, filters, and identifiers so Settings, reports, notifications, incidents, and support workflows can deep-link without creating another surface.
11. Governed report generation/release is available to Owner, Admin, and Reviewer, subject to project authorization, accountable human action, required sign-off policy, and a same-transaction audit event.
12. Core evidence is not deleted by age. Owner-scheduled project or organization deletion uses a 30-day grace period; final purge removes sensitive bodies and blobs while retaining only the minimum referential tombstone and audit metadata required to preserve historical integrity.

## Record taxonomy and authority

| Record | Ownership | Purpose | Authoritative behavior |
|---|---|---|---|
| `AuditEvent` | Organization or project | Consequential human/domain action | Append-only; commits in the same transaction as the action |
| Receipt | Read projection | Human-readable explanation and deep links | Rebuildable from authoritative records; never independently mutated |
| `AnalysisRun`, `DetectionRun`, `ResearchRun`, `MonitoringRun`, `ParseRun` | Project | Durable work lifecycle | Typed terminal states, predecessor links, attempts, idempotency, and timestamps |
| `AgentToolCall` | Project | One bounded tool invocation | Redacted input summary, typed result/error, timing, cost, provider receipt, query identity |
| `SourceSnapshot` | Project | Attributable Parallel retrieval | Immutable provenance, bounded excerpt, retrieval metadata, stance, authority classification |
| `AgentEvaluation` / `JudgeVerdict` | Organization plus referenced project run | Deterministic and model evaluation | Exact run, rubric, prompt, policy, judge, model, and score bindings |
| `LearningProposal` / `LearningCandidate` / `CanaryRun` | Organization | Bounded improvement lifecycle | Allowlisted change class, regression evidence, traffic bound, promoter or automation basis, rollback |
| Provider attempt/event | Organization or project | Operational delivery/retry evidence | Typed result/error and redacted provider receipt; not a governed decision |
| Security event | Organization or account | Authentication, authorization, token, replay, and abuse signal | Restricted visibility, immutable occurrence data, no secret payload |
| `DossierExport` | Project | Reproducible report artifact | Exact script, evidence, decision, prompt, policy, rubric, judge, generator, and artifact hash binding |

A chronology may interleave these records, but labels must identify the record type and authority. “Receipt” is reserved for the readable projection of a consequential action; routine telemetry is not promoted into an audit receipt.

## Scope and visibility matrix

| Viewer | Organization Trust | Organization Records | Authorized project records | Sensitive security/provider detail | Mutating Trust controls |
|---|---|---|---|---|---|
| Owner | Read | Read | Read | Read redacted operational detail | Manual canary/promote/pause/rollback |
| Admin | Read | Read operational and membership history | Read | Read redacted provider detail; security detail only when operationally required | None; controls remain focusable with Owner-only reason |
| Editor | Read | Own membership/account events | Read assigned/authorized project activity and runs | No | None |
| Reviewer | Read | Own membership/account events | Read authorized evidence, decisions, evaluations, and report records | No | None |
| Viewer | Read summary | Own membership/account events | Read authorized project records and released exports | No | None |

Additional rules:

- Cross-tenant, unauthorized-project, and unknown locators return indistinguishable access-safe not-found responses.
- Project names, counts, tool-call totals, source titles, excerpts, report bindings, and activity must be computed only from the authorized project set.
- Actor display follows current privacy policy while preserving immutable actor identity internally. Purged or removed identities render an approved historical label without changing the underlying event.
- Downloading a source body, original script, provider payload, or artifact is a separate authorized operation; visibility of a record row does not grant blob access.
- Tool arguments show typed, redacted fields. Free-form source text, screenplay passages, headers, tokens, signed URLs, and provider credentials are omitted.

## AI Trust

### Purpose and claims

AI Trust explains how ClearCut evaluates its work and how bounded improvements are controlled. It must not imply that a high score means an item is cleared or legally safe.

The summary identifies:

- the selected completed run or organization aggregate and its time range;
- deterministic blocker, warning, and information results;
- the ten judge dimensions and their individual scores;
- score aggregation method and weighting;
- weakest dimensions and unresolved findings;
- exact rubric, judge prompt, policy, model alias/version, and evaluation identity;
- latency, tool count, token usage, and cost when available;
- links to the evaluated run and its redacted Records history.

The headline score is derived from displayed dimensions. If dimensions are equally weighted, it is their arithmetic mean. If a versioned rubric uses weights, the UI names the weighted method and displays the weights. Missing or failed dimensions do not silently become zero or disappear; the evaluation is incomplete.

### Deterministic gates

Deterministic policy evaluation runs before judge acceptance and reports `block`, `warn`, or `info` independently of numeric scores.

- A blocker prevents the affected output from being accepted, promoted, or used to satisfy a governed release requirement.
- A warning remains visible until reviewed or superseded by a later run.
- An information result records useful context without implying approval.
- A high judge score never overrides a deterministic blocker.

The grounding gate rejects any claim lacking its cited Parallel `SourceSnapshot` and complete attributable provenance. Provider failure, no results, or unavailable sources create unresolved review states, never fallback evidence.

### Learning lifecycle

```text
proposal
→ candidate
→ regression_failed | regression_passed
→ shadow
→ bounded_canary
→ promoted
→ paused | rolled_back | superseded
```

Every candidate records:

- the allowlisted change class and bounded diff;
- organization scope and creator;
- baseline and target metrics;
- regression corpus/version and results;
- deterministic gate results;
- shadow and canary traffic bounds;
- latency, quality, cost, and error budgets;
- promotion basis and actor or automated-policy identity;
- prior version and tested rollback path.

Eligible learning changes are limited to query phrasing, retrieval/category examples, prompt refinements, and organization-scoped preferences. Evidence-schema extensions may add optional fields only; they cannot remove or weaken required provenance, uncertainty, conflict, or citation fields.

Owner manual actions require recent reauthentication, explicit typed confirmation, and rationale. They remain idempotent and cannot skip failed prerequisites. Rollback is always available to an Owner and may also trigger automatically when a bounded canary breaches a gate.

### Trust states

- **Loading:** stable score/rubric skeletons and status text.
- **Empty:** no completed evaluation yet, with an explanation and link to eligible runs.
- **Recoverable error:** evaluation projection unavailable, Retry preserves selected filters.
- **Permanent error:** evaluation invalid or missing immutable bindings; names the evaluation ID and explains remediation.
- **Success:** complete gate, score, provenance, and learning state.
- **Not found:** names the requested run/evaluation/candidate locator without revealing unauthorized existence.
- **Stale:** clearly marks that a newer policy, rubric, prompt, or run exists and links to it.

## Records

### Information architecture

Records remains one route and uses URL-addressable views through the existing `TabsBar` vocabulary:

```text
#records?view=activity
#records?view=runs
#records?view=evaluations
#records?view=policies
#records?view=operations
```

Supported filters include organization/project scope, record type, actor, status, time range, provider, run ID, item ID, receipt ID, and correlation ID. Invalid filters are ignored with an accessible explanation; unauthorized values never change the result count or reveal existence.

Deep links use immutable IDs. A record detail opens as a route-addressable detail state or dialog that restores focus and preserves filters when closed.

### Activity

Activity presents governed actions and their Receipts. Each row includes:

- Receipt and authoritative `AuditEvent` identifiers;
- actor, action, scope, and timestamp;
- human-readable effect and rationale summary;
- referenced item, version, policy, report, or deletion request;
- transaction/correlation identity;
- supersession or reversal relationship where applicable.

A reversed decision is not erased. The later event links to the earlier event and explains the effective current state.

### Runs and tools

Run rows expose durable state, predecessor/continuation, attempts, start/end time, counts, cost, and terminal result. Tool-call detail exposes the typed tool name, redacted argument summary, timing, typed result/error, provider receipt identity, and linked query/snapshots.

The UI never renders hidden model reasoning. It may show concise server-produced summaries and the inputs/outputs explicitly approved for audit. A failed call and its retry remain separate attempts; totals are derived from the visible authorized records.

### Evaluations

Evaluation records bind the run to deterministic gates, judge verdict, rubric, prompt, policy, model, token/cost metadata, and candidate impact. Missing bindings are an invalid evaluation, not a partial success.

### Policies

Policy history distinguishes global read-only catalogs from organization-owned versions. It links to Settings for authorized management while preserving activation, supersession, validation, and rollback events.

### Operations

Operations covers provider attempts, durable-job recovery, deletion/purge jobs, email delivery, and restricted security events. Operational recovery actions remain capability-gated, idempotent, and audited. Records does not become a general-purpose log viewer.

### Records states

- **Loading:** stable rows/cards with `aria-busy` and retained filter controls.
- **Empty:** distinguishes no records, no authorized project records, and no filter matches.
- **Recoverable error:** Retry retains scope and filters.
- **Permanent error:** explains unavailable or invalid historical data without inventing reconstruction.
- **Success:** paginated/streamed authorized chronology with stable ordering.
- **Not found:** names the typed immutable locator while keeping unknown and unauthorized responses indistinguishable.
- **Redacted:** identifies which class of field was withheld and why, without revealing its value.

## Retention, deletion, and reproducibility

Core scripts, evidence, decisions, source snapshots, reports, and their audit relationships have no automatic age-based deletion. Operational telemetry may have a separately approved bounded retention schedule, but it cannot be the only copy of evidence provenance or a governed audit event.

During the 30-day deletion grace period, affected records are read-only, new jobs and governed actions are blocked, and signed links are revoked. Restoration writes a new `AuditEvent` and restores access without rewriting history.

Final purge:

- removes original scripts, source bodies beyond permitted minimal excerpts, provider payloads, generated artifacts, and stored blobs;
- removes or irreversibly pseudonymizes personal data not required for the retained audit boundary;
- keeps only minimum identifiers, hashes, timestamps, action type, scope tombstone, and deletion-event linkage needed to prevent broken historical references;
- marks prior report artifacts unavailable rather than claiming they remain reproducible after their required inputs were purged;
- never rewrites a historical event to imply that evidence still exists.

The pre-deletion impact preview must state which reproducibility guarantees will be lost. The Owner may export the retained record before scheduling deletion.

## Accessibility, responsive, and visual requirements

Both surfaces render through the shared `page()` wrapper and preserve the mock’s cards, stat grids, tables, banners, badges, progress patterns, typography, and two-layer navigation.

- Keyboard users can reach every filter, row action, detail, and gated control.
- Focus remains stable during polling and filter updates; dialogs trap and restore focus.
- Score rings and meters have equivalent text, not color-only meaning.
- Status changes use concise live-region announcements.
- Tables become readable cards or controlled horizontal regions on narrow screens; no record value requires horizontal page scrolling.
- Coarse-pointer targets are at least 44px.
- Script and Night shoot themes meet the same contrast and hierarchy from 320 through 1440px.
- Reduced motion is honored.
- Capability-gated controls remain focusable and describe the exact restriction.
- Technical identifiers, timestamps, versions, hashes, cost, and latency use mono styling.

## Required mock-to-production corrections

1. Replace the mock’s flattened `addReceipt()` objects with Receipt projections backed by immutable `AuditEvent`s.
2. Replace broad `settings` gating on learning mutations with Owner-only learning-governance capability and required gates.
3. Replace static latest-run trust data with selectable, immutable evaluation bindings and honest incomplete/stale states.
4. Separate deterministic gate results from judge scores and prevent score-based override.
5. Add URL-addressable Records views, filters, and immutable detail links.
6. Enforce organization/project authorization on every record count, query, detail, and artifact link.
7. Redact tool arguments/results and prevent raw provider payload, screenplay text, source body, credential, token, or signed-URL disclosure.
8. Replace age-based retention display with approved no-age-deletion and Owner-scheduled project/organization deletion semantics.
9. Add complete loading, empty, recoverable/permanent error, success, stale/redacted, and access-safe not-found states.
10. Preserve the existing visual vocabulary, score/rubric presentation, bounded-learning story, failure visibility, and readable chronology.

No mock implementation changes are authorized by this document alone.

## Domain and contract implications

This design establishes the need for, without freezing final names or fields:

- immutable `AuditEvent` plus Receipt projection;
- durable run and attempt records with predecessor and idempotency relationships;
- redacted `AgentToolCall` projection and protected provider-payload storage boundary;
- `AgentEvaluation`, deterministic gate result, `JudgeVerdict`, and exact version bindings;
- learning proposal/candidate/regression/shadow/canary/promotion/rollback records;
- provider operation and restricted security-event records;
- organization/project scope and redaction policy on every query/detail endpoint;
- stable pagination, filters, correlation IDs, and immutable deep-link identifiers;
- deletion tombstones and explicit reproducibility-loss state.

The OpenAPI contract must use typed unions for record kinds and run/provider terminal states. Raw dictionaries, ambiguous booleans, and unrestricted payload fields cannot cross the API boundary.

## Verification expectations

When production targets exist, verify:

- Trust read access for active members and Owner-only manual learning mutations;
- auto-promotion only for allowlisted low-risk candidates after every required gate;
- protected-rule mutation and gate-bypass attempts fail closed;
- score aggregation, incomplete dimensions, blocker precedence, stale bindings, and legal-boundary wording;
- `AuditEvent`/Receipt consistency and same-transaction governed actions;
- organization/project authorization on lists, counts, filters, details, exports, and direct links;
- unknown and unauthorized IDs are indistinguishable;
- redaction of tokens, credentials, signed URLs, screenplay/source bodies, raw provider payloads, and hidden model reasoning;
- complete Parallel provenance on every `EvidenceClaim` and unresolved zero-evidence behavior;
- run attempts, retries, predecessor links, idempotency, costs, and totals;
- policy/evaluation/report exact-version bindings;
- deletion grace, restoration, purge tombstone, and reproducibility-loss behavior;
- keyboard, focus, live-region, 44px target, both-theme, and 320–1440px responsive behavior;
- loading, empty, recoverable/permanent error, success, stale/redacted, and access-safe not-found states.

## Architecture gate

This consolidation permits preliminary design of Trust/Records read models, audit taxonomy, redaction policy, evaluation bindings, and bounded-learning lifecycle. It also resolves the authority of Receipt versus `AuditEvent`.

It does not authorize freezing the complete OpenAPI or database schema. The analysis/evidence, revision/monitoring/report, and notification surface reviews still determine final evidence-decision, selective re-scan, export, and event contracts.

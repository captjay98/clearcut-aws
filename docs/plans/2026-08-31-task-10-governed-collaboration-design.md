# Task 10 Governed Collaboration Design

**Date:** 2026-08-31
**Status:** Approved
**Scope:** Full Task 10 capability group
**Authority:** `docs/plans/2026-08-31-atomic-react-tanstack-rebuild.md`, packets 07b–07d, `docs/APPROVAL_POLICY.md`, and `docs/API_OPERATIONS.md`

## Objective

Implement the complete governed evidence-workspace collaboration capability: evidence decisions, assignment, disposition, referral and acknowledgement, comments, one-level replies, immutable revisions, authorized mentions, authoritative item projections, and API-connected browser workflows.

Task 10 must preserve tenant ownership, human accountability, evidence provenance, uncertainty, and the legal boundary. Zero evidence remains unresolved and can never become a clearance conclusion.

## Current problem

The Task 9 read model provides tenant-scoped persisted items and evidence, but Task 10 writes are split across incompatible boundaries:

- the generated client and backend decision routes do not match;
- decision vocabularies differ across the domain, OpenAPI, and UI;
- assignment and disposition use direct delivery-layer SQL without complete capability, version, idempotency, or audit enforcement;
- referrals and comments use browser-local or in-memory state;
- governed writes target the legacy audit table instead of `authoritative_audit_events`;
- item detail omits persisted collaboration history, conflicts, capabilities, and an optimistic-lock version;
- the UI contains fabricated evidence, a seeded comment, and fallback-to-first-item behavior.

These paths cannot be hardened independently without creating inconsistent authorization, concurrency, and audit semantics.

## Chosen architecture

Use a shared governed-command kernel for cross-cutting invariants while keeping domain behavior in the owning bounded modules:

- `decisions`: evidence decisions and dispositions;
- `items`: assignments and authoritative item projections;
- `collaboration`: referrals, acknowledgements, comments, replies, revisions, mentions, and outbox events.

The shared command infrastructure enforces:

1. authenticated organization and project scope;
2. server-derived actor and active membership;
3. current capability;
4. expected item version;
5. canonical intent hash;
6. scoped idempotency identity;
7. typed not-found, forbidden, conflict, and validation outcomes;
8. same-transaction authoritative audit insertion.

Delivery handlers are thin adapters over application services and canonical OpenAPI operations. Existing mismatched or direct-SQL write paths are retired rather than maintained as compatibility behavior.

## Alternatives rejected

### Independent feature-specific command implementations

This would preserve module isolation but duplicate capability, version, intent, idempotency, conflict, and audit behavior. The resulting semantic drift is unacceptable for governed actions.

### Harden existing delivery-layer SQL in place

This is initially faster but deepens the current split between transport, authorization, domain behavior, and persistence. It would also continue legacy audit usage and make race/rollback testing difficult.

## Persistence and ownership

Add one post-`0029` reversible migration with additive changes.

### Clearance items

- Add a monotonic `version` used for optimistic concurrency.
- Advance it only when an accepted command changes authoritative item state.
- Preserve organization, project, script version, and evidence ownership.

### Governed command identity

Persist enough identity to reproduce and validate a command:

- organization ID;
- project ID;
- actor ID;
- operation name;
- idempotency key;
- intent hash;
- expected item version;
- resulting item version;
- immutable response/result identity;
- creation time.

Enforce uniqueness by organization, project, actor, operation, and idempotency key.

The same key and intent returns the original result. The same key with different intent returns a typed conflict.

### Decisions and dispositions

- Store canonical enum values and required rationale.
- Scope records through complete organization/project/item ownership.
- Preserve expected and resulting versions.
- Do not infer a legal conclusion.

### Referrals

- Add organization and project ownership.
- Store draft/submitted/acknowledged lifecycle, target role, question/notes, submitting actor, acknowledging actor, and transition times.
- Keep submission and acknowledgement as separate attributable transitions.

### Comments and replies

- Add organization and project ownership.
- Preserve immutable comment identity and immutable parent identity.
- Allow one reply level only.
- Store edits as append-only revisions rather than overwriting prior content.

### Mentions

- Store recipient user IDs, not parsed usernames as authority.
- Validate recipients as active authorized members of the scoped project.
- Exclude the actor from mention delivery.

### Outbox

- Insert outbox events in the same transaction as the source collaboration change.
- Include schema version and deduplication identity.
- Deliver asynchronously with duplicate protection; delivery does not control source transaction success after commit.

### Audit

All new Task 10 events use `authoritative_audit_events`. No new writes target the legacy `audit_events` table.

### Referential integrity

Use composite ownership constraints for project-owned records. Command, decision, referral, comment, revision, mention, outbox, and audit records must not cross organization or project boundaries.

### Downgrade

Drop new constraints, indexes, tables, and columns in dependency-safe reverse order. Do not rewrite or fabricate protected evidence data during upgrade or downgrade.

## Authorization and command semantics

Clients never submit a trusted role. Application services derive the actor and current capabilities from authenticated request scope.

### Evidence decisions

Allowed actors: Owner, Admin, Reviewer.

Required inputs:

- canonical decision;
- nonblank rationale;
- `expectedVersion`;
- `intentHash`;
- `Idempotency-Key`.

A clearance-like outcome requires cited evidence claims. An item with zero claims remains unresolved and may only receive an escalation, blocker, or further-review outcome. The decision, item transition/version, command identity, and authoritative audit event commit atomically.

### Assignment

Allowed actors: Owner, Admin, Editor, Reviewer.

The assignee must be an active authorized member of the scoped organization/project. Assignment is operational rather than a legal judgment, but remains version-checked, idempotent, attributable, and audited.

### Disposition

Allowed actors: Owner, Admin, Reviewer.

Disposition requires rationale, expected version, intent hash, and idempotency identity. It cannot imply legal clearance or bypass unresolved evidence requirements.

### Referral

Owner, Admin, and Reviewer may submit a referral. Editor may save a draft but may not submit it. Submission and acknowledgement are independent attributable transitions. Referral state, command identity, audit event, and outbox event commit atomically.

### Comments

Active authorized project members may add comments. Replies are limited to one level. Revisions append immutable history. Mentions resolve to active authorized users and exclude the actor. Comment/reply/revision, mention rows, audit event, and outbox events commit atomically.

## Concurrency and failure behavior

- A command changes state only when `expectedVersion` matches the current item version.
- A stale command returns 409 without partial writes.
- Unknown and foreign item IDs use safe not-found parity.
- Missing capability returns a typed 403 with a user-presentable explanation.
- Invalid enums, blank rationale/content, invalid reply depth, or unauthorized mentions return typed validation errors.
- An audit or outbox insertion failure rolls back the complete command.
- Governed frontend mutations do not retry automatically.
- Provider calls are outside Task 10; persisted Task 9 evidence is the only evidence input.

## API contract

OpenAPI remains the executable source of truth.

Canonical operations use `/clearance-items/...` paths and include:

- `assignClearanceItem`;
- `changeClearanceItemDueDate` if retained by the approved operation inventory;
- `recordEvidenceDecision`;
- `setDisposition`;
- `referClearanceItem`;
- `acknowledgeReferral`;
- `addComment`;
- `replyToComment`;
- `reviseComment`.

The contract must:

- normalize decision and disposition vocabularies;
- require `Idempotency-Key` where specified;
- require expected version, rationale, and intent for governed commands;
- expose current item version and server-derived capabilities;
- expose persisted decision, referral, comment, revision, mention, evidence, and conflict projections;
- document typed 403, safe 404, 409, and 422 responses;
- support generated TypeScript and Python clients without manual patches.

## Frontend design

Use TanStack Query for authoritative reads and `useMutation` for writes.

### Read behavior

Item detail presents:

- exact item identity and stable deep link;
- persisted claims and source snapshots;
- explicit zero-evidence state;
- persisted evidence conflicts;
- current item version;
- decision and disposition history;
- assignment and referral state;
- comments, replies, revisions, and mentions;
- server-derived capabilities with role explanations.

The application never substitutes the first item when an exact selected item is unavailable.

### Mutation behavior

- No optimistic domain-state updates.
- Disable automatic retries for governed mutations.
- On success, invalidate and refetch item detail, evidence, worklist, and relevant Records projections.
- On stale conflict, retain the user’s rationale/content and offer authoritative refresh.
- Keep restricted controls visible where explanation is useful; provide a focusable capability explanation.
- Restore focus after dialogs and failed/successful command transitions.

### Removed fallbacks

- Remove fabricated claims from `EvidenceDrawer`.
- Remove the fixed seeded comment.
- Remove browser-local referral, acknowledgement, comment, and revision state.
- Remove fallback-to-first-item behavior.

## Strict-TDD implementation sequence

Every production behavior begins with a focused failing test and recorded expected failure.

1. Contract normalization and generated clients.
2. Migration and ownership/concurrency constraints.
3. Shared governed-command kernel.
4. Evidence-decision vertical slice.
5. Assignment and disposition vertical slices.
6. Referral and acknowledgement vertical slice.
7. Comment, reply, revision, mention, and outbox vertical slice.
8. Authoritative item projection and frontend query/mutation integration.
9. Multi-user browser workflows and accessibility/focus coverage.
10. Full Task 10 verification and independent review.

## Test requirements

### Contract and migration

- Canonical operation/path parity.
- Required headers and fields.
- Generated-client drift.
- Upgrade and downgrade.
- Composite ownership constraints.
- Scoped idempotency uniqueness.
- Immutable revision and outbox constraints.

### Backend behavior

- Role and capability matrices.
- Deactivated membership denial.
- Unknown and cross-tenant safe parity.
- Zero-evidence clearance rejection.
- Exact item and evidence ownership.
- Idempotent replay.
- Key/intent mismatch.
- Two-actor stale-version races.
- Invalid rationale/content/enums/mentions/reply depth.
- Audit and outbox failure rollback.
- No legal conclusion or fabricated evidence.

### Frontend and browser

- Direct item deep links preserve exact identity.
- Explicit zero-evidence and cited-evidence states.
- Reviewer decision and authoritative refresh.
- Stale second-reviewer conflict with retained input.
- Assignment and disposition.
- Referral and acknowledgement.
- Comments, one-level replies, revisions, and authorized mentions.
- Capability explanations.
- Unknown/foreign item behavior.
- Keyboard, focus, responsive, and four-engine coverage.

## Final acceptance gate

Run:

- focused Task 10 API/domain/integration suites;
- contract validation and generated-client drift checks;
- migration upgrade/downgrade tests;
- Task 10 Playwright matrix;
- web production build;
- Ruff and Pyright on attributable Python;
- generator syntax validation where changed;
- safe scoped `git diff --check`;
- security, transaction, evidence-truthfulness, and legal-boundary self-review;
- independent semantic/code-quality review.

## Constraints

- Do not call paid providers.
- Do not inspect or modify either protected `.clearcut` directory.
- Do not fabricate evidence, comments, referrals, audit receipts, or successful command state.
- Do not make legal conclusions.
- Do not modify protected rules through automation.
- Do not create a commit unless the user explicitly requests one.

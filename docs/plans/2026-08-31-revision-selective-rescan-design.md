# Revision and Selective Rescan Vertical Slice Design

**Status:** Approved
**Date:** 2026-08-31
**Scope:** Deadline-focused, provider-free-verifiable end-to-end revision workflow

## Objective

Let an authorized user upload a complete revised screenplay, commit it as the next immutable project version, inspect a persisted conservative diff, and explicitly start a durable selective rescan that processes only changed or new material. Unchanged evidence is carried forward with provenance, while prior human decisions remain historical and require confirmation for the new version.

## Constraints

- Reuse the existing upload, parse, warning-review, and commit workflow.
- Keep the FastAPI modular monolith and module-owned storage boundaries.
- Never overwrite a committed script version or historical evidence.
- Never infer clearance from missing, failed, or carried evidence.
- Require an accountable human trigger before selective rescan dispatch.
- Keep paid providers disabled by default and preserve cost acknowledgement and concurrency gates.
- Support deterministic provider-free tests with fake adapters.
- Prefer one honest vertical slice over a generalized revision engine.

## Architecture

The scripts module owns immutable versions, parsed elements, element lineage, and adjacent-version diffs. Detection owns clearance-item lineage and affected-item detection. Research owns evidence provenance and research execution. Operations owns durable job state and dispatch. A selective-rescan application coordinator invokes typed module ports; modules never read or write each other's storage.

Revision commit and diff persistence are atomic within the scripts module. Starting a rescan atomically records the human trigger, durable job, dispatch intent, and audit event before dispatch. Cross-module rescan processing is idempotent and staged rather than represented as a false distributed transaction.

## Revision Commit

A revised file follows the existing upload flow:

1. Upload the complete revised screenplay.
2. Parse it with the current parser.
3. Review or accept parse warnings.
4. Commit the parse run as the next immutable version.

The commit service locks the project's version sequence, allocates the next ordinal, and enforces uniqueness on `(project_id, ordinal)`. The committed version records its predecessor, parse run, source artifact, content digest, actor, and timestamp. Retrying the same parse-run commit returns the existing version instead of creating another ordinal.

## Deterministic Element Lineage

Element matching is provider-free and deterministic:

1. Match exact normalized element type and text.
2. Disambiguate duplicates using neighboring context.
3. Preserve exact moved elements across position changes.
4. Apply conservative same-type similarity matching for modifications.
5. Treat ambiguous matches as removed plus added.

Lineage records before and after element IDs, change kind (`unchanged`, `moved`, `modified`, `added`, or `removed`), and confidence (`exact`, `contextual`, `similar`, or `unmatched`). Only exact or confidently contextual unchanged/moved matches qualify for evidence carry-forward. Similar, ambiguous, added, and removed material is affected.

The persisted adjacent-version diff contains before/after version IDs, categorized element IDs, matching-algorithm version, and creation time. Algorithm versioning keeps reports reproducible.

## Item and Evidence Lineage

For confidently unchanged or moved passages, the new version receives item projections linked to predecessor items. Existing source snapshots and evidence claims are referenced with their original URL, retrieval time, excerpt, authority classification, stance, query/research-run identity, and provenance. Prior decisions are shown only as historical context. New-version items are `carried_forward_confirmation_required`, never automatically cleared.

Modified and added passages require fresh detection and research. Removed passages remain in historical versions, are linked as removed in the diff, and are excluded from active new-version work. No historical evidence or audit data is deleted.

## Human-Triggered Selective Rescan

After revision commit, the UI displays the persisted diff and impact estimate before provider work. An authorized user explicitly starts selective rescan. The command validates tenant/project scope, actor capability, active policy, adjacent-version diff, provider configuration, and idempotency.

The durable job progresses through:

1. `queued`
2. `materializing_lineage`
3. `carrying_evidence`
4. `detecting_affected_passages`
5. `researching_affected_items`
6. `awaiting_confirmation`
7. `completed`

Each stage persists its result and idempotency marker. Retries resume from the last completed stage without duplicating versions, items, evidence, jobs, or provider calls.

Detection runs only on changed and added passages. Research runs only for resulting affected items. Provider calls use the existing paid-provider acknowledgement and bounded-concurrency gates. Typed provider failures create visible unresolved review outcomes; no fallback evidence is invented.

### Runtime dependency: durable child-job progression requires a queue drainer

Durable rescan child-job progression requires Cloud Tasks (GCP) or a background queue-draining worker. The rescan orchestration is enqueue-only: `request_detection` and `request_research` persist durable child jobs but do not execute them inline, and local recovery only reclaims expired leases — it does not drain fresh `queued` rows. In the production/hosted profile Cloud Tasks dispatches those queued child jobs, so rescans complete. The local single-container profile has no such dispatcher by default: it needs Cloud Tasks, a background queue-draining worker, or (for E2E tests only) the test-only drain endpoint for modified-passage rescans to progress past the initial enqueue to completion. This is an operational dependency of the local profile, not a limitation of the production path.

## API and UI

The API adds or completes typed operations for:

- Commit a parsed upload as the next revision.
- Read an adjacent-version diff and impact summary.
- Start selective rescan for a committed revision.
- Read durable rescan status, stage progress, affected items, saved calls, and typed failures.

The versions UI adds:

- Upload revision through the existing import flow.
- Immutable version timeline.
- Persisted diff filters for unchanged, moved, modified, added, and removed elements.
- Affected-work and carried-forward summary.
- Explicit selective-rescan confirmation showing enabled providers and cost controls.
- Reload-safe durable progress.
- Results grouped into carried evidence requiring confirmation, newly detected/researched items, removed historical items, and unresolved failures.

The production path uses persisted API state; timer-based mock completion is not used.

## Error Handling

- Parse failure commits no version.
- Concurrent ordinal conflicts return a typed conflict or retry safely.
- Version/diff persistence failure rolls back the scripts transaction.
- Dispatch failure leaves a visible queued job for reconciliation.
- Stage failure records a redacted typed error and supports retry.
- Provider failure preserves completed work and creates unresolved review items.
- Reload reconstructs state from persisted versions, diffs, and jobs.
- Cross-tenant or cross-project identifiers fail before repository access.

## Provider-Free Acceptance Test

One end-to-end test creates Version 1 and uploads Version 2 containing unchanged, moved, modified, added, and removed passages. It proves:

- Both immutable versions and the adjacent diff persist.
- Deterministic lineage classifies all five change kinds.
- Only changed and added material enters detection/research.
- Unchanged/moved item and evidence provenance carries forward.
- Prior decisions remain historical and require confirmation.
- Removed items remain historical and leave active scope.
- A durable rescan job survives reload and completes with fake providers.
- Retrying commit, start, or processing is idempotent.
- Tenant and actor authorization fail closed.

## Out of Scope

- Arbitrary branch-and-merge screenplay history.
- Semantic model-based passage matching.
- Automatic carry-forward of clearance decisions.
- Silent provider fallback.
- Firebase runtime work, Portable PostgreSQL worker expansion, or new deployment topology.

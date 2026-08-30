# ClearCut Workflows

## Golden path

```text
Authenticate -> resolve organization -> create project
-> import screenplay -> immutable v1
-> detect ten-category candidates
-> mandatory Parallel Search -> bounded Extract -> source snapshots -> evidence claims/conflicts
-> human assignment/discussion/decision
-> Editor proposes rewrite -> different Reviewer approves -> immutable v2
-> compute affected set -> selective re-scan
-> monitor retained sources -> governed change review
-> generate frozen report snapshot -> human release -> export
```

## Organization entry

1. Authenticate with the deployment-selected adapter.
2. Resolve the internal user and issue/rotate an opaque app session.
3. Resume an invitation, auto-enter one membership, show a chooser for many, or offer organization creation for none.
4. Authorize every organization/project request from current database state.

Organization bootstrap, first Owner membership, default bindings, optional invitation/outbox, and audit commit atomically.

## Ingestion

```text
created -> upload_authorized -> uploaded -> validating -> parsing
        -> warnings_pending -> committed
        -> rejected | failed | expired
```

- Paste/Fountain/FDX parse deterministically.
- PDF parsing may use the approved Gemini path but remains schema-validated and isolated.
- Client checks are advisory; server verifies size, extension, MIME, magic bytes, object generation, and hash.
- Parse warnings require explicit acceptance before v1 commit.

## Analysis and research

Detection may create items before research completes. Research runs per item or bounded batch, persists every Search/Extract call/attempt, stores immutable origin-labelled snapshots, then creates cited claims. Empty, denied, unavailable, partial-enrichment, failed, and conflicting results remain visible terminal/review states. Extract receives only server-selected URLs from the same Search run.

## Decisions and collaboration

Assignments, comments, mentions, and operational triggers may be automatic where policy permits. Evidence decisions, rewrite approval, referral, disposition, monitoring review, report generation, and release require an accountable human. Each governed command re-loads current authorization/policy server-side and commits the action plus `AuditEvent` in one transaction.

## Revision and selective re-scan

```text
rewrite draft -> proposed -> approved -> materialized -> superseded
                            -> rejected | withdrawn
```

The proposer cannot approve. Approval creates the new version, diff, affected-item projection, re-scan job, and audit atomically. Re-scan categories: unchanged, directly affected, nearby affected, moved, removed, added, split, merged. Only directly/nearby affected items require research; preserved evidence keeps exact lineage.

## Monitoring

```text
scheduled|manual -> queued -> running -> completed|failed|cancelled
source result -> non_material | material | unavailable
material/unavailable -> review item -> keep+follow-up | reopen | refer
```

Monitoring never changes a decision automatically. Reopen supersedes the prior decision; keep creates a real task; refer creates a referral.

Scheduled Search/Extract is the stable monitoring path. When conditional Parallel Monitor is enabled, its signed event-stream webhook creates only an untrusted candidate; a new scoped Search/Extract run must verify it before materiality and review.

## Evaluation and learning

```text
run -> deterministic gates -> independent judge -> persisted evaluation
-> proposal -> regression -> shadow -> bounded canary -> promote|rollback
```

A blocker prevents acceptance/promotion/release use regardless of judge score. Learning candidates may change only allowlisted low-risk phrasing/examples/prompt refinements/organization preferences. Protected rules are human-only.

## Report lifecycle

```text
live preview -> generation queued -> immutable snapshot ready
-> human attestation -> released -> downloadable
                         -> superseded by a later released snapshot
```

Generation and release are separate governed commands. A released artifact never reads live mutable state. Drift is reported against, not applied to, the frozen release.

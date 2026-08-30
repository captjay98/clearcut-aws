# Revisions and Selective Re-scan Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create immutable screenplay revisions through maker/checker rewrites or re-imports and re-run only evidence work affected by a structural diff.

**Architecture:** Stable element/span identities and explicit lineage classify changes. Rewrite approval atomically creates a version, diff, affected set, re-scan job/outbox, and audit; background work checkpoints per item.

**Tech Stack:** Python domain diff engine, SQLAlchemy/PostgreSQL, Cloud Tasks adapter, property testing, TanStack versions UI.

---

**Depends on:** Plans 03, 05, 07  
**Checkpoint:** R6

### Task 1: Implement rewrite lifecycle and maker/checker tests

States: draft, proposed, approved, rejected, withdrawn, materialized, superseded. Test proposer cannot approve, stale proposal/version conflicts, role/project scope, rationale, idempotency, and preserved history.

### Task 2: Implement stable diff and lineage property tests

Classify unchanged, direct, nearby, moved, removed, added, split, merged. Generate arbitrary scene/element edits and assert unchanged logical elements keep identity, removed evidence remains historical, and repeated evaluation of identical normalized inputs is deterministic. Test transport/serialization ordering separately; screenplay element order is semantic.

```python
@given(script_version_pairs())
def test_affected_set_is_deterministic(pair):
    first = diff(pair.before, pair.after)
    second = diff(pair.before, pair.after)
    assert first.affected_logical_ids == second.affected_logical_ids
```

### Task 3: Commit immutable v2+ atomically

Approval transaction writes proposal decision, new version/elements, diff/lineage, affected projection, re-scan run/outbox, and `AuditEvent`. Simulate failure at each write and prove no partial version/job/audit.

### Task 4: Implement durable selective re-scan

Test per-item queued/running/succeeded/failed/cancelled, retry of only failed work, predecessor continuation, reused evidence, no duplicate calls, and late/stale worker protection. Direct/nearby items research against the new version; unaffected claims retain prior version lineage.

### Task 5: Implement Versions UI and cross-version reads

Build v1-only guidance, history, rewrite/re-import diff, hashes behind disclosure, per-flag progress, failure/retry/cancel, moved/removed/added lineage, current versus locked versions, and navigation. Use production-only release language; no rewrite trigger belongs on Versions.

```bash
uv run pytest services/api/tests/versions services/api/tests/rescan -q
pnpm --filter @clearcut/web test:e2e -- revision-rescan
```

Expected: commands exit 0 and test output proves unaffected items made zero new research calls.

### Exit criteria

- Separate actors propose and approve the golden rewrite.
- v1 remains immutable and readable; v2 is exact approved text.
- Affected scope is computed, not fixture IDs.
- Only affected items cause new research; unchanged source lineage is preserved.
- Partial failure/retry/cancel is durable and idempotent.
- R6 captures source/tool-call counts proving checks saved.

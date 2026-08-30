# Monitoring Materiality and Governed Review Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Compare verified old/new snapshots, classify material/unavailable changes, and let an authorized human keep, reopen, or refer without mutating prior evidence or decisions.  
**Architecture:** Materiality operates only on scoped snapshots produced by the approved Search/Extract path. Review commands re-authorize current state and commit the decision plus authoritative `AuditEvent` atomically; provider confidence is input, never a decision.  
**Tech Stack:** Python 3.12, PostgreSQL, Pydantic, Hypothesis, pytest.

---

**Depends on:** 09a, 07b  
**Governing inputs:** `docs/EVIDENCE_POLICY.md`, `docs/APPROVAL_POLICY.md`, `docs/WORKFLOWS.md`

### Task 1: Implement deterministic change comparison and materiality inputs

**Files:**
- Create: `services/api/src/clearcut/monitoring/application/compare_snapshots.py`
- Create: `services/api/src/clearcut/monitoring/domain/materiality.py`
- Test: `services/api/tests/monitoring/test_snapshot_comparison.py`
- Test: `services/api/tests/monitoring/test_materiality.py`
- Test: `services/api/tests/monitoring/test_materiality_properties.py`

**Steps:**
1. Add failing exact-old/new binding, content-only/formatting-only, date/title/redirect/unavailable, citation disagreement, injection, duplicate, and cross-project property tests.
2. Run tests; expect missing comparison failures.
3. Implement normalized comparison inputs without changing either snapshot. Deterministic blockers handle missing scope/provenance/injection; Gemini may propose a materiality explanation only after blockers pass.
4. Persist `non_material`, `material`, or `unavailable` with exact old/new snapshot IDs, policy/prompt/model versions, rationale, and originating watch/provider event.
5. Run tests; expect pass and no source body leakage.

### Task 2: Create deduplicated review work

**Files:**
- Create: `services/api/src/clearcut/monitoring/application/open_change_review.py`
- Test: `services/api/tests/monitoring/test_review_deduplication.py`
- Test: `services/api/tests/monitoring/test_review_scope.py`

**Steps:**
1. Add failing material/unavailable, repeated signal, concurrent worker, superseded snapshot, default assignee, escalation window, and revoked membership tests.
2. Implement idempotent review creation for material/unavailable changes only. Non-material changes remain recorded but do not create human work.
3. Run concurrency/scope tests; expect one addressable review item per effective change.

### Task 3: Implement governed keep, reopen, and refer commands

**Files:**
- Create: `services/api/src/clearcut/monitoring/application/review_change.py`
- Test: `services/api/tests/monitoring/test_review_commands.py`
- Test: `services/api/tests/monitoring/test_review_atomicity.py`
- Test: `services/api/tests/monitoring/test_review_roles.py`

**Steps:**
1. Add failing role, rationale, recent-state, stale review, concurrent reviewer, rollback, and audit tests.
2. Implement `keep_with_follow_up`, `reopen`, and `refer`. Reopen creates a superseding review/decision projection; it never deletes or edits the prior decision. Keep creates a real assigned task; refer creates a governed referral.
3. Re-load authorization, policy, evidence, and review freshness inside the transaction and commit the effect plus `AuditEvent` atomically.
4. Run tests; expect rollback to leave neither state nor audit half-committed.

### Task 4: Expose projections and record evidence

**Files:**
- Create: `services/api/src/clearcut/monitoring/application/watch_projection.py`
- Test: `services/api/tests/monitoring/test_watch_projection.py`
- Create: `docs/reviews/<date>-09b-monitoring-review.md`

**Steps:**
1. Add failing API projection tests for run/provider/change/review state, old/new links, source origin, provider-event correlation, assignee, action availability, redaction, and unauthorized parity.
2. Implement the scoped projection consumed by Watch, Notifications, Records, and report inputs.
3. Run monitoring/audit/security/contract tests plus one staging scheduled chain; expect preserved decisions and deduplicated review work.
4. Commit only after owner authorization with `feat: add governed evidence watch review`.

### Exit criteria

- Only verified Search/Extract snapshots participate in materiality.
- Material/unavailable changes open deduplicated human review; non-material changes remain recorded.
- Keep/reopen/refer preserve history and commit atomically with authoritative audit.
- No provider signal or model output changes an evidence decision automatically.


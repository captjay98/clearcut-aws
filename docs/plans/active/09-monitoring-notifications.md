# Monitoring and Notifications Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Re-check retained evidence through scheduled Search/Extract, optionally accept signed Parallel Monitor event-stream signals after a recorded go/no-go, open governed review for verified material changes, and deliver authorized redacted notifications.

**Architecture:** Scheduled Search/Extract is the always-available durable path. Conditional Monitor signals are verified, replay-safe candidate inputs that must pass a new scoped Search/Extract run before materiality. Domain/operational events feed a recipient/template service that writes first-class notifications transactionally.

**Tech Stack:** FastAPI/PostgreSQL, Cloud Scheduler/Tasks adapters, Web Push, SSE, TanStack Start.

---

**Depends on:** Plans 07–08  
**Checkpoint:** R7 with Plan 10

### Task 1: Implement monitoring policy and run lifecycle

Test off/manual/daily/weekly cadence, next-run computation, schedule dedupe, manual trigger, lease/retry/cancel/reconcile, checkpoint count, project authorization, default assignee, and escalation window. Cadence is operational history, not a governed decision.

### Task 2: Gate and implement conditional Parallel Monitor signals

After R3, record owner go/no-go. On GO, implement only `event_stream` create/update/cancel/events, HMAC-SHA256 webhook verification, timestamp/replay protection, provider-event dedupe, scope revocation, and mandatory Search/Extract verification. On NO-GO, leave Monitor unbound and make no Monitor claim; scheduled monitoring remains complete.

### Task 3: Implement source comparison/materiality

Persist new snapshots and classify non-material, material, or unavailable with exact old/new references and rationale. Test content-only versus formatting change, redirect/unavailable, prompt injection, duplicate change, and source removed after project access loss.

### Task 4: Implement governed monitoring review

Keep+follow-up creates an addressable assigned task; reopen creates a superseding review/decision projection without deleting prior verification; refer creates a referral. Each commits with rationale and audit. Test same-transaction rollback and stale review races.

### Task 5: Implement notification event taxonomy/recipients

Create event schemas/templates and table-driven recipient tests for every row in `docs/plans/2026-08-29-notifications-ui-design.md` §Event taxonomy. Apply self-exclusion, active membership, project authorization, ownership/assignment, fixed role, and dedupe before insert. Payloads stay redacted. CI fails when an approved taxonomy row has no fixture.

```python
assert actor.id not in recipients_for(event)
assert all(can_access_destination(user, event.destination) for user in recipients_for(event))
```

### Task 6: Implement inbox and delivery layers

Build project/tier filters, stable structured destinations, unread/read/mark-all, nav badge, loading/empty/filter-empty/recoverable/permanent/destination-unavailable states, contextual push permission banner, SSE reconnect with `Last-Event-ID`, bounded replay/backpressure, and polling fallback. Push payload is notification ID, tier, and generic title only. Archive inbox notifications after 90 days while retaining authorized operational correlation; revoke/expire subscriptions safely.

### Task 7: Add scheduled and delivery integration proof

Use deterministic clock tests locally; in staging verify Scheduler -> task -> monitoring run -> change -> review item -> notification -> authorized destination. Record provider/task receipts without source bodies or tokens.

```bash
uv run pytest services/api/tests/monitoring services/api/tests/notifications -q
pnpm --filter @clearcut/web test:e2e -- monitoring notifications
```

Expected: commands exit 0; SSE-disconnect case proves polling fallback and revoked destinations do not navigate.

### Exit criteria

- Monitoring never silently changes evidence/decisions.
- Search/Extract rechecks work without Monitor; enabled Monitor signals are signed, replay-safe, and re-verified.
- Material/unavailable changes open deduplicated review work.
- All review effects preserve history and audit atomically.
- Recipient matrix/self-exclusion/project revocation pass.
- SSE falls back to polling; urgent push requires permission.
- Inbox implements every planned state and no sensitive metadata.

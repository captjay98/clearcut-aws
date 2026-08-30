# Evidence Watch and Conditional Parallel Monitor Runtime Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Re-check retained evidence through scheduled Search/Extract and, only after an owner go/no-go, ingest Parallel `event_stream` signals securely as additional candidates for verification.  
**Architecture:** ClearCut's durable watch scheduler is the always-available product path. Conditional Parallel Monitor lifecycle and signed webhooks add new-event signals, but every signal is verified through the normal scoped Search/Extract path before it can become a change candidate.  
**Tech Stack:** Python 3.12, PostgreSQL, Cloud Scheduler/Tasks ports, `parallel-web`, FastAPI webhooks, HMAC-SHA256, OpenTelemetry, pytest.

---

**Depends on:** 05c, 07b, 08b  
**Governing inputs:** `docs/PARALLEL_INTEGRATION.md`, `docs/EVIDENCE_POLICY.md`, `docs/SECURITY_AND_PRIVACY.md`, `docs/API_OPERATIONS.md`  
**Release rule:** Tasks 1–3 are required for the product monitoring feature. Tasks 4–6 execute only when `docs/reviews/<date>-parallel-monitor-go-no-go.md` records owner **GO** after R3. Monitor no-go does not block R9 and must not be represented as implemented.

### Task 1: Freeze watch, run, provider-event, and lifecycle contracts

**Files:**
- Modify: `packages/contracts/openapi.yaml`
- Create: `services/api/src/clearcut/monitoring/domain/models.py`
- Create: `services/api/src/clearcut/monitoring/domain/events.py`
- Create: `services/api/src/clearcut/monitoring/ports/web_monitor.py`
- Create: `services/api/alembic/versions/0015_monitoring.py`
- Test: `services/api/tests/monitoring/test_contracts.py`
- Test: `services/api/tests/migrations/test_0015_monitoring.py`

**Step 1:** Add failing contract tests for off/manual/daily/weekly policy, exact-source versus new-event watch kind, provider capability state (`disabled`, `pending`, `active`, `degraded`, `cancelled`), run/checkpoint lifecycle, monitor/event IDs, materiality candidate, and governed review link.

**Step 2:** Run tests; expect missing-contract failures.

**Step 3:** Define capability-specific `WebMonitorPort` types from `docs/PARALLEL_INTEGRATION.md`; Monitor content/basis is untrusted input and is never a `SourceSnapshot` or `EvidenceClaim`.

**Step 4:** Add migration 0015 for scoped monitoring policies, watches, runs/checkpoints, provider monitor lifecycle attempts, webhook receipts, provider events, change candidates, and review items. Add composite scope keys, dedupe/replay constraints, and query indexes. No table may grant a provider event authority to mutate an existing claim/decision.

**Step 5:** Test upgrade/downgrade, uniqueness, revoked project scope, immutable provider receipts, and index query plans; run contract/migration tests and expect pass.

### Task 2: Implement the mandatory scheduled Search/Extract recheck path

**Files:**
- Create: `services/api/src/clearcut/monitoring/application/change_policy.py`
- Create: `services/api/src/clearcut/monitoring/application/run_scheduled_watch.py`
- Create: `services/api/src/clearcut/monitoring/adapters/scheduler.py`
- Test: `services/api/tests/monitoring/test_cadence.py`
- Test: `services/api/tests/monitoring/test_scheduled_recheck.py`
- Test: `services/api/tests/monitoring/test_watch_jobs.py`

**Step 1:** Add failing off/manual/daily/weekly next-run, timezone, dedupe, lease, retry, cancel, reconcile, scope revocation, and checkpoint tests using a deterministic clock.

**Step 2:** Add failing exact retained-URL recheck tests. The job calls bounded Extract only for an already-authorized retained URL and runs Search when the watch is query/topic based or Extract reports unavailable/redirected content.

**Step 3:** Implement policy/outbox/scheduler/task operations. Organization preferences may reduce cadence or disable monitoring but cannot raise provider ceilings or bypass authorization.

**Step 4:** Persist new immutable snapshots/attempts and a raw change candidate; do not classify materiality or open governed review in this packet.

**Step 5:** Run monitoring/research/security tests; expect scheduled monitoring to work without Parallel Monitor API.

### Task 3: Record the Parallel Monitor go/no-go

**Files:**
- Create: `docs/reviews/<date>-parallel-monitor-go-no-go.md`
- Modify: `docs/submission/limitations.md` when it exists

**Step 1:** After R3 passes, record remaining schedule, working credentials/quota, official API/SDK version, webhook-secret availability, deployed HTTPS endpoint readiness, and golden-path risk.

**Step 2:** Owner records one decision:

```text
GO     -> execute Tasks 4–6 and claim Monitor only after deployed proof
NO-GO  -> leave WebMonitorPort unbound, skip Tasks 4–6, retain scheduled Search/Extract monitoring
```

**Step 3:** Verify a no-go production manifest contains no Monitor configuration, routes, claims, or demo footage.

### Task 4: Implement the conditional Parallel event-stream adapter and lifecycle

**Files:**
- Create: `services/api/src/clearcut/monitoring/adapters/parallel_monitor.py`
- Create: `services/api/src/clearcut/monitoring/application/sync_parallel_monitor.py`
- Test: `services/api/tests/monitoring/test_parallel_monitor_adapter.py`
- Test: `services/api/tests/monitoring/test_monitor_lifecycle.py`
- Test: `services/api/tests/conformance/test_web_monitor_port.py`

**Step 1:** Add failing create/update/cancel/list-events normalization and auth/rate/config/schema/ambiguous failure tests using sanitized captures.

**Step 2:** Implement only `type="event_stream"` with intent-heavy bounded queries, approved frequency, safe source policy, and an opaque random external correlation ID. Never use snapshot Monitor, Task, or `previous_interaction_id`.

```python
monitor = client.monitor.create(
    type="event_stream",
    frequency=request.frequency,
    processor="lite",
    settings={"query": request.query, "advanced_settings": request.advanced_settings},
    webhook={"url": request.webhook_url, "event_types": list(request.event_types)},
    metadata={"external_id": request.external_id},
)
```

**Step 3:** Persist lifecycle attempts and `monitor_id`. Update/cancel on cadence/query-policy change, watch removal, project deletion scheduling, scope loss, or owner no-go reversal. Cancellation is reconciled when provider outcome is ambiguous.

**Step 4:** Register `ParallelMonitorAdapter` only when the reviewed deployment capability flag and webhook secret are present. Startup rejects Task/snapshot monitor configuration.

**Step 5:** Run lifecycle/conformance tests; expect pass.

### Task 5: Verify and ingest signed Monitor webhooks

**Files:**
- Create: `services/api/src/clearcut/monitoring/delivery/parallel_webhook.py`
- Create: `services/api/src/clearcut/monitoring/application/ingest_parallel_event.py`
- Test: `services/api/tests/monitoring/test_parallel_webhook_signature.py`
- Test: `services/api/tests/monitoring/test_parallel_webhook_replay.py`
- Test: `services/api/tests/monitoring/test_parallel_event_ingest.py`

**Step 1:** Add failing missing/malformed/valid/invalid/multi-signature/rotated-secret tests plus old/future timestamp, exact-body mutation, duplicate webhook ID, unknown monitor, revoked scope, delayed/out-of-order event, and event-fetch failure tests.

**Step 2:** Verify the Standard Webhooks headers over the exact request bytes with a five-minute tolerance and constant-time comparison:

```python
signed = webhook_id.encode() + b"." + timestamp.encode() + b"." + raw_body
expected = base64.b64encode(hmac.new(secret, signed, hashlib.sha256).digest())
if not any(hmac.compare_digest(expected, candidate) for candidate in v1_signatures):
    raise InvalidWebhookSignature
```

Do not parse JSON, acknowledge, enqueue, or log body fields before verification.

**Step 3:** After verification, commit the webhook ID/timestamp/body hash/monitor/event-group correlation and outbox message atomically, then return success. Duplicate valid delivery returns idempotent success without duplicate work.

**Step 4:** In a worker, fetch events by persisted `monitor_id` and `event_group_id`. Store bounded redacted content/citations/provider IDs; never trust webhook metadata as authorization.

**Step 5:** Feed each candidate through a new scoped Search/Extract verification run. Only verified new snapshots proceed to materiality in 09b.

**Step 6:** Run webhook/event/security tests; expect all forged/replayed/revoked inputs blocked and duplicates deduplicated.

### Task 6: Prove conditional Monitor behavior

**Files:**
- Create: `services/api/tests/live/test_parallel_monitor_live.py`
- Modify: `scripts/verify-runtime-profile.mjs`
- Create: `docs/reviews/<date>-09a-parallel-monitor-evidence.md`

**Step 1:** Add profile checks proving only `event_stream` Monitor is reachable and excluded Parallel APIs remain absent.

**Step 2:** In staging, create a disposable monitor, verify an authentic or provider-supported test webhook through the deployed endpoint, fetch its event group, prove dedupe, then cancel it and verify terminal provider/local state. Do not leave billable monitors running.

**Step 3:** Record safe IDs, timestamps, SHA/digest, request status/latency, webhook verification result, event/recheck correlation, cancellation receipt, and explicit non-claims.

**Step 4:** Claim Monitor in R9/video only when this evidence matches the deployed candidate.

### Exit criteria

- Manual/daily/weekly evidence watch works through bounded Search/Extract regardless of Monitor go/no-go.
- Enabled Monitor accepts only verified signed/replay-safe events and treats them as candidate signals.
- Every Monitor signal is re-verified through mandatory Search/Extract before governed review.
- Monitor never changes evidence, decisions, rewrites, reports, or protected policy automatically.
- Task, snapshot Monitor, FindAll, Responses/Chat, Interactions, and Deep Research remain absent.

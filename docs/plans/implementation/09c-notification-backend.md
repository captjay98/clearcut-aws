# Notification Projection and Delivery Backend Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Project approved domain/operational events into an authorized redacted inbox, SSE/polling feed, and urgent push delivery.  
**Architecture:** Recipient projections consume versioned outbox events idempotently; delivery attempts remain operational records and never determine recipients from provider payloads.  
**Tech Stack:** PostgreSQL, FastAPI, SSE, Web Push, JSON Schema, pytest.

---

**Depends on:** 02c, 07c, 09b

### Task 1: Freeze taxonomy and recipient fixtures

**Files:**
- Create: `services/api/src/clearcut/collaboration/domain/notifications.py`
- Create: `services/api/tests/fixtures/notification_taxonomy.yaml`
- Test: `services/api/tests/notifications/test_taxonomy.py`
- Test: `services/api/tests/notifications/test_recipients.py`

**Steps:**
1. Encode every approved taxonomy row and add failing fixture-completeness, recipient, self-exclusion, redaction, project-revocation, and structured-destination tests.
2. Implement closed event/template mappings; CI fails when an approved taxonomy row lacks a fixture.
3. Run taxonomy tests; expect pass.

### Task 2: Implement authorized inbox projection

**Files:**
- Create: `services/api/src/clearcut/collaboration/application/recipient_projection.py`
- Create: `services/api/alembic/versions/0016_notifications.py`
- Test: `services/api/tests/notifications/test_authorization.py`
- Test: `services/api/tests/notifications/test_deduplication.py`
- Test: `services/api/tests/migrations/test_0016_notifications.py`

**Steps:**
1. Add failing active-membership, ownership/assignment, fixed-role, self-exclusion, dedupe, concurrency, and scope-change tests.
2. Add migration 0016 and implement idempotent event-to-recipient projection. Provider/webhook metadata never supplies recipient IDs or destinations.
3. Run migration/authorization tests; expect pass.

### Task 3: Implement inbox, SSE, polling, push, and retention

**Files:**
- Create: `services/api/src/clearcut/collaboration/application/delivery.py`
- Create: `services/api/src/clearcut/collaboration/delivery/sse.py`
- Create: `services/api/src/clearcut/collaboration/adapters/web_push.py`
- Test: `services/api/tests/notifications/test_sse_replay.py`
- Test: `services/api/tests/notifications/test_push_redaction.py`
- Test: `services/api/tests/notifications/test_retention.py`

**Steps:**
1. Add failing list/read/mark-all, `Last-Event-ID`, bounded replay/backpressure, polling parity, revoked subscription, generic push, retry, and 90-day archive tests.
2. Implement endpoints and delivery jobs. Push contains only notification ID, tier, and generic title; destination is resolved after authenticated application entry.
3. Run notification/security/contract tests; expect no sensitive payload and no revoked-scope delivery.
4. Record `docs/reviews/<date>-09c-notifications.md` and commit only after owner authorization with `feat: add authorized notification delivery`.

### Exit criteria

- Every approved event has tested recipients and redacted content.
- Inbox/SSE/polling/push remain authorized after membership/project changes.
- Parallel provider content cannot select recipients or destinations.


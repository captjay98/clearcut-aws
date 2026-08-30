# Watch and Notifications UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the mock-authoritative evidence-watch review and organization inbox with truthful Search/Extract/conditional-Monitor states.  
**Architecture:** TanStack routes consume generated clients and structured destinations after authorization; SSE degrades to polling. Provider operation details appear only as safe linked Records projections, while user actions remain domain language.  
**Tech Stack:** TanStack Start, generated TypeScript client, Service Worker, Playwright, axe.

---

**Depends on:** 09b, 09c, 06c

### Task 1: Freeze Watch and notification UI state fixtures

**Files:**
- Modify: `docs/UI_STATE_MATRIX.md`
- Create: `apps/web/src/features/watch/watch-state.ts`
- Create: `apps/web/src/features/notifications/notification-state.ts`
- Test: `apps/web/src/features/watch/watch-state.test.ts`
- Test: `apps/web/src/features/notifications/notification-state.test.ts`

**Steps:**
1. Add failing fixtures for off/manual/daily/weekly, scheduled run, Search running/empty/failure, Extract full/partial/failure, unchanged/material/unavailable, Monitor disabled/pending/active/degraded, provider signal awaiting verification, review outcomes, inbox empty/filter-empty/unread/read, revoked destination, and all loading/error/not-found states.
2. Implement exhaustive discriminated-union render models; unknown states fail tests rather than silently showing success.
3. Run unit/contract drift tests; expect pass.

### Task 2: Implement the Watch surface from the mock

**Files:**
- Create: `apps/web/src/routes/o.$orgSlug.projects.$projectId.watch.tsx`
- Create: `apps/web/src/features/watch/WatchPage.tsx`
- Test: `apps/web/tests/e2e/watch.spec.ts`

**Steps:**
1. Add failing E2E for every approved state, role/capability matrix, cadence change, manual run, old/new evidence links, keep/reopen/refer dialog, stale/conflicting action, keyboard order, focus restoration, mobile layout, and unauthorized/not-found parity.
2. Implement generated-client reads/commands and the mock's visual hierarchy. Label Monitor as an additional signal only when enabled; never imply it replaced Search or made a decision.
3. Run Watch E2E, axe, both-theme visual, and responsive tests; expect pass.

### Task 3: Implement Notifications and resilient delivery

**Files:**
- Create: `apps/web/src/routes/o.$orgSlug.notifications.tsx`
- Create: `apps/web/src/features/notifications/NotificationsPage.tsx`
- Create: `apps/web/public/service-worker.js`
- Test: `apps/web/tests/e2e/notifications.spec.ts`
- Test: `apps/web/tests/e2e/sse-fallback.spec.ts`

**Steps:**
1. Add failing filters/read counts/mark-all/push prompt/denied permission/generic push/SSE loss-replay/poll fallback/revoked destination/all-role tests.
2. Implement generated-client operations, structured authorized destinations, contextual push permission, bounded SSE replay, and polling fallback.
3. Run notification E2E/axe/visual/responsive tests and staging delivery chain; expect pass.
4. Record `docs/reviews/<date>-09d-watch-notifications-ui.md` and commit only after owner authorization with `feat: add evidence watch and notification ui`.

### Exit criteria

- Watch truthfully distinguishes Search, Extract enrichment, scheduled recheck, optional Monitor signal, verification, and human review.
- Inbox states remain authorized, accessible, addressable, and delivery-resilient.
- The UI never presents a provider signal as admitted evidence or an automated decision.


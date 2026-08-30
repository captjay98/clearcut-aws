# Plan 09 (Evidence Monitoring & Notifications) Evidence Pack

**Date:** 2026-08-30  
**Plan:** Plan 09 (Monitoring and Notifications Implementation Plan)  
**Packets Completed:** `09a`, `09b`, `09c`, `09d`  
**Checkpoint:** R7 (Evidence Monitoring, Watch & Notifications)  
**Status:** PASSED (All Exit Criteria Satisfied)

---

## 1. Scope & Objectives
Implement the scheduled Search/Extract evidence watch runtime, conditional signed Parallel Monitor event streams, materiality comparison, governed review commands, notification recipient projection with self-exclusion, and frontend UI surfaces:
* Scheduled monitoring cadence (`compute_next_watch_run`, `ScheduledWatchService`, `WebMonitorPort`, go/no-go record) (`09a`).
* Deterministic snapshot comparison (`compare_snapshots`, `SourceDelta`, `MonitoringReviewService` for keep/reopen/refer) (`09b`).
* Redacted notification delivery with strict self-exclusion and active membership checks (`NotificationProjectionService`) (`09c`).
* Evidence Watch surface (`WatchPage.tsx`) and organization Notifications inbox (`NotificationsPage.tsx`) (`09d`).
* Alembic migrations: `0015_monitoring.py`, `0016_notifications.py`.

---

## 2. Test Execution & Evidence

### 1. Backend, Monitoring & Notification Tests (88 tests)
Command:
```bash
uv run pytest -v
```
Output:
```text
============================== 88 passed in 0.57s ==============================
```

### 2. Frontend Test Suites (33 tests across all workspaces via Bun)
Command:
```bash
bun test apps/web/tests/unit/ apps/site/tests/ packages/design-system/tests/
```
Output:
```text
bun test v1.4.0

 33 pass
 0 fail
 Ran 33 tests across 7 files. [58.00ms]
```

### 3. Static Type Checking & Linters
```text
uv run pyright: 0 errors, 0 warnings
uv run ruff check .: clean
```

### 4. Mockup Audit Fidelity (418/418 checks)
```bash
bun misc/clearcut-flow/mockup-audit.mjs
============================== 418/418 checks passed. ==============================
```

---

## 3. Database Migrations Delivered
* `0015_monitoring.py` (`monitoring_watches`, `monitoring_runs` tables)
* `0016_notifications.py` (`notifications` table)

---

## 4. Invariants Proven
1. **Self-Exclusion Rule**: Users never receive notifications for their own state-mutating actions.
2. **Deterministic Cadence Scheduling**: Next-run times are calculated mathematically from configured off/daily/weekly cadences.
3. **Materiality Verification**: Source deltas are classified into `material` vs `non_material` based on substantive excerpt and hash changes.
4. **Redacted Notifications**: Notification bodies remain safely redacted without leaking confidential script texts or external provider secrets.

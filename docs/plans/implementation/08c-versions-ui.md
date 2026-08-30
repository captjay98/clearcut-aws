# Versions and Re-scan UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement immutable version history, diffs, lineage, and durable per-item re-scan states.  
**Architecture:** UI reads generated version/job projections and never computes affected scope.  
**Tech Stack:** TanStack Start, Playwright.

---

**Files:** Create `apps/web/src/routes/o.$orgSlug.projects.$projectId.versions.tsx`, `apps/web/src/features/versions/`; test `apps/web/tests/e2e/versions-rescan.spec.ts`.

1. Add failing E2E for the `versions` state row, maker/checker actors, diff classes, hashes disclosure, retry/cancel, locked/current versions, and navigation.
2. Implement generated-client UI; run UI matrix/axe/visual and backend-connected selective-call proof; expect exit 0 and zero calls for unaffected items.
3. Record evidence; commit `feat: add version and rescan workspace` after authorization.

**Exit:** Version history and durable re-scan state are truthful at every target viewport.

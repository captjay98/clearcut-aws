# Report Preview, Release, Download, and Print UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement truthful live preview, generation, frozen review, release, download, and print states.  
**Architecture:** Generated semantic commands keep generation/release distinct; document content comes only from snapshot projections.  
**Tech Stack:** TanStack Start, Playwright, browser PDF/print checks.

---

**Files:** Create `apps/web/src/routes/o.$orgSlug.projects.$projectId.report.tsx`, `apps/web/src/features/report/`; test `apps/web/tests/e2e/report.spec.ts`, `report-print.spec.ts`.

1. Add failing E2E for every report state, seven tabs/exhibits, open items, binding, release-only copy, all roles, expired download, stale/superseded, print isolation/selectable text/page splits.
2. Implement generated-client UI; run UI matrix/axe/visual/Chromium-Firefox-WebKit print tests; expect exit 0 with no split exhibits or app chrome.
3. Record evidence; commit `feat: add clearance report delivery surface` after authorization.

**Exit:** Report generation, release, download, and print are distinct truthful UI states.

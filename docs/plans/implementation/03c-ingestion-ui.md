# Project Creation and Ingestion UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the three-step project/import/check flow with truthful durable states.  
**Architecture:** Real file/drop and paste controls call generated operations; job state comes from polling/SSE, never timers pretending to be backend work.  
**Tech Stack:** TanStack Start, generated client, Playwright.

---

**Files:** Create `apps/web/src/routes/o.$orgSlug.projects.new.tsx`, `apps/web/src/features/ingestion/import-step.tsx`, `parse-review.tsx`, `analysis-progress.tsx`; test `apps/web/tests/e2e/ingestion.spec.ts`, `ingestion-access.spec.ts`.

1. Add failing E2E tests for four formats, actual input/drop, advisory client checks versus server result, warnings, cancel/continue, and every `new` state in `docs/UI_STATE_MATRIX.md`.
2. Run `pnpm --filter @clearcut/web test:e2e -- ingestion`; expect missing-route failures.
3. Implement UI with generated clients, accessible step/status announcements, durable job polling, and no sample-result fallback.
4. Run five-width/two-theme/keyboard/axe/unauthorized and backend-connected E2E; expect exit 0.
5. Record evidence; commit `feat: add truthful ingestion workspace` after authorization.

**Exit:** The mock chooser is replaced by real behavior and no UI timer claims provider completion.


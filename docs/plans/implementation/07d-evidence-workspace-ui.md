# Evidence Workspace UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement project, screenplay workspace, item worklist, and item detail surfaces.  
**Architecture:** Generated read/command clients drive all routes; the design system owns presentation.  
**Tech Stack:** TanStack Start, Playwright, ClearCut design system.

---

**Files:** Create `apps/web/src/routes/o.$orgSlug.projects.$projectId.tsx`, `.workspace.tsx`, `.items.tsx`, `.items.$itemId.tsx`, `apps/web/src/features/evidence/`; test `apps/web/tests/e2e/evidence-workspace.spec.ts`, `evidence-access.spec.ts`, `item-print.spec.ts`.

1. Add failing E2E for `project/workspace/items/item` state rows, deep links, stable anchors, filters, mobile tabs, provenance, zero evidence, conflicts, all roles, and print.
2. Implement generated-client routes with one decision command path, capability explanations, and no local domain state machine.
3. Run UI matrix/axe/visual/print plus API-connected multi-user path; expect exit 0.
4. Record evidence; commit `feat: add evidence review workspace` after authorization.

**Exit:** Expect every workspace route/state/role/direct-link/print gate to pass against generated clients.

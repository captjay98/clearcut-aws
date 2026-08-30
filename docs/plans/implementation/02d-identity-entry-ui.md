# Identity, Entry, Projects, and Team UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement auth, invitation, onboarding, projects, and Team surfaces against generated clients.  
**Architecture:** Routes contain presentation/state orchestration only; server operations own security and domain behavior.  
**Tech Stack:** TanStack Start, generated TypeScript client, ClearCut design system, Playwright.

---

**Files:** Create `apps/web/src/routes/auth/sign-in.tsx`, `auth/invite.$token.tsx`, `onboarding.tsx`, `o.$orgSlug.projects.tsx`, `o.$orgSlug.team.tsx`, `apps/web/src/features/identity/`, `apps/web/src/features/team/`; test `apps/web/tests/e2e/identity-entry.spec.ts`, `team.spec.ts`.

1. Add failing generated-client component/E2E tests for all five `docs/UI_STATE_MATRIX.md` rows and Owner/Admin/Editor/Reviewer/Viewer controls.
2. Run `pnpm --filter @clearcut/web test:e2e -- identity-entry`; expect missing-route failures.
3. Implement routes with accessible forms, focus/live regions, safe direct links, capability explanations, and no duplicated authorization rules.
4. Run E2E at five widths/two themes plus axe and unauthorized links; expect exit 0.
5. Record evidence; commit `feat: add identity and team workspace surfaces` after authorization.

**Exit:** UI never infers access from mock/seeded state and every required route state is proven.


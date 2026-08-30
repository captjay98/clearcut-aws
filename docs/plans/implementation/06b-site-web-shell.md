# Public Site and Workspace Shell Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement truthful Astro public pages and the scoped TanStack workspace shell.  
**Architecture:** Astro is public; TanStack uses same-origin session bootstrap and generated clients.  
**Tech Stack:** Astro, TanStack Start/Router, design system.

---

**Files:** Create `apps/site/src/pages/index.astro`, `features.astro`, `docs.astro`, `apps/site/src/layouts/PublicLayout.astro`, `apps/web/src/routes/__root.tsx`, `apps/web/src/routes/o.$orgSlug.tsx`, `apps/web/src/components/navigation/`; test `apps/site/tests/public-pages.test.ts`, `apps/web/tests/e2e/shell.spec.ts`.

1. Add failing route, metadata, no-false-runtime-claim, session bootstrap, navigation, safe not-found, theme, and prototype-route exclusion tests.
2. Run site build and shell E2E; expect missing-route failures.
3. Implement mock-faithful public pages/shell, same-origin boundary, breadcrumbs, project rail, mobile navigation, skip link, live route heading, and favicon/metadata.
4. Run builds, route tests, five widths/two themes, and unknown routes; expect exit 0.
5. Record evidence; commit `feat: add public site and workspace shell` after authorization.

**Exit:** Public copy distinguishes prototype/demo from runtime proof and workspace scope is server-derived.


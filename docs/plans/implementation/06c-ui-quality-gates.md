# UI Accessibility, Browser, Visual, and Performance Gates Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Establish reusable production UI acceptance across browsers, assistive technology, widths, themes, print, and performance.  
**Architecture:** Route-state fixtures drive Playwright and visual assertions; generic galleries are excluded.  
**Tech Stack:** Playwright, axe, Chromium, Firefox, WebKit, Lighthouse or equivalent budgets.

---

**Files:** Create `apps/web/playwright.config.ts`, `apps/web/tests/fixtures/states.ts`, `apps/web/tests/e2e/ui-matrix.spec.ts`, `tests/ui/visual/`, `docs/UI_PERFORMANCE_BUDGETS.md`; modify `.github/workflows/ci.yml`.

1. Add failing matrix generation proving every `docs/UI_STATE_MATRIX.md` row maps to a test and screenshot fixture.
2. Freeze budgets for route JS, LCP/CLS/INP, long-list interaction, screenshot noise, and print pages.
3. Configure Chromium/Firefox/WebKit, axe, keyboard/focus, reduced motion, coarse pointer, five widths/two themes, visual and print suites.
4. Run `pnpm --filter @clearcut/web test:e2e -- ui-matrix`; expect exit 0 or a named accepted browser limitation with owner/date.
5. Record evidence; commit `test: add production ui quality matrix` after authorization.

**Exit:** A route cannot ship by passing only structural mock checks.


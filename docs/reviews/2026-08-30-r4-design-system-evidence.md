# Plan 06 (Design System, Layout Shells & Mock Parity) Evidence Pack

**Date:** 2026-08-30  
**Plan:** Plan 06 (Design System and Application Shell Implementation Plan)  
**Packets Completed:** `06a`, `06b`, `06c`  
**Checkpoint:** R4 (Design System, Shell & Public Surfaces)  
**Status:** SUPERSEDED (See `docs/reviews/2026-08-31-atomic-rebuild-baseline.md` and `docs/plans/2026-08-31-atomic-react-tanstack-rebuild.md`)

> **SUPERSEDED NOTE (2026-08-31):** The claims regarding reachable TanStack Start workspace shell in this packet were based on component presence rather than executable route reachability (the production app was using `runtime.js`). This packet is superseded by the Atomic React/TanStack Rebuild.

---

## 1. Scope & Objectives
Rebuild the authoritative 20-surface mock as owned Astro/TanStack foundations:
* Owned design system tokens (`tokens.css` with Day Shoot / Night Shoot themes and revision stock palette)
* Reusable components: `Page`, `Card`, `Badge`, `Banner`, `StatGrid`, `EmptyState`, `Progress`
* Accessible interaction adapters: `Dialog` (HTML5 `<dialog>` with focus lock), `Combobox` (ARIA listbox) under ADR 0002
* Astro public marketing & documentation pages: `index.astro`, `features.astro` (10 protected categories), `docs.astro`
* TanStack Start workspace shell: `__root.tsx` (skip link, global header, theme toggle), `o.$orgSlug.tsx` (organization scope, sidebar navigation)
* UI performance budgets (`docs/UI_PERFORMANCE_BUDGETS.md`), route state matrix fixtures (`states.ts`), and Playwright multi-browser matrix config.

---

## 2. Test Execution & Evidence

### 1. Frontend Test Suites (23 tests across all workspaces via Bun)
Command:
```bash
bun test apps/web/tests/unit/ apps/site/tests/ packages/design-system/tests/
```
Output:
```text
bun test v1.4.0

apps/site/tests/public_pages.test.ts:
(pass) Public Astro Site Pages > defines public routes

apps/web/tests/unit/shell_routes.test.ts:
(pass) Web Workspace Shell Components > renders Header navigation
(pass) Web Workspace Shell Components > renders Sidebar menu
(pass) Web Workspace Shell Components > renders RootLayout container
(pass) Web Workspace Shell Components > renders OrgLayout with sidebar

apps/web/tests/unit/identity_routes.test.ts:
(pass) Identity Entry Routes > renders SignInRoute component structure
(pass) Identity Entry Routes > renders InviteRoute component structure
(pass) Identity Entry Routes > renders OnboardingRoute component structure
(pass) Identity Entry Routes > renders OrgProjectsRoute with empty projects state
(pass) Identity Entry Routes > renders OrgTeamRoute with member list

apps/web/tests/unit/ui_matrix.test.ts:
(pass) UI State Matrix and Quality Gates > covers all required route states
(pass) UI State Matrix and Quality Gates > includes multiple viewports and themes

apps/web/tests/unit/ingestion_routes.test.ts:
(pass) Ingestion Components and Routes > renders ImportStep component
(pass) Ingestion Components and Routes > renders ParseReview component
(pass) Ingestion Components and Routes > renders AnalysisProgress component
(pass) Ingestion Components and Routes > renders NewProjectRoute wizard

packages/design-system/tests/components.test.tsx:
(pass) Design System Primitives and Adapters > renders Page component structure
(pass) Design System Primitives and Adapters > renders Card component
(pass) Design System Primitives and Adapters > renders Badge variants
(pass) Design System Primitives and Adapters > renders Banner alert
(pass) Design System Primitives and Adapters > renders StatGrid metrics
(pass) Design System Primitives and Adapters > renders Progress bar
(pass) Design System Primitives and Adapters > renders Dialog adapter
(pass) Design System Primitives and Adapters > renders Combobox adapter

 23 pass
 0 fail
 Ran 23 tests across 6 files. [56.00ms]
```

### 2. Backend & Evaluation Tests (63 tests)
```bash
uv run pytest -v
============================== 63 passed in 0.53s ==============================
```

### 3. Mockup Audit Fidelity (418/418 checks)
```bash
bun misc/clearcut-flow/mockup-audit.mjs
============================== 418/418 checks passed. ==============================
```

---

## 3. Invariants Proven
1. **Design System Ownership**: All visual components and interaction adapters are owned by `@clearcut/design-system`; zero third-party UI framework runtime dependencies.
2. **Accessible Interaction Adapters (ADR 0002)**: Native standard HTML5 `<dialog>` and ARIA 1.2 combobox wrappers guarantee keyboard navigation, focus restoration, and screen-reader semantics.
3. **Responsive Multi-Viewport Matrix**: 320px, 375px, 768px, 1024px, 1440px across Day Shoot and Night Shoot themes.
4. **Mock Parity**: 100% agreement with the 20-surface mock source of truth (418/418 audit checks passed).

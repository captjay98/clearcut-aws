# Design System and Application Shell Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rebuild the authoritative mock as ClearCut-owned Astro/TanStack foundations with exact visual vocabulary, accessibility, responsive behavior, and truthful state/data boundaries.

**Architecture:** `packages/design-system` owns components/tokens; feature code imports no visual/headless library directly. Astro owns public pages, TanStack Start owns the workspace, both consume generated contracts where needed.

**Tech Stack:** TanStack Start/Router, Astro, TypeScript, CSS custom properties, Vitest/Testing Library, Playwright/axe; one headless accessibility adapter only after proof.

---

**Depends on:** Plan 01; contract consumers from later plans integrate incrementally  
**Checkpoint:** R4

Resolve or explicitly accept DG-04, DG-06, DG-08, and DG-10 before declaring mock/production UI parity.

### Task 1: Snapshot mock requirements and close audit bookkeeping

**Files:** Create `packages/design-system/src/tokens.css`, `tests/ui/mock-contract.test.ts`, update living docs (not historical evidence) after explicit scope approval.

Parse the current mock audit output rather than hard-coding 366/418. Add tests for 20 canonical surfaces plus supporting renderers definition, shared wrapper/primitives, themes, spacing, navigation, print, and known M1–M8 gaps from the audit review. Generate route-state cases from `docs/UI_STATE_MATRIX.md`; the state gallery is never route proof.

### Task 2: Prove/select the interaction adapter

Create representative Dialog and Combobox adapters and SSR/hydration, DOM-fidelity, keyboard, focus restoration, screen-reader semantics, reduced-motion, bundle/treeshake, maintenance/license evidence. Reject or accept exactly one library in an ADR. Delete proof code for rejected candidates.

### Task 3: Implement tokens and primitives test first

**Files:** Create `Page`, `Section`, `Card`, `StatGrid`, `DataTable`, `EmptyState`, `Banner`, `TabsBar`, `Badge`, `Progress`, `Avatar`, Dialog/Drawer adapters and component tests.

```tsx
export function Page({ title, trail, actions, children }: PageProps) {
  return <main id="main-content">{/* shared composition */}</main>;
}
```

Preserve CSS/token geometry, text glyphs/shapes, Script/Night themes, focus, safe areas, reduced motion, and runtime-only inline values.

### Task 4: Implement public Astro surfaces

Build marketing/features/docs equivalents from the mock without claiming simulated calls as runtime evidence. Add metadata, canonical/OG/Twitter/favicon/robots/JSON-LD as appropriate. Correct stale excerpt/route-count documentation from current data.

### Task 5: Implement TanStack shell/router/state boundaries

Build same-origin session bootstrap, organization/project route scopes, sidebar/project rail/mobile navigation, breadcrumbs, route error/not-found boundaries, appearance persistence, skip link/live regions. Prototype sitemap/states are development-only routes guarded from production builds unless explicitly retained.

### Task 6: Verify visual/accessibility parity

Test 320/375/768/1024/1440, both themes, keyboard/focus, coarse pointer, reduced motion, no overflow, route announcements, unknown routes, and print isolation. Add screenshot/computed-style baselines with an explicit noise threshold.

```bash
node misc/clearcut-flow/mockup-audit.mjs
pnpm --filter @clearcut/design-system test
pnpm --filter @clearcut/web test:e2e -- ui-foundation
pnpm --filter @clearcut/site build
```

Expected: live mock audit summary passes; component/E2E/build commands exit 0 across the recorded theme/width matrix.

### Exit criteria

- Public and workspace shells compile independently.
- Feature code imports only ClearCut-owned primitives/generated client.
- Both themes and five widths pass no-overflow and visual checks.
- Accessibility adapter proof is accepted; no mixed/direct headless imports.
- M1–M8 are fixed or explicitly accepted with production tests.
- R4 does not claim domain/API completeness.

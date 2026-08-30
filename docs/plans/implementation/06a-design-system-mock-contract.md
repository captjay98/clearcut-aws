# Design System and Mock Contract Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Convert the authoritative mock vocabulary into owned tokens, primitives, adapters, and test fixtures.  
**Architecture:** Feature code imports only `@clearcut/design-system`; one selected headless library remains behind owned adapters.  
**Tech Stack:** TypeScript, CSS custom properties, Vitest, Testing Library.

---

**Files:** Create `packages/design-system/src/tokens.css`, `src/index.ts`, `src/components/`, `src/adapters/dialog.tsx`, `src/adapters/combobox.tsx`, `tests/ui/mock-contract.test.ts`, `docs/adr/0002-headless-adapter.md`; test `packages/design-system/src/**/*.test.tsx`.

1. Add failing computed-style/DOM/accessibility tests for shared primitives, two themes, spacing, focus, reduced motion, and the 20-surface/state contracts.
2. Run the mock audit and design-system tests; capture live total and expected missing-component failures.
3. Complete Dialog/Combobox proof, select one library in ADR 0002, and implement minimal owned components matching mock markup/tokens.
4. Run mock audit, component tests, bundle/SSR/hydration/license checks; expect exit 0 and no direct feature-library imports.
5. Record evidence; commit `feat: add mock derived design system` after authorization.

**Exit:** M1–M8 are fixed or explicitly accepted; no check count is hard-coded.


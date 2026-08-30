# ADR 0002: Native HTML5 & Standard ARIA Accessible Interaction Adapters

## Status
Accepted

## Context
ClearCut requires robust accessible primitives (modals/dialogs, dropdowns/comboboxes, tab bars) that function across light and dark themes, obey strict focus locks and keyboard accessibility, and execute cleanly during SSR/hydration without adding large third-party runtime bundles.

## Decision
ClearCut adopts standard HTML5 `<dialog>` and ARIA 1.2 compliant TypeScript wrappers located strictly in `packages/design-system/src/adapters/`. Feature code never imports external UI libraries directly.

## Consequences
- Single ownership of all visual components and interaction adapters in `@clearcut/design-system`.
- Zero third-party runtime dependencies for accessibility primitives.
- SSR and hydration safety verified by unit tests.

---
name: mock-to-tanstack
description: Implements ClearCut's authoritative mock UI as production TanStack Start components while preserving visual fidelity, themes, responsive behavior, accessibility, states, print behavior, and the boundary around approved headless accessibility primitives. Use when building or reviewing ClearCut workspace UI, extracting components from misc/clearcut-flow, or deciding whether a UI dependency fits the design system.
---

# Mock-to-TanStack

Translates the ClearCut mock prototype into production TanStack Start components. The mock is the visual and interaction source of truth; production implements its patterns faithfully.

## Source of Truth

- **Location:** `misc/clearcut-flow/`
- **Surfaces:** 20 complete screens covering the full product.
- **Themes:** Script (light, cream tones) and Night shoot (dark, amber/gold accents).
- **Responsive:** 320–1440px; sidebar collapses to mobile bottom nav + drawer below tablet.
- **Baseline gate:** `node misc/clearcut-flow/mockup-audit.mjs` — 366 structural checks, zero regressions allowed.

Inspect the matching mock surface and its shared primitives before implementing any production component. Do not redesign; implement.

## Public Component Vocabulary

ClearCut owns these component APIs. Application features import only these names:

- `Page` — breadcrumb, eyebrow, title, lede, actions, notice, body.
- `Section` — titled content region.
- `Card` — surface with header, content, footer.
- `StatGrid` — metric cards with semantic state classes.
- `DataTable` — sortable, filterable tabular data.
- `EmptyState` — icon, description, and single clear next action.
- `Banner` — contextual notice with optional dismiss.
- `TabsBar` — horizontal tab navigation.
- `Badge` — status indicator with semantic variants.
- `Progress` — determinate and indeterminate progress.
- `Avatar` — user identity with fallback.

Map repeated mock patterns to the shared design-system package (`packages/design-system/`). New primitives follow the same ownership model.

## Implementation Order

Use this hierarchy for every interactive element:

1. **Semantic native HTML and CSS.** Buttons, links, inputs, tables, progress, and straightforward disclosures use browser elements directly.
2. **ClearCut-owned component using native behavior.** When the mock defines a pattern that native HTML covers, wrap it in a ClearCut component for consistency without adding a dependency.
3. **ClearCut-owned adapter around the approved headless accessibility library.** Use this only when native behavior is insufficient for complex interactions: dialogs with focus trapping, menus, popovers, listboxes, and comboboxes.

**Incorrect — feature code imports a headless primitive directly:**

```tsx
// ❌ Do not import headless primitives in feature code.
import { Dialog as HeadlessDialog } from "@some-headless-lib/react";

export function EvidenceDetailModal({ item }: Props) {
  return (
    <HeadlessDialog open={item.isOpen} onClose={item.close}>
      <h2>{item.name}</h2>
    </HeadlessDialog>
  );
}
```

**Correct — feature code imports only the ClearCut adapter:**

```tsx
// ✅ Import the ClearCut-owned Dialog component.
import { Dialog, DialogTitle, DialogBody } from "@clearcut/design-system";

export function EvidenceDetailModal({ item }: Props) {
  return (
    <Dialog open={item.isOpen} onClose={item.close}>
      <DialogTitle>{item.name}</DialogTitle>
      <DialogBody>
        {/* Evidence content */}
      </DialogBody>
    </Dialog>
  );
}
```

The adapter's internal use of a headless library is an implementation detail that does not leak into feature code.

## Dependency Boundary

- **No shadcn** — no CLI, registry, presets, component vocabulary, or companion packages.
- **No external visual component library** — no pre-styled component system dictates ClearCut's markup or tokens.
- **No Tailwind assumption** — the production system uses mock-derived CSS custom properties and token classes.
- **No icon-library substitution** — icons are text glyphs and CSS shapes as defined by the mock.
- **No direct headless imports in feature code** — all headless behavior is wrapped in `packages/design-system/` adapters.
- **No mixing headless systems** — select exactly one approved headless library; do not combine React Aria, Base UI, and Radix across surfaces.
- **No headless package is approved merely by this skill** — selection requires a compatibility proof against TanStack Start SSR/hydration, mock DOM structure, keyboard behavior, screen-reader semantics, reduced motion, bundle size, and licensing.

## State and Governance Requirements

Every production surface must implement these states using ClearCut-owned components:

| State | Implementation |
|-------|---------------|
| Loading | Structural skeleton + spinner via `Progress` or dedicated skeleton component. |
| Empty | `EmptyState` with icon, description, and one clear next action. |
| Recoverable error | Error message adjacent to the failed action with a retry affordance. |
| Permanent error | Explanation of why the action cannot succeed. |
| Success | Confirmation feedback appropriate to the action. |
| Not-found | Names the identifier the user typed; does not silently fall back. |

Capability-gated controls remain focusable and describe their restriction — they are never hidden.

## Accessibility

- WCAG 2.1 AA minimum. Contrast tokens meet AA on their own backgrounds.
- Keyboard navigable with visible focus styles on every interactive element.
- Dialog focus trapping and background inertness (`inert` attribute).
- Focus restoration when dialogs, drawers, and popovers close.
- Skip link, landmarks (`<nav>`, `<main>`, `<aside>`), and live regions (`aria-live`).
- Coarse-pointer touch targets: 44px minimum.
- `safe-area-inset` for fixed mobile controls.
- `prefers-reduced-motion`: disable or simplify all animation.

An adapter failure must surface as a typed development error, not silently degrade keyboard or focus behavior.

## Motion and Layout

- Animate only when the product design requires it. No decorative motion.
- Use compositor properties only: `transform` and `opacity`.
- Never animate layout properties (`width`, `height`, `top`, `left`, `margin`, `padding`).
- Pause off-screen looping activity.
- No persistent `will-change` outside an active animation.
- Use a documented, fixed stacking scale — no arbitrary z-index values.
- No inline margin, padding, or gap — geometry lives in the stylesheet via spacing tokens (`--space-1` through `--space-16`).
- Exception: runtime-computed values (score percentage, progress width, stock color) may use inline styles.

## Responsive and Print Parity

- **Responsive:** single column below tablet; sidebar collapses to mobile bottom nav + drawer. Grid primitives (`grid-2`, `grid-3`, `grid-sidebar`) adapt across breakpoints.
- **Print:** report page uses print isolation. App chrome is hidden. Exhibits do not split across pages. Only the four approved `!important` rules apply (visibility, screen-reader clip, reduced motion, print chrome).

## Workflow

1. **Before implementation:** read the matching mock surface in `misc/clearcut-flow/` and identify shared primitives, token usage, state handling, and responsive behavior.
2. **Map to components:** translate mock render functions to ClearCut-owned React components. Preserve the `Page` wrapper pattern — every surface renders through it.
3. **Extract shared patterns:** repeated patterns become design-system primitives in `packages/design-system/`.
4. **Theme compliance:** verify both Script and Night shoot themes render correctly using CSS custom properties scoped to `:root`.
5. **State completeness:** implement all six required states for the surface.
6. **Do not redesign:** if the mock defines a pattern, implement it. Design changes go through the mock first.

## Verification

- **Mock baseline:** `node misc/clearcut-flow/mockup-audit.mjs` must pass 366/366 checks. This validates the prototype, not production components.
- **Production checks** (when targets exist): component tests, Playwright accessibility tests, keyboard/focus integration tests, responsive snapshot tests, and theme-switching coverage.
- **Adapter isolation:** confirm no feature-level imports of the approved headless library exist outside `packages/design-system/`.
- **Visual parity:** all 20 surfaces match the mock across both themes and 320–1440px.

---
name: ui-audit
description: Use before shipping or reviewing ClearCut web surfaces for mock fidelity, accessibility, responsive behavior, state completeness, and production readiness.
---

# ClearCut UI Audit

Audit behavior and visual fidelity against `misc/clearcut-flow/`, the authoritative prototype. Do not redesign the vocabulary or introduce an external component system.

## ClearCut Overrides

- Use the Script and Night shoot theme tokens, custom primitives, text glyphs, and CSS shapes from the mock.
- Do not add shadcn, Radix, an icon package, or ad-hoc inline geometry.
- Preserve the two-layer navigation, `page()` wrapper, token spacing, mono technical values, and runtime-only inline values.

## Accessibility

- Keyboard navigation reaches every interactive control; focus is visible and dialogs trap and restore focus.
- Use semantic controls, accessible names, live regions, linked form errors, and `aria-busy`/status text for async work.
- Meet WCAG 2.1 AA contrast and 44px coarse-pointer targets.
- Respect reduced motion and keep landmarks and skip navigation intact.

## Responsive and Visual Fidelity

- Verify 320px, 375px, 768px, 1024px, and 1440px with no horizontal overflow.
- Confirm sidebar-to-mobile navigation behavior, both themes, sticky surfaces, hover/focus states, and print isolation.
- Use the mock's cards, banners, tabs, badges, progress, tables, and empty-state patterns rather than one-off replacements.

## State Completeness

Every surface handles loading, empty, recoverable error with retry, permanent error, success, and not-found states. Not-found states identify the requested hash or resource. Capability-gated controls remain focusable and explain their restriction.

## Production Readiness

- Run the mock audit (`node misc/clearcut-flow/mockup-audit.mjs`) and relevant Playwright accessibility/responsive coverage.
- Check async content for layout stability, useful feedback, and no unnecessary re-renders.
- Confirm evidence excerpts and technical values are readable without implying legal certainty.
- Keep app chrome out of printed reports and prevent exhibits from splitting across pages.

# ClearCut UI Primitive Strategy

**Date:** 2026-08-28  
**Status:** Approved  
**Scope:** Production TanStack Start workspace and canonical agent guidance

## Decision

ClearCut will implement the completed mock as a custom visual system in TanStack Start. ClearCut owns the public component API, markup, CSS, tokens, states, and visual behavior. Native HTML is the default implementation substrate. One approved headless accessibility library may be used only behind ClearCut-owned adapters for interaction behavior that is costly or risky to implement correctly, such as dialog focus management, menus, popovers, listboxes, and comboboxes.

ClearCut will not adopt shadcn as its component system. It will not use shadcn registries, presets, CLI workflows, component vocabulary, Tailwind conventions, icon libraries, or required companion packages as production architecture.

## Context

The authoritative design source is `misc/clearcut-flow/`: 20 surfaces, Script and Night shoot themes, responsive layouts from 320–1440px, complete state patterns, print behavior, and a 366-check structural audit. TanStack Start and TanStack Router do not require a component library, so the production framework does not create a reason to adopt shadcn or Base UI as the visual architecture.

The vendored `shadcn` skill is tightly coupled to shadcn CLI commands, registries, Tailwind, Base UI or Radix APIs, icon packages, Sonner, and shadcn-specific composition. The vendored `baseline-ui` skill also mandates Tailwind, `motion/react`, `tw-animate-css`, `cn()` backed by `clsx` and `tailwind-merge`, and Base UI, React Aria, or Radix. Those mandates conflict with the approved mock-derived system even though some framework-neutral baseline guidance remains useful.

## Architecture

### Public component boundary

Application code consumes ClearCut-owned components, including:

- `Page`
- `Section`
- `Card`
- `StatGrid`
- `DataTable`
- `EmptyState`
- `Banner`
- `TabsBar`
- `Badge`
- `Progress`
- `Avatar`

These components preserve the mock's vocabulary and expose product-level semantics rather than third-party primitive APIs. Application features must not import an approved headless library directly.

### Implementation hierarchy

Use the following order:

1. Semantic native HTML and CSS.
2. A ClearCut-owned component using native behavior.
3. A ClearCut-owned adapter around the single approved headless accessibility library when native behavior is insufficient.

The headless dependency is an implementation detail. It must not dictate styling, token names, component names, iconography, page composition, or application imports.

### Headless-library selection

React Aria is the first candidate because accessibility behavior is its primary concern, but it is not approved automatically by this design. Before adding a dependency, validate a representative dialog and combobox against:

- TanStack Start SSR and hydration behavior
- required DOM structure and mock fidelity
- keyboard behavior and focus restoration
- screen-reader semantics
- reduced-motion behavior
- package size and tree-shaking
- maintenance health and licensing

Select exactly one headless system. Do not mix React Aria, Base UI, and Radix across surfaces.

### Styling and icons

The production system uses mock-derived CSS custom properties, spacing tokens, layout primitives, semantic state classes, and the two approved themes. It does not require Tailwind. Icons remain text glyphs or CSS shapes unless a later approved design explicitly changes that decision.

## Accessibility and interaction rules

The ClearCut-specific guidance will preserve these useful framework-neutral constraints from `baseline-ui`:

- prefer native semantics and never hand-roll complex interaction behavior without justification;
- use visible focus styles, keyboard navigation, focus restoration, dialog focus trapping, and background inertness;
- provide 44px coarse-pointer targets and safe-area handling for fixed mobile controls;
- animate only when the product design requires it, prefer compositor properties, and honor reduced motion;
- use structural skeletons for loading states and place recoverable errors next to the triggering action;
- use a documented stacking scale and avoid arbitrary z-index values;
- pause off-screen looping activity and avoid persistent `will-change`;
- preserve paste behavior in inputs and textareas.

These rules will be expressed in ClearCut terminology without Tailwind, shadcn, Base UI, Radix, React Aria, or animation-package mandates.

## Agent skill disposition

Delete the six incompatible vendored catalog skills:

- `.agents/skills/baseline-ui/`
- `.agents/skills/financial-patterns/`
- `.agents/skills/frontend-design/`
- `.agents/skills/multi-currency/`
- `.agents/skills/neon-postgres/`
- `.agents/skills/shadcn/`

Replace the two UI-oriented skills with one active ClearCut-specific `mock-to-tanstack` skill. It will instruct agents to:

- treat `misc/clearcut-flow/` as the visual and interaction source of truth;
- map mock primitives to ClearCut-owned React components;
- preserve both themes, responsive behavior, all required states, capability-gated controls, and print behavior;
- prefer native semantics and isolate any approved headless dependency behind adapters;
- prohibit shadcn, external visual component libraries, direct primitive imports, Tailwind assumptions, and icon-library substitutions;
- verify production behavior separately from the mock's structural audit.

Update `.agents/profile.toml`, skill manifest/catalog metadata, steering, and generated `.kiro/` output so the canonical and generated inventories remain consistent.

## Error and state handling

Every production surface must implement loading, empty, recoverable error, permanent error, success, and not-found states using ClearCut-owned components. Errors stay adjacent to the failed action where possible. Capability-gated controls remain focusable and explain their restriction. A headless adapter failure must surface as a typed development error rather than silently degrading keyboard or focus behavior.

## Verification

The production rebuild will verify:

- visual and interaction parity for all 20 surfaces;
- Script and Night shoot themes;
- responsive behavior from 320–1440px;
- keyboard operation, focus order, focus trapping, and focus restoration;
- landmarks, accessible names, live regions, and screen-reader semantics;
- reduced motion and coarse-pointer targets;
- loading, empty, error, success, and not-found states;
- capability-gated controls;
- report print isolation and page-break behavior;
- absence of direct headless-library imports outside approved adapters.

The existing command `node misc/clearcut-flow/mockup-audit.mjs` remains the structural baseline check for the prototype. Production component, accessibility, and Playwright tests are separate checks when their target suites exist.

## Consequences

This approach preserves exact ClearCut identity while avoiding unnecessary reimplementation of the hardest accessibility behaviors. It adds a small adapter layer and requires disciplined dependency boundaries, but avoids shadcn-driven design drift and avoids coupling application features to third-party component APIs.

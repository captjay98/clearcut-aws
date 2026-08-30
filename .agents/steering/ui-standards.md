# UI Standards

## Design Source of Truth
The mock UI prototype at `misc/clearcut-flow/` is the authoritative visual identity. The production app implements its patterns — it does not redesign from scratch. The mock has 20 surfaces, 366 structural audit checks, two themes, responsive from 320–1440px, and zero axe-core violations.

## Themes
- **Script** (light): Typewriter ink on cream stock. Warm backgrounds, dark text, blue accents.
- **Night shoot** (dark): Amber flags on charcoal pages. Near-black surfaces, amber/gold accents.
- Theme tokens are scoped to `:root` via CSS custom properties. Every surface renders correctly in both themes.

## Component Library
- Custom ClearCut-owned components built from the mock's primitives: `Page`, `Section`, `Card`, `StatGrid`, `DataTable`, `EmptyState`, `Banner`, `TabsBar`, `Badge`, `Progress`, `Avatar`.
- The mock defines the visual vocabulary. No external visual component library (no shadcn, no pre-styled system).
- Native HTML is preferred. At most one explicitly approved headless accessibility library may be used for complex interaction behavior (dialogs, menus, popovers, listboxes, comboboxes). It must be isolated behind ClearCut-owned adapters in `packages/design-system/`; feature code must not import it directly. Multiple headless primitive systems must not be mixed.
- Icons are text glyphs and CSS shapes, not an icon library.

## Spacing
- Token-based spacing scale: `--space-1` through `--space-16`.
- Card padding, grid gaps, and section rhythm all use tokens.
- No inline margin, padding, or gap. Geometry lives in the stylesheet.

## Typography
- System font stack (Inter-like). Mono for IDs, timestamps, and technical values.
- `.small` for secondary text, `.muted` for de-emphasized, `.mono` for technical.

## Layout
- Two-layer navigation: sidebar (org/project) + breadcrumb trail.
- `page()` wrapper for every surface — breadcrumb, eyebrow, title, lede, actions, notice, body.
- Grid primitives: `grid-2`, `grid-3`, `grid-sidebar`.
- Responsive: single column below tablet, sidebar collapses to mobile bottom nav + drawer.

## Color Patterns
- `is-success` (green), `is-warning` (amber), `is-danger` (red), `is-accent` (blue) — used on badges, banners, stat cards, and borders.
- `color-mix()` for hover states. `box-shadow: inset` for left-border accents (avoids layout shift).
- `backdrop-filter: blur` on sticky elements (header, exhibit nav).

## Accessibility
- WCAG 2.1 AA minimum. Contrast tokens meet AA on their own backgrounds.
- Keyboard navigable. Visible focus styles. `reduced-motion` support.
- Skip link, landmarks, live regions (`aria-live`), dialog focus trapping, background inertness.
- Coarse-pointer touch targets (44px minimum).

## States
Every surface must handle: loading (skeleton + spinner), empty (icon + description + action), error (recoverable with retry, permanent with explanation), success, and not-found (names the hash typed).

## Print
- Report page is marked for print isolation. App chrome is hidden. Exhibits don't split across pages.
- Only 4 `!important` rules: visibility, screen-reader clip, reduced motion, print chrome.

## Rules
- No inline styles except runtime-computed values (stock color, score percentage, progress width).
- No `!important` in the marketing/app layer.
- One page wrapper (`page()`), written in one place. Every render function returns through it.
- Capability-gated controls are focusable and describe their restriction — never hidden.

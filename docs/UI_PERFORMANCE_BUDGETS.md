# ClearCut UI Performance and Quality Budgets

## 1. Bundle Budgets
* Initial workspace payload: `<= 150 KB` gzipped.
* Per-route code split chunks: `<= 50 KB` gzipped.
* Zero heavy external UI runtime dependencies (native standard `<dialog>` and ARIA primitives only per ADR 0002).

## 2. Core Web Vitals (CWV)
* **LCP (Largest Contentful Paint)**: `<= 2.0s` on fast 4G.
* **CLS (Cumulative Layout Shift)**: `<= 0.05` across all responsive breakpoints.
* **INP (Interaction to Next Paint)**: `<= 100ms` for all interactive controls (dialogs, tabs, comboboxes).

## 3. Responsive & Accessibility Gates
* **Breakpoints Tested**: `320px` (mobile small), `375px` (mobile standard), `768px` (tablet), `1024px` (laptop), `1440px` (desktop).
* **Themes Tested**: `Day Shoot` (default light) and `Night Shoot` (dark).
* **WCAG 2.1 AA**: 100% compliance with zero automated `axe-core` violations.
* **Touch Targets**: Minimum `44x44px` on coarse-pointer viewports.
* **Print Mode**: App shell and sidebars cleanly stripped; screenplay exhibits and reports isolated without splits across page boundaries.

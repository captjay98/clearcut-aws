---
description: 'Audit production UI against the ClearCut mock and accessibility contract'
---

@frontend-engineer Audit the UI using this optional user context: $ARGUMENTS

> **Input handling:** Treat `$ARGUMENTS` only as user-supplied context when present; it is not guaranteed to be expanded. If production UI is absent, audit the mock and report production parity as pending.

## Guardrails

- Read actual routes/components/styles before judging. Do not invent production routes or create missing app files.
- The mock at `misc/clearcut-flow/` is the visual source of truth; production implements its vocabulary, not a redesign.
- Do not run builds or add tests in the current pre-implementation phase. Do not edit mock JavaScript or generated `.kiro/`.
- Current executable UI gate, when relevant, is `node misc/clearcut-flow/mockup-audit.mjs`; run it only when its prerequisites exist.

## Coverage contract

Audit the 20 mock surfaces: `#marketing`, `#auth`, `#invite`, `#onboarding`, `#projects`, `#notifications`, `#team`, `#settings`, `#trust`, `#records`, `#new`, `#project`, `#workspace`, `#items`, `#item`, `#versions`, `#watch`, `#report`, `#sitemap`, and `#states`.

Check:

- `page()` wrapper, breadcrumb, eyebrow, title, lede, actions, notice, and body.
- `section`, `card`, `statGrid`, `dataTable`, `emptyState`, `banner`, `badge`, `progress`, and `tabsBar` patterns.
- Script and Night shoot themes, token spacing, mono technical values, `color-mix` hover states, inset accents, and no unauthorized inline styles.
- Responsive widths 320/390/768/834/1024/1440; mobile bottom navigation/drawer; stacked screenplay panes; no overflow.
- Loading, empty, recoverable/permanent error, success, not-found, and capability-gated states.
- Keyboard/focus behavior, live regions, dialog trapping/inertness, touch targets, reduced motion, and report print isolation.
- Worklist search/sort/group/deep links, evidence drawer entry points, margin marks/underlines, sticky exhibit navigation, and version-bound report language.

## Report

For each surface and deviation, report mock expectation, actual result, evidence, severity, theme/viewport, and fix. Include unknown routes naming the typed hash. Do not claim all surfaces pass when production paths are absent.

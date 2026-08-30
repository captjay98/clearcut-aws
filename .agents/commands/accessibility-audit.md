---
description: 'Audit accessibility against the ClearCut design contract'
---

@frontend-engineer Audit ClearCut accessibility using this optional user context: $ARGUMENTS

> **Input handling:** Treat `$ARGUMENTS` only as user-supplied context when present. It is not guaranteed to be expanded by the command runner. If it is empty or literal, ask for the target and continue with repository evidence.

## Guardrails

1. Read the repository state and identify the actual app, route, test, and mock paths before running anything.
2. This repository is currently pre-implementation. Do not invent `apps/`, `services/`, `packages/`, Playwright configs, routes, or test files. If a target is absent, record **not applicable — prerequisite absent** and do not create it.
3. The current executable design gate is the mock audit, when its script exists:

   ```bash
   node misc/clearcut-flow/mockup-audit.mjs
   ```

   Run it only when the mock has not been modified or when the audit is explicitly requested; do not test mock JavaScript as production behavior.
4. Do not add tests as part of this command. Do not change generated `.kiro/` output. Report suggested tests separately.

## Audit matrix

The mock defines **20 surfaces × 2 themes = 40 surface-theme combinations**. Do not report 48 views: dialogs are interaction states within those surfaces, not additional surfaces. Track the eight dialog states separately and name each one audited.

For every available production surface and each Script and Night shoot theme, check:

- Semantic landmarks and one useful page title.
- Keyboard reachability, visible focus, skip link, and no focus traps.
- Dialog `aria-modal`, labelled title, focus return, and background inertness.
- Form labels, field descriptions, recoverable errors, and status announcements.
- `aria-live` for search results, run progress, toasts, and async errors.
- Tables with caption, header cells, scope, and keyboard-safe sorting.
- Capability-gated controls remain focusable and explain their restriction.
- Contrast, non-color status cues, zoom/reflow to 200%, and coarse-pointer targets of at least 44px.
- Reduced motion behavior and no content loss at 320px through 1440px.

## Phase-gated manual checks

When a runnable surface, supported assistive technology, and an authorized test target exist:

- **VoiceOver/screen-reader golden path** — on macOS use VoiceOver to navigate landing → sign in → project → flags → flag detail → verify evidence → report. Record reading order, landmarks, focus movement, control names, announcements, dialog focus return, and live-region updates. Use the equivalent configured screen reader when the target platform is not macOS.
- **Forced-colors/high-contrast** — enable the platform/browser forced-colors or high-contrast mode and inspect both themes across available surfaces. Verify text, status cues, borders, focus indicators, disabled/capability-gated explanations, dialogs, tables, and controls remain perceivable without relying on color or background imagery.

If the surface, assistive technology, forced-colors mode, or documented runner is absent, report each manual check separately as **not applicable — prerequisite absent**; do not infer a pass from axe or the mock structural audit.

## Available checks

Use only checks whose prerequisites exist. Prefer repository-defined scripts over guessed commands. If a configured E2E/a11y suite exists, run its documented command; do not invoke an undeclared package runner or create a config to make a command work. If no production app exists, audit the mock structure only and mark production checks pending.

## Report

Return a table with target, prerequisite, command/manual evidence, result (`pass`, `fail`, or `not applicable`), and follow-up. For every failure include surface, element, WCAG criterion, severity, reproduction, and minimal fix. Include the 40-combination matrix count and the separately tracked dialog states, plus the VoiceOver/screen-reader and forced-colors/high-contrast status. Do not claim the production app passes based only on the mock audit.

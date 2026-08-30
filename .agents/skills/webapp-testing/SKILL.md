---
name: webapp-testing
description: Test ClearCut local web behavior with the repository's configured Playwright suite, including responsive, accessibility, role, evidence-state, and print workflows.
license: Complete terms in LICENSE.txt
---

# Web Application Testing

Use the repository's TypeScript Playwright suite as the primary path. When the workspace exists, run the configured `pnpm test:e2e` command and rely on Playwright's `webServer` configuration to start required services. Do not invent ports, package filters, or startup commands before Plan 01 creates the manifests.

## ClearCut Coverage

- Mock fidelity across the 20 planned surfaces and both Script/Night shoot themes.
- Responsive behavior from 320–1440px, including mobile navigation and 44px coarse-pointer targets.
- Keyboard order, visible focus, dialog trapping/restoration, landmarks, live regions, and reduced motion.
- Fixed-role capability boundaries and focusable restricted controls.
- Loading, empty, error, success, and applicable not-found states.
- Evidence provenance/conflict visibility and zero-evidence unresolved states.
- Governed actions that cannot complete before human approval.
- Report print isolation, version binding, and exhibit pagination.

## Workflow

1. Confirm the real workspace and Playwright configuration exist. If absent, report the Plan 01 prerequisite instead of scaffolding an ad hoc runner.
2. Start from the configured `pnpm test:e2e` project and existing fixtures.
3. Use role/label/test-id locators; do not bind tests to styling details.
4. Monitor page errors, failed requests, and unexpected console errors.
5. Capture screenshots/traces only where they improve diagnosis or form an approved visual baseline.
6. Preserve real provenance in recorded Parallel fixtures; never fabricate evidence to satisfy an assertion.
7. Report the exact command, project/browser, viewport, and pass/fail output.

## Optional Python Probe

For a one-off static artifact probe only, the canonical helper is `.agents/skills/webapp-testing/scripts/with_server.py`. Run `python3 .agents/skills/webapp-testing/scripts/with_server.py --help` first. Do not substitute this helper for the configured TypeScript E2E suite or use it to define production test architecture.

## Anti-patterns

- Arbitrary sleeps instead of locator assertions or condition-based waits.
- CSS selectors coupled to visual implementation when semantic locators exist.
- Live paid-provider calls in deterministic E2E.
- Uncited static Parallel responses.
- Starting guessed servers or creating a second Playwright configuration.
- Claiming browser coverage when only the mock structural audit ran.

## Reference Files

The bundled `examples/` and helper script are optional references for focused probes. Project E2E conventions and the current Playwright configuration take precedence.

# UI Plan-to-Mock Audit — 2026-08-30

## Verdict

**NOT FULLY CLOSED.** The prototype is strong and structurally healthy, but “418/418” does not mean every approved UI requirement is represented. All 20 canonical surfaces render and the majority of the correction lists have been incorporated. Residual semantic, state, and documentation gaps remain and are assigned to active production plans; this docs-only pass did not change the mock.

## Scope and evidence

Reviewed:

- all approved UI design documents in `docs/plans/`;
- `product-plan.md`, `feature-ledger.md`, the planning baseline, and submission strategy;
- `misc/clearcut-flow/index.html`, `assets/app.js`, `assets/app.css`, README, and audit script;
- recent mock commits through repository `HEAD` at the time of review;
- all 20 canonical routes in a fresh Chromium browser sweep.

Commands and results:

```bash
node misc/clearcut-flow/mockup-audit.mjs
# 418/418 checks passed.
```

Browser spot sweep:

- 20/20 routes rendered exactly one `<main>` and a non-empty `<h1>` at 1440x1000 and 320x844.
- 20/20 routes had no horizontal document overflow at those widths.
- Night shoot at 320x844 also had no horizontal document overflow on all 20 routes.
- Browser page-error collection was empty.

This was not a fresh axe, assistive-technology, Safari/Firefox, printed-PDF, screenshot-diff, or full end-to-end interaction pass. The 2026-08-28 record contains broader historical checks but is stale: it says 366/366 while the live audit is 418/418 and predates later mock commits.

## Surface-plan coverage

| Approved design | Surfaces | Mock coverage | Verdict |
|---|---|---|---|
| Identity & organization entry | auth, invite, onboarding, projects | resolver outcomes, invitation records/states, role/project scope, creation gate, and access states are represented | Strong; production-only auth/security semantics remain |
| Project creation & ingestion | new | three steps, modes, drop-target treatment, parse notes, timed phases, cancellation, and progress are represented | Partial; actual file input/drop behavior and some per-format/state proof are absent |
| Evidence workspace | project, workspace, items, item | addressable items, not-found, filter context, adaptive drawer, version binding, comments/replies/history/mentions, bulk actions, print and gating are represented | Strong; complete per-surface state matrix is not proven |
| Revision, monitoring & report | versions, watch, report | maker/checker rewrite, computed re-scan, failures, materiality, follow-up, frozen snapshot and separate release state exist | Partial; stale release-dialog copy fuses generation and release |
| Notifications | notifications | event templates, tiers, structured destinations, filters, project labels, `<time>`, access-aware blocking and self-exclusion exist | Partial; contextual push-permission banner and complete route states are not demonstrated |
| Team & settings | team, settings | tabs, member actions, invitation lifecycle, role/access review, governance lifecycle, retention/deletion and integrations are represented | Strong; production authorization and atomicity remain server obligations |
| Trust & Records | trust, records | ten-dimension rubric, gate separation, selectable evaluations, redaction boundary, URL-addressable views, operations and deletion semantics are represented | Strong; browser receipts remain simulations, not authoritative audit records |
| UI primitive strategy | all | shared wrappers/primitives, tokens, themes, responsive navigation, focus handling, print isolation and dependency intent are represented | Strong; production component/adaptor proof does not exist yet |
| Public/prototype surfaces | marketing, sitemap, states | all are implemented in the mock | Planning gap closed by `docs/UI_SURFACE_CONTRACT.md`; sitemap/states remain prototype-only |

## Residual mock gaps

### M1 — release attestation copy still fuses generation and release

The report surface now has a correct frozen-snapshot state and a separate Release button, but the dialog opened by Release still says “Generate and release the clearance report?” and its confirm button says “Generate & release.” This contradicts the approved two-phase lifecycle and could teach an implementation agent the wrong command semantics.

Observed prototype snippet:

```js
title: proj().dossier ? 'Export record' : 'Generate and release the clearance report?',
// ...
`<button ... data-action="confirm-dossier">Generate &amp; release</button>`
```

Expected future mock wording: “Release this frozen snapshot?” and “Release report.” The action must continue to call release only; it must not regenerate.

### M2 — ingestion has a simulated chooser, not an actual file input/drop interaction

The approved plan asked for a file input and drop target. The mock renders a keyboard-reachable button styled as a drop target and then seeds a format-specific file when activated. That communicates the intended composition but does not exercise file selection, drag/drop, extension/MIME/size client checks, or invalid-file focus behavior.

This is acceptable as a disclosed simulation only if production Plan 03 treats it as visual guidance—not behavioral proof.

### M3 — notifications lacks the planned contextual push-permission banner

Push preference and `Notification.requestPermission()` are represented under Settings. The inbox quotes the preference, but its approved contextual permission-prompt banner is not present as an inbox state. Plan 09 owns the production state and any later mock correction.

### M4 — per-surface state completeness is asserted more broadly than it is demonstrated

The `#states` gallery documents generic loading, empty, error, and not-found patterns, and several routes expose special states through data/query controls. That is not equivalent to every surface demonstrating all applicable loading, empty, recoverable error, permanent error, success, stale/redacted, and access-safe not-found states. Production plans must enumerate and test states route by route.

### M5 — documentation and generated guidance still cite 366 checks

The following source material still uses 366 as the baseline even though the current audit is 418:

- `docs/2026-08-28-mock-ui-verification.md` (historical record);
- `.agents/skills/mock-to-tanstack/SKILL.md`;
- `.agents/skills/quality-gates/SKILL.md`;
- `.agents/steering/agents.md` and product-map guidance;
- `docs/plans/2026-08-28-clearcut-ui-primitive-strategy-design.md`.

Do not rewrite historical evidence to pretend it was run later. Update living guidance in a separately authorized canonical `.agents` change, regenerate consumers, and preserve the dated record as history.

### M6 — README excerpt count appears stale

The mock README says the workspace ends with “3 of 43 scenes,” while the verification record and current dataset describe a seven-scene excerpt. Production Plan 06 must derive public/documentation claims from the current mock data or explicitly correct the documentation baseline.

### M7 — supporting route count needs one documented definition

The audit reports 20 canonical routes while the renderer registry also contains marketing variants, features, docs, and resolver renderers. This is valid, but agents need one rule: report 20 canonical product/review surfaces; describe supporting renderers separately. `docs/UI_SURFACE_CONTRACT.md` now establishes that definition.

### M8 — favicon request returns 404 in a fresh local browser run

The page rendered correctly, but `/favicon.ico` returned 404. This is not a workflow failure; Plan 06 owns metadata/icon completeness and should verify it with the future site assets.

## Requirements implemented since the UI plans were written

The design documents' “still required” sections are historical. Current source and audit evidence show later implementation of, among other items:

- stable `#item?id=` addressing and access-safe not-found;
- filter-context item navigation, source counts, adaptive drawer, version binding, bulk operations, threaded discussion, edit history, mentions, action entries, and item print;
- organization resolver, five invitation outcomes, project-creation capability, final-owner protection, member deactivation/reactivation, and governance version lifecycle;
- structured notification destinations, project/tier filters, tier templates, self-exclusion, project switching, unavailable-target explanation, and `<time datetime>`;
- computed re-scan scope, durable failure/retry presentation, monitoring materiality and follow-ups, frozen snapshots, drift detection, and distinct generate/release surface states;
- selectable evaluations, ten exact judge dimensions, deterministic warnings, redacted tool-call summaries, and no-age core retention plus 30-day deletion grace.

## Production plan consequences

1. Plan 03 must implement real file controls and server-side byte verification; the mock button is not an upload contract.
2. Plan 06 owns M5–M8 documentation/metadata alignment and should add an automated requirement-level UI contract test rather than growing only string checks.
3. Plan 09 owns the full notification delivery-state matrix and contextual push prompt.
4. Plan 11 must use release-only language and commands after snapshot generation.
5. Every UI plan must include per-surface state, authorization, responsive, accessibility, direct-link, and visual-parity evidence.

## Closure rule

Do not mark the UI-plan-to-mock audit closed until M1–M8 are either corrected in the mock/living guidance or explicitly accepted as prototype boundaries with owner, rationale, and production acceptance evidence. A green structural audit alone cannot close them.

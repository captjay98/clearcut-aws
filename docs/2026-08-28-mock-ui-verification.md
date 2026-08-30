# ClearCut mock — verification record

**Date:** 2026-08-28
**Subject:** `misc/clearcut-flow`, the interface prototype and design source of truth
**Verdict:** All 20 surfaces work. No known functional defects.

## How this was verified

| Method | Result |
|---|---|
| Structural audit (`mockup-audit.mjs`) | 366/366 checks |
| Syntax (`node --check`), CSS brace balance | clean |
| Responsive sweep — 20 surfaces × 6 widths × 2 appearances | 240 renders, no overflow, nothing escaping the viewport, no collapsed text, no page errors |
| Accessibility — axe-core, WCAG 2.0/2.1 A + AA + best practice | 48 views (every surface in both appearances, plus 8 dialogs), 0 violations |
| Functional walkthrough — real controls driven end to end | 56 checks, 0 failures, no page errors |
| Computed-style regression — every element's box, type and colour | 13,411 element states across 91 views, 0 differences beyond a measured noise floor of 3 |
| Print | 8-page A4 document, 17,814 characters of selectable text, no app furniture |

Widths covered: 320, 390, 768, 834, 1024, 1440. Appearances: Script and Night.

## Per-surface findings

### Public entry

- **`#marketing`** — Interactive script page with three flagged terms, each swapping its own evidence card. Verified: one card shown and one flag pressed at all times, route and scroll untouched. The primary CTA lands directly in a populated project, which is what the hero's "No account required" line promises.
- **`#auth`** — Simulated sign-in, reachable from the footer. Authenticates, writes a receipt, routes to onboarding. No credentials collected.
- **`#invite`** — The can/cannot lists derive from the capability model, so they cannot drift from what is enforced.
- **`#onboarding`** — Organisation creation, pre-filled. Renaming persists; the optional reviewer is added as Invited.

### Organisation

- **`#projects`** — Two projects with derived stage and progress. Switching changes the active project.
- **`#notifications`** — Generated receipts merged with seeded events. The actor's own actions do not count as unread.
- **`#team`** — Invite adds a member with a receipt. Demoting the only Owner is refused. The demo role switcher reports the active role and gates accordingly.
- **`#settings`** — Profile saves; the receipt records `cadence: Weekly → Daily`, i.e. display vocabulary rather than the stored canonical value.
- **`#trust`** — Grades all ten dimensions the planning baseline scores, with the headline as their mean (90), the weakest dimension named, and the warning count derived from the deterministic gates. A learning candidate promotes to canary and rolls back.
- **`#records`** — Every research run opens to the tool calls behind it: tool, argument, duration, result and terminal status, including the timeout that was retried and the source that needs a person. Run totals are the sum of those rows.

### New clearance

- **`#new`** — All three steps work on a project that has not been started. Step 1 persists production details. A Paste import creates v1 from the text entered. The check runs on a real clock with a visible spinner and skeleton. This is the surface that demonstrates the agent working.

### Analysis

- **`#project`** — Next-step CTA reflects real state and navigates to a filtered worklist. The final call stores its rationale and displays it.
- **`#workspace`** — Renders through the same page wrapper as every other surface, so it carries a breadcrumb and, when relevant, the sample-data notice. Seven scenes with all ten flags placed inline and in the rail, footed by "END OF EXCERPT — 7 of 43 scenes, pages 2–15 of 62". The stage caption reads the same version as the header chip.
- **`#items`** — Ten rows. Search filters live and preserves caret and scroll. Grouping by scene yields 7 groups. A filter set by deep link persists across navigation. Three distinct empty states: no flags at all, no search match, no filter match.
- **`#item`** — Shows every source retrieved for the flag, including disagreeing ones. Verifying a source records the decision and moves the overview's count.

### Review and delivery

- **`#versions`** — Both versions listed with revision stock and lineage. The re-check resolves its affected flags with a receipt.
- **`#watch`** — Manual check surfaces the change; recording a review stores the chosen effect and echoes it.
- **`#report`** — Renders the actual clearance document: seven exhibit sections, Exhibits A–E from live state, an open-items appendix, and a binding table naming the script, sign-off rules, search method, grading method, the judge and the grade recorded. The release dialog's open count agrees with the appendix.

### Meta

- **`#sitemap`** and **`#states`** — Grouped under "Prototype tools", so review instrumentation does not read as shipped product.
- **Unknown hash** — renders a real not-found naming the hash typed, and keeps the hash rather than silently redirecting.
- **Role gating** — As Viewer, privileged controls are gated with a stated, focusable reason.

## Design invariants confirmed

- **One fact, one source.** Flag placement derives from `SCENES`. Counts derive from `DEMO_FACTS`. Cadence renders only through `cadenceLabel()`. Version labels through `boundVersionLabel()` and `versionChip()`. The verification denominator derives from the flags awaiting a call. Run totals derive from tool calls. The judge's headline is the mean of its dimensions. A released report's binding and its draft preview read one helper.
- **Flags belong to a project.** A project with no completed check has none, so the worklist, the annotated script and the report agree with the overview instead of reporting another project's findings.
- **No dead inputs.** Every editable field reaches the record it claims to.
- **One page wrapper.** All 20 surfaces render through `page()`; the wrapper is written in exactly one place.
- **Geometry lives in the stylesheet.** The 14 remaining inline styles all carry a value computed at runtime; nothing static.
- **The cascade is used, not argued with.** Four `!important` rules remain — visibility, the screen-reader clip, reduced motion, and hiding chrome from print.

## Defects found and fixed during this pass

Recorded because each one had survived earlier review.

1. **The audit harness printed its summary two thirds of the way up the file**, so roughly sixty checks registered after the report and were never displayed or able to fail the exit code. The true count was 259, not the 236 previously reported.
2. **`go()` validated the whole hash target against the route table**, so any CTA carrying a deep-link query silently did nothing — including the project overview's primary next-step button. It survived the earlier 40-check walkthrough because that walkthrough reached the worklist through the sidebar.
3. **Clicking "Clear search" threw a DOM error every time.** Replacing the route body while focus sat inside it left the browser mid-blur as the subtree detached. Fixed at the source by releasing focus before the replacement.
4. **Print output led with app furniture** — the surface's breadcrumb, page head, summary stats and release buttons printed as the first page of a record meant for counsel.
5. **Three places invented a version the project never saved**, so a project at v1 could file a report headed "Script snapshot v2".
6. **The ledger listed a selective re-scan** before any re-scan had run.
7. **The overview reported "0 verified"** while two rows in the worklist read "Verified", because the count and the population were drawn from different places.
8. **A wizard flag was global**, so saving details on one project reported step one complete on the other.
9. **The evidence decision answered to four names.** Settled on the pair that matches the resulting status and receipt.
10. **Two defects introduced by this pass and caught by measurement**: a regex that added a second `class` attribute to four elements, silently dropping those styles; and a component class that lost a size battle to a utility class in a later layer.

## Method note

Two harness lessons, both of which produced false failures before being corrected.

A red result is not a defect until the expectation is checked. In this pass, eight walkthrough failures and two sweep findings turned out to be wrong expectations: a filter that correctly persists across navigation, a "Clear search" control that only exists in the no-match state, a tab bar that is deliberately a horizontal scroller, and children of `display: none` ancestors reported as collapsed text.

For refactors that must not change appearance, measure rather than inspect. The `!important` removal and the inline-style removal were each verified by capturing every element's computed box, type and colour before and after, and by first establishing the harness's own noise floor by diffing two identical captures. Without that floor, three unstable readings — mid-transition CTA colours and a spinner animation frame — would have read as regressions.

## Not verified

- **Chromium only.** No Safari, no Firefox, no real iOS or Android device. The two constructs most likely to differ in Safari are `display: inline` on the landing flag buttons and `visibility: hidden` stacking behind the evidence cards.
- **No screen-reader pass.** Roles, names, live regions and focus order are correct by inspection and by axe-core, but nothing has been driven with VoiceOver or NVDA. Zero violations is not a WCAG conformance claim; that needs assistive-technology testing and expert review.
- **Provider behaviour.** Model and search calls are deterministic browser simulations, disclosed on the landing page and in the README.

## Outside the mock

- Production application with `google-adk`/`google-genai` and `parallel-web` imported and called at runtime — the prototype cannot satisfy this requirement by construction.
- The three-minute demonstration video and the hosted project URL.
- **AI tooling compliance.** The contest rules limit projects to Google Cloud AI tools plus the chosen partner's built-in AI features, and the organiser briefing extends this to the tools used to write the code, naming Gemini CLI and Gemini Code Assist as the safe path. Development to date used a non-Google assistant. This needs a written ruling from Devpost support or a move to Gemini tooling, and it can void the submission independently of product quality.

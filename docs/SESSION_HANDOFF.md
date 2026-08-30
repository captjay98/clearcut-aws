# ClearCut Session Handoff

**Current phase:** pre-implementation  
**Next allowed action:** implementation packet 01a only, after explicit owner authorization  
**Do not start:** product implementation, infrastructure mutation, deployment, credentials, mock correction, or Git commit from this planning task

## Start here

1. Read `docs/README.md` and `docs/IMPLEMENTATION_PLAN.md`.
2. Read `docs/plans/implementation/README.md`, `docs/plans/active/FEATURE_COVERAGE.md`, and `docs/DELIVERY_PLAN.md`.
3. Read `docs/DECISION_GAPS.md`; resolve each item before its named contract/task boundary.
4. Read `docs/PARALLEL_INTEGRATION.md` before touching detection/research/provider contracts. Search is mandatory; Extract is bounded; Monitor is conditional; excluded Parallel APIs are release failures.
5. Re-run `node misc/clearcut-flow/mockup-audit.mjs`; the current planning baseline observed 418/418 on 2026-08-30.
6. Review `docs/reviews/2026-08-30-ui-plan-to-mock-audit.md`; do not interpret 418/418 as full UI-plan closure.
7. If implementation is explicitly authorized, execute `docs/plans/implementation/01a-workspace-open-source.md` only.

## Known open decisions before or during foundation packets

- Confirm the exact Google agent platform/runtime wording required by the official contest page versus the package-level repository requirements.
- Obtain written organizer clarification on whether non-Google development assistants affect eligibility; the official rules' project-runtime restriction and the organizer-briefing interpretation recorded in the repo are not fully reconciled.
- Select exactly one headless accessibility library only after the required proof; no candidate is pre-approved.
- Packet 01a freezes exact tool versions; packet 01b decides the OpenAPI generator while preserving the already accepted checked-in generated-client paths.
- Decide the initial email mode for local/demo deployment (`none`, SMTP, Resend, or ZeptoMail) without changing the port contract.
- Do not decide Parallel Monitor now. Packet 09a requires a recorded owner go/no-go only after the mandatory 05a–05c R3 evidence slice passes; a Monitor no-go leaves scheduled Search/Extract monitoring intact.

## Frozen Parallel handoff

```text
05a  mandatory Parallel Search + provenance
05b  bounded Extract of at most 3 Search-authorized URLs
05c  claim/conflict/authority/confidence admission
09a  scheduled Search/Extract watch + conditional Monitor event-stream ingestion
09b  verified materiality + governed review
09c  notification backend
09d  Watch and Notifications UI
```

Task, FindAll, Responses/Chat, Interactions, Deep Research, snapshot Monitor, alternate research providers, and silent fallbacks are outside the submitted runtime. Implementation must stop if an SDK/API change makes the frozen request/response assumptions invalid; update the contract/packet through review instead of improvising.

## Current evidence

- Structural mock audit: 418/418 passed.
- Fresh browser spot sweep: all 20 canonical routes rendered one main heading with no horizontal page overflow at 1440x1000 and 320x844; Night shoot also had no horizontal page overflow at 320x844; no page errors were reported.
- Known audit limitation: the browser sweep was not a fresh axe, VoiceOver/NVDA, Safari, Firefox, print, or full interaction regression.
- Repository is dirty with extensive user-owned `.agents`, `.kiro`, and planning changes. Preserve them.

## First checkpoint

Packets 01a–01c end at R1. They must not claim product behavior. Evidence must name exact commands, output, revision, dirty-tree status, and explicit non-claims.

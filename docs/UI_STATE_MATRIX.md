# ClearCut Production UI State Matrix

This matrix converts the mock's visual guidance into route-level production acceptance. A generic `#states` gallery does not satisfy any row.

## Universal proof

Every applicable state is tested at 320, 375, 768, 1024, and 1440 pixels in Script and Night shoot themes. Tests cover keyboard order, visible focus, live-region behavior, coarse pointer, reduced motion, no horizontal page overflow, direct navigation, and authorization-safe not-found parity. Item and report routes also cover print.

## Surface matrix

| Surface | Required resource/data states | Required failure/access states | Owner packet |
|---|---|---|---|
| marketing | normal, runtime-proof disclosure, no-JavaScript readable core | unknown supporting route, missing optional media | 06b |
| auth | signed-out, submitting, recovery requested, verification required, signed-in continuation | invalid generic credentials, rate limited, provider unavailable, suspended | 02d |
| invite | pending, accepting, accepted, declined | expired, revoked, wrong account, malformed/not-found | 02d |
| onboarding | empty form, submitting, organization created, invitation optional | validation, duplicate slug retry, rollback-safe server failure | 02d |
| projects | loading, one/many organizations, projects present, no projects, no grants | membership deactivated, safe unknown organization/project | 02d |
| notifications | loading, empty, filter-empty, unread/read, mark-all, push prompt, SSE live, polling fallback | recoverable/permanent load failure, permission denied, destination unavailable | 09d |
| team | loading, members, invitations, no invitations, inherited/explicit grants | final Owner restriction, stale edit, unauthorized action, safe member not-found | 02d |
| settings | loading, operational settings, protected read-only/Owner edit, deletion grace | validation, recent-reauth required, stale version, adapter unavailable | 10c |
| trust | no evaluation, running/incomplete, valid score, blocker-over-score, learning stages | stale bindings, invalid evaluation, failed canary, rollback | 10b |
| records | loading, empty, filtered, activity, run/tool, evaluation, policy, operation | redacted, deleted destination, safe unknown, recoverable/permanent error | 10a |
| new | pristine project, four input modes, upload/parse progress, warnings, committed v1, cancelled/continued | invalid file, hostile/rejected, parse/model failure, upload expiry/replay | 03c |
| project | loading, unchecked project, checking, evidence ready, open work, complete | failed run, no project grant, safe not-found | 07d |
| workspace | loading script, pages/scenes, evidence drawer variants, superseded version read-only | item research running/no-sources/failed, broken anchor, safe not-found | 07d |
| items | loading, empty no-flags, filter-empty, list/board/group/search, selection/bulk | invalid filter, stale bulk item, partial per-item conflict, safe not-found | 07d |
| item | loading, sources, conflicts, zero evidence, discussion, decision/referral/disposition | research failed, stale decision, capability restriction, safe not-found, print | 07d |
| versions | v1-only, history, diff classes, re-scan queued/running/succeeded/cancelled | failed item/retry, stale worker, inaccessible version | 08c |
| watch | off/manual/daily/weekly, Search running/empty/failure, Extract full/partial/failure, no change, material/unavailable change, Monitor disabled/pending/active/degraded, signal awaiting verification, review/follow-up | provider failure, forged/replayed webhook, duplicate/stale review, scheduler/task failure | 09d |
| report | live preview, generation queued/running/succeeded, frozen snapshot, released/superseded, download/print | missing binding blocker, failed generation/retry, stale live state, expired download | 11c |
| sitemap | development-only complete index | excluded from production build | 06a |
| states | development-only component gallery | excluded from production build; never counted as route acceptance | 06a |

## Evidence artifact

Each owning packet writes a dated evidence matrix containing route, role, state fixture, theme, width, browser, accessibility result, screenshot identifier, and test name. A screenshot alone is not behavior proof; a structural test alone is not visual proof.

# E2E test honesty ledger

This ledger records what the browser suite proves and, equally importantly, what it does not prove. Do not describe local deterministic coverage as hosted, paid-provider, or legal-clearance evidence.

## Runtime isolation

`playwright.config.ts` starts both the API and web app automatically. Every run uses:

- a unique SQLite database and storage directory under `/tmp`;
- `CLEARCUT_SEED_DEMO=false`;
- one API worker and one Playwright worker;
- local job dispatch;
- production session, organization, project, capability, invitation, membership, and command boundaries;
- an e2e-only authenticated fixture route mounted around the imported production app.

The evidence fixture does not call a paid provider. Its synthetic Search/Extract provenance is explicitly marked as an e2e fixture and is not a Parallel receipt or provider session. Zero-evidence items remain unresolved and receive no invented fallback claim.

## Task 11 commands

Run the two authoritative evidence specs across all configured projects:

```bash
PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=mac15-arm64 \
  pnpm --filter clearcut-web exec playwright test \
  tests/e2e/evidence-workspace.spec.ts \
  tests/e2e/evidence-access.spec.ts
```

Run one project while iterating:

```bash
PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=mac15-arm64 \
  pnpm --filter clearcut-web exec playwright test \
  tests/e2e/evidence-workspace.spec.ts \
  tests/e2e/evidence-access.spec.ts \
  --project=chromium-desktop-1440
```

The host-platform override is needed only when the local Playwright browser installation targets that macOS artifact. CI or another host should use its installed platform normally.

## Configured matrix

| Project                 | Engine/profile        |   Viewport |
| ----------------------- | --------------------- | ---------: |
| `chromium-desktop-1440` | Desktop Chrome        | 1440 × 900 |
| `firefox-desktop-1024`  | Desktop Firefox       | 1024 × 768 |
| `webkit-tablet-768`     | Desktop Safari/WebKit | 768 × 1024 |
| `mobile-375`            | iPhone 13/WebKit      |  375 × 667 |

`workers: 1` is intentional because the local API suites share deterministic SQLite-backed setup and governed version state.

## API-connected evidence coverage

| Spec                                   | Level               | Proven behavior                                                                                                                                                                                                                                                                                                                                                                                       |
| -------------------------------------- | ------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `evidence-workspace.spec.ts`           | REAL, deterministic | Separate owner/reviewer/editor browser contexts created through public registration and real invitations/project grants; cited and zero-evidence deep links; decision persistence through refetch/reload; stale-version conflict with rationale retention; assignment/disposition persistence; cross-actor referral acknowledgement; authorized mentions across comment, reply, and revision history. |
| `evidence-access.spec.ts`              | REAL, deterministic | Server-derived denied-action explanations; unknown/foreign deep-link parity; unresolved zero-evidence state with no source link; labelled drawer dialog with initial focus, Tab containment, Escape close, and trigger-focus restoration; legal-boundary visibility, focusable governance, and no horizontal document overflow at every configured viewport.                                          |
| `review-collaboration-actions.spec.ts` | REAL reachability   | Authenticated owner and deterministic cited item reach the current decision, comment, rewrite, referral, and legal-boundary surfaces. This replaces the stale unauthenticated `Commit Governed Decision` smoke assertion.                                                                                                                                                                             |
| `revision-rescan.spec.ts`              | REAL, deterministic | Full provider-free revision + selective-rescan journey (see below).                                                                                                                                                                                                                                                                                                                                 |
| `version-diff-lineage.spec.ts`         | REAL, deterministic | A single committed version is labelled the latest revision and the diff/lineage surface honestly reports that no adjacent diff exists — no fabricated empty diff and no rescan trigger — using the current production copy.                                                                                                                                                                           |

Other E2E specs are outside the recorded Task 11 matrix. Their presence must not be used to claim they passed this run or that visibility-only smoke tests prove persisted backend behavior.

## Durable revision + selective rescan proof (`revision-rescan.spec.ts`)

This spec drives the real production UI and API end to end and is deliberate about its boundary.

### What it PROVES (locally, provider-free, deterministic)

- **Real import UI, twice.** Version 1 and the Version 2 revision are each imported through the actual upload → parse → commit flow (`ScriptUploadModal`), and each commit is confirmed by observing the persisted `:commitVersion` POST.
- **Persisted timeline.** After a reload the version list is the source of truth: two recorded versions, the newest labelled the latest revision.
- **Adjacent diff over the published contract.** All five change kinds (`unchanged`, `moved`, `modified`, `added`, `removed`) are present with per-kind element counts and `summary` aggregates read from the same `getScriptVersionDiff` contract the UI consumes. The rendered `VersionDiffViewer` shows the matching filter chips, the added Nike row, and the removed Ferrari row.
- **Governed, human-confirmed start.** A selective rescan never auto-starts. The confirm dialog is the sole trigger; the start request returns `202` and carries a fresh `Idempotency-Key` header. The persisted `rescanJobId` is written to the URL.
- **Reload-safe durability.** A reload reconstructs the same persisted job from the URL and issues no second start POST (verified by intercepting `:startSelectiveRescan`), and the job reaches terminal `succeeded` through the durable job engine.
- **Affected items detected and researched.** The modified passage (Rolex → iPhone) and the added passage (Nike) become fresh Version 2 clearance items through the real detection path and reach `researchStatus = "completed"` through the real research job with hermetic Search/Extract.
- **Removed passage retired.** The removed Ferrari passage does not resurface as a Version 2 item.
- **Carried evidence keeps its original provenance.** The predecessor cited item still references its original source URL, excerpt, and retrieval time after the rescan; its status and its prior governed decision are unchanged — the rescan re-clears nothing and mutates no historical record.
- **No duplicate work.** A revisit of the persisted job issues no new start POST, the timeline still shows exactly two versions, and exactly one `selective_rescan` job was ever created.
- **No paid provider was contacted.** A request listener fails the proof if any browser request reaches a Parallel/Gemini/Vertex/Google API host; the recorded run made none.

### Why an explicit child-job drain exists in the harness

The parent `selective_rescan` job only **enqueues** durable detection/research child jobs; it never blocks on them. In the hosted target a durable dispatcher (Cloud Tasks) pulls those queued children. The local composition intentionally runs no queue-draining worker — the periodic local recovery loop only recovers expired `claimed`/`running` leases, never fresh `queued` rows. So after the rescan reaches terminal success its research children are still `queued`, and affected items do not reach `research_status = "completed"` on their own.

The provider-free harness therefore exposes one schema-hidden, authenticated, org+project-scoped fixture endpoint, `…/drain-child-jobs`, that runs exactly the detection/research children the rescan already enqueued through the **same** hermetic doubles, mirroring the repository-level drain in `services/api/tests/e2e/test_revision_selective_rescan.py`. It is an explicit stand-in for the hosted dispatcher: it invents no work and no evidence, calls no paid provider, and only executes durable jobs that already exist. The deeper element-lineage identity invariants (`lineage_kind == carried_forward`, `predecessor_item_id` linkage, `carried_forward_confirmation_required`, evidence-lineage edges) are not exposed over HTTP and are proven at the repository level by that backend test; the browser proof asserts the behavior those invariants produce that is observable at the HTTP/UI surface.

### What it does NOT prove

- hosted durability, real Cloud SQL/Cloud Storage/Cloud Tasks behavior, or a hosted durable dispatcher actually pulling queued children (the local drain is a deterministic substitute, not that worker);
- live Parallel Search/Extract quality, provider availability, or genuine provider receipts;
- paid-provider reliability or cost behavior under real load;
- legal advice, final legal clearance, or any guarantee that an item is clear.

## Last witnessed results

On 2026-08-31:

- Task 11 matrix: **44 passed** across all four projects (`11` cases × `4` projects), one worker.
- Rewritten collaboration reachability check: **1 passed** on `chromium-desktop-1440`.
- Focused Chromium access suite: **5 passed**.
- Focused Chromium governed workspace suite: **6 passed**.

On 2026-09-08 (revision + selective rescan):

- `revision-rescan.spec.ts` and `version-diff-lineage.spec.ts`: **8 passed** across all four projects (`2` cases × `4` projects: `chromium-desktop-1440`, `firefox-desktop-1024`, `webkit-tablet-768`, `mobile-375`), one worker. No project needed scoping-down.

## Explicit limits

This local suite does **not** prove:

- live Parallel Search/Extract behavior, provider availability, or provider receipts;
- hosted Cloud SQL, Cloud Storage, Cloud Tasks, Secret Manager, or production identity behavior;
- public deployment availability, public video evidence, or organizer compliance acceptance;
- legal advice, final legal clearance, or a guarantee that an item is clear.

Those claims require separate, attributable evidence from the real environment. Missing external evidence remains an explicit blocker; it must never be fabricated from deterministic fixtures.

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

Other E2E specs are outside the recorded Task 11 matrix. Their presence must not be used to claim they passed this run or that visibility-only smoke tests prove persisted backend behavior.

## Last witnessed results

On 2026-08-31:

- Task 11 matrix: **44 passed** across all four projects (`11` cases × `4` projects), one worker.
- Rewritten collaboration reachability check: **1 passed** on `chromium-desktop-1440`.
- Focused Chromium access suite: **5 passed**.
- Focused Chromium governed workspace suite: **6 passed**.

## Explicit limits

This local suite does **not** prove:

- live Parallel Search/Extract behavior, provider availability, or provider receipts;
- hosted Cloud SQL, Cloud Storage, Cloud Tasks, Secret Manager, or production identity behavior;
- public deployment availability, public video evidence, or organizer compliance acceptance;
- legal advice, final legal clearance, or a guarantee that an item is clear.

Those claims require separate, attributable evidence from the real environment. Missing external evidence remains an explicit blocker; it must never be fabricated from deterministic fixtures.

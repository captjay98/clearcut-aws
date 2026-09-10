---
feature: mock-parity-flags-research
status: delivered
updated: 2026-09-10
branch: feat/local-image-journey
commits: 46b2821..HEAD
---

# Mock Parity — Flags, Research, Workspace

## Report

**What was built** — Mock-aligned display for flags, research evidence, and the screenplay workspace. One presentation module maps API categories/statuses/stances/authority to the mock vocabulary. The flags worklist uses the mock title, status chips, and row anatomy (id, category, scene, sources·conflict, confidence, severity, status). Item detail shows script context, a primary source card, a source table with Bearing labels, clamped excerpts, and ownership via a member picker. The workspace injects gutter marks for entity-name matches, revision stock, and reuses the evidence panel in the drawer. The shell shows `vN — white pages`.

**Verification** — `pnpm --filter clearcut-web test` 89 passed; `tsc --noEmit` clean; rebuilt `clearcut:local` and confirmed live list/detail/workspace chrome.

**Journey log** —
1. Backend category enums differ from mock English; presentation mapping is the only safe place to bridge.
2. `ProjectScript` version is a string (`v1`); do not double-prefix.
3. List `ClearanceItem` has no `page` field — omit `p.N` unless the API provides it.
4. Detail `claimCount` lives on `evidenceState` for some payloads — `displayStatus` reads both.
5. Flag pager and List/Board toggle remain follow-ups.

## [S1] Problem

The live Docker image runs the full governed journey, but flags, research evidence, and the screenplay workspace still read as API dumps. The mock at `misc/clearcut-flow/` is the design source of truth (AGENTS.md). A side-by-side of mock `#items` / `#item` / `#workspace` against live `:18080` shows systematic display drift: wrong titles and status vocabulary, missing CC-ids/page/owner/source-conflict meta, raw stance/authority enums, untruncated provider excerpts, no primary-source card or source table, no gutter marks on script lines, three different category label sets, and decision controls that are raw radios + a member-id textbox instead of the mock’s reviewer actions.

## [S2] Design

### Principles

1. Mock is the visual and vocabulary contract; backend remains the data authority.
2. One presentation module owns category, status, stance, authority, and severity labels — no surface invents its own strings.
3. Never invent evidence, ownership, pages, or conflict states the API did not return. Missing fields render as absent, not placeholder fiction.
4. Governed writes stay on existing commands; this feature is display + interaction fidelity, not new domain behavior.
5. Prefer truncating long excerpts over showing multi-kilobyte raw markdown dumps.

### Canonical vocabulary (single module)

Extend `apps/web/src/features/clearance/itemPresentation.ts` as the only label source.

**Backend category enum (authoritative storage)** → **mock display label** → **margin short**:

| API `category` | Display | Short |
|---|---|---|
| `real_persons_living` / `real_persons_deceased` | People & likeness | PEOPLE |
| `corporate_entities` | Organizations & insignia | INSIGNIA |
| `products_and_trademarks` | Brands & trademarks | MARK |
| `copyrighted_works` | Artwork & media | ART |
| `music_and_lyrics` | Music & lyrics | MUSIC |
| `locations_and_landmarks` | Locations & property | LOCATION |
| `vehicles_and_insignia` | Products & trade dress | PRODUCT |
| `sensitive_historical_events` | Privacy & sensitive facts | PRIVACY |
| `contact_information` | Dialogue & quotations | QUOTE |

Notes:
- Mapping is a presentation alias only; storage values never change in this feature.
- Unmapped future categories fall back to title-cased snake_case + first-word short (current behavior).
- Delete the third vocabulary in `CategoryFilterBar` / workspace radios; filters use `displayCategory()` + counts keyed by API enum.
- `shortCategory()` keys must match API enums after underscore→space normalization, not mock English.

**Decision / workflow status language**

Keep API `status` / `workflowStatus` / `disposition` as data. Map display:

| Condition | Mock label | Tone |
|---|---|---|
| status blocked / disposition must-fix-like | Must fix | is-danger |
| sourcesDisagree or status conflict | Sources disagree | is-warning |
| status referred | With specialist | is-warning |
| settled verified/ruled_out/resolved | Verified | is-success |
| claimCount === 0 and research not completed | Needs research | is-muted/warning |
| otherwise attention/unresolved | Needs your call | is-warning |

`displayStatus(item)` used by flags list, workspace rail, item header, and report excerpts.

### Layer 1 — Flags worklist (`items/index.tsx`)

Acceptance-shaped UI, mock vocabulary:

1. Eyebrow `Analysis`; title **Clearance flags**; lede: “Everything the check flagged, with its scene, owner, and where your call stands.”
2. Breadcrumb: Projects / **project title** / Clearance items (org chip optional if Page trail cannot resolve name).
3. Status filter chips: All (n) · Attention (n) · Needs your call (n) · Sources disagree (n) · With specialist (n) · Verified (n) · Must fix (n) · Could not verify (n) — only chips with count > 0 plus All/Attention.
4. Sort as button row (Term, Severity, Confidence, Scene, Due, Status) + Group combobox retained.
5. List/Board toggle: List default; Board groups by status columns (stretch if time-boxed — List first).
6. Row anatomy:
   - checkbox (existing)
   - title = entityName
   - meta: **CC-… or short item id** · displayCategory · **Scene N · p.N** (page from API when present) · **`K sources` / `K sources · conflict`** (claimCount + sourcesDisagree) · confidence %
   - aside: owner avatar+name when assignee present · severity word · displayStatus
   - Review item link retained
7. Sidebar project nav: **Flags {openAttentionCount}** badge (mock shows open flags).
8. Shell header when in project: revision stock chip `v1 — white pages` (or latest version label) from version query — not hardcoded.

### Layer 2 — Item detail & research (`items/$itemId.tsx` + evidence components)

1. Header: category eyebrow · entityName · lede **“Scene N, page P · High/Medium/Low priority”** (priority from severityOf / API severity) · status badge.
2. Pager: “X of Y flags” + prev/next using current sort order from list query cache or a lightweight sibling fetch.
3. Actions: Print record (window.print CSS) · **Back to items** (not workspace only).
4. **Script context** section when `contextText` present: the passage + “Anchored to a stable span…”.
5. **Evidence** rewrite:
   - Section head: “Evidence” · “Sourced claims with authority tier and retrieval metadata. N sources retrieved for this flag.”
   - **Primary source card**: top authority tier snapshot → authority label · title · short claim (first claim or snapshot excerpt truncated ~280 chars) · `retrieved {relative/absolute} · snapshot retained` · “Where this came from” expandable (URL, origin search|extract, snapshotId).
   - **Source table**: Source | Authority | What it says | Bearing.
     - Bearing: supports → Supports; context → Context; conflicts → Disagrees; opposing/contradicts → Disagrees (align to actual stance enum values from contracts).
   - Excerpts: clamp with “Show more”; strip markdown noise if trivial (`#`, `**`) without rewriting meaning.
   - Confidence block when confidence present.
   - Conflict callout when sourcesDisagree or any stance conflicts: **“Conflict retained, not resolved automatically”** + conflict text if API provides it, else generic “Sources disagree on this flag; a human must decide.”
6. **Your call** card: primary actions Verify this source / Rule this source out / Refer to specialist / Propose a rewrite — each opens or focuses the existing governed forms; do not remove the legal-boundary copy.
7. **Ownership**: assignee avatar+name or “Unassigned”; due date; priority; Reassign control — replace raw “Assignee member ID” textbox with member picker (listOrganizationMembers) still posting member id.
8. Keep evidence-review decision radios as the detailed form behind “Your call” (or collapsed “Record review decision”) so audit language stays.

### Layer 3 — Workspace screenplay (`workspace.tsx` + `ScreenplayViewer`)

1. Title: **Screenplay — {projectTitle}** (not only “Clearance Workspace”).
2. Ensure `getProjectScript` scenes/lines carry flag markers matching entity terms; if API does not attach flags on lines, resolve client-side by matching item.entityName/contextText against line text (already partially done) and still render gutter marks when a match exists.
3. Render gutter mark + shortCategory + severity glyph + underlined term on matching lines (ScreenplayViewer already implements this — verify props are fed; fix data wiring, not a new viewer).
4. Page regions with page numbers when scene.page exists; revision stock on version (v1 white).
5. Scene rail: scenes with nested flag chips (glyph + term + shortCategory), click selects flag and opens EvidenceDrawer.
6. Right pane / drawer: **Evidence workbench** for selected flag (reuse improved evidence block from Layer 2) rather than only the filter list. Keep filter list available (tab or section above workbench).
7. Header live readout via ShellContext: `Scene N · p.P` when selection/scroll changes (mock).
8. Mobile tabs Script / Scenes / Evidence already exist — keep.

### Layer 4 — Shared chrome

1. AppShell project header: version chip + stock color class from mock REVISION_STOCK map.
2. Flags sidebar count.
3. Align item list and workspace cards to the same `displayStatus` / `displayCategory` helpers.

### Out of scope

- Changing backend category enum or migrations
- Board view polish beyond a minimal status-column board (if shipped, follow-up)
- Marketing/docs pages
- Hosted GCP or provider behavior
- Rewriting legal-boundary copy
- Full print stylesheet audit beyond a usable print of item detail

### Risks / contracts

- `page` optional on ClearanceItem — omit `p.N` when null.
- `assignee` may be absent — omit owner row rather than “Unassigned” spam on list; show Unassigned only on detail ownership card.
- Stance enum must be read from contracts; do not hardcode only mock words if live API uses `supports`/`context`/`conflicts`.
- E2E strings: `new-clearance-flow.spec.ts` asserts “Detected clearance items” — update to “Clearance flags” when title changes.
- Unit tests for `itemPresentation` mapping and displayStatus.

## [S3] Out of Scope

- Org resolver surface, invite UX, monitoring UI beyond report already fixed
- Permanent container-targeted Playwright suite
- Paid provider cost/behavior changes

## Tasks

- [x] T1: Canonical presentation module — acceptance: unit tests cover API categories and status matrix (covers: S2)
- [x] T2: Flags worklist mock chrome — acceptance: live list matches mock row anatomy; e2e title updated (covers: S2; depends: T1)
- [x] T3: Item detail evidence block — acceptance: primary card + source table with Bearing (covers: S2; depends: T1)
- [x] T4: Item detail review chrome — acceptance: member picker; mock action labels (covers: S2; depends: T1)
- [x] T5: Workspace script-flag wiring — acceptance: gutter marks + evidence drawer (covers: S2; depends: T1,T3)
- [x] T6: Shell revision stock + version chip — acceptance: `vN — color pages` (covers: S2; depends: T1)
- [x] T7: Verify — acceptance: 89 unit tests + typecheck + live smoke (covers: S2; depends: T2–T6)

## Suggested implementation order

T1 → T2 + T3 in parallel → T4 → T5 → T6 → T7.

## Verification (2026-09-10)

- `pnpm --filter clearcut-web test` — 13 files, **89 passed**
- `tsc --noEmit -p apps/web/tsconfig.json` — clean
- Rebuilt `clearcut:local` and re-checked live: Clearance flags list, evidence table (Supports/Bearing), Needs research vs Needs your call, gutter LOCATION/MARK marks, `v1 — white pages` shell chip

## Manual acceptance script (live image)

1. Rebuild/restart `clearcut:local` if needed.
2. Open flags list: title/chips/row meta match mock grammar.
3. Open researched item: primary card + table + conflict language; excerpts truncated.
4. Open workspace: gutter mark on Coca-Cola line; click opens evidence; rail lists flags.
5. Confirm one un-researched item still shows Needs research + Run research, zero invented claims.

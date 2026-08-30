# Revision, Monitoring & Report UI Design

**Date:** 2026-08-29
**Status:** Approved
**Surfaces:** `#versions`, `#watch`, `#report`
**Depends on reviewed surfaces:** `#trust`, `#records`, `#team`, `#settings`, `#auth`, `#onboarding`, `#invite`, `#projects`, `#new`, `#notifications`, `#project`, `#workspace`, `#items`, `#item`

## Purpose

This design establishes the revision lineage, selective re-scan, source monitoring, and report generation/release/export behavior for ClearCut. These three surfaces are the final production-delivery pipeline: a rewrite creates a new version, re-scanning validates affected evidence, monitoring catches source changes after decisions, and the report packages everything for handoff.

The mock at `misc/clearcut-flow/` remains the visual and interaction source of truth. This document does not authorize mock implementation changes beyond those already applied.

## Approved decisions

1. Rewrite proposal and approval are separate governed actions with a maker/checker split. An Editor proposes rewrite text on `#item`. A Reviewer or above approves it. The proposer cannot approve their own proposal. Approval atomically creates a new immutable script version.
2. Selective re-scan is a durable async job following the same lifecycle as the initial analysis run (queued → running → succeeded/failed/cancelled). It is not synchronous.
3. Monitoring review is a governed decision. "Reopen" creates a superseding review record; it never deletes the prior decision. "Keep + follow-up" creates a durable follow-up task. "Refer" creates a referral.
4. Report generation and release are separate operations. Generation creates a frozen snapshot artifact. Release is a governed attestation that makes the snapshot available for delivery.
5. A released report is immutable. It reads from its frozen snapshot, not live mutable state.
6. Owner, Admin, and Reviewer may generate and release reports within authorized projects.

## `#versions` — Script versions and selective re-scan

### Purpose

The versions page is the history of the screenplay as an immutable, append-only ledger. Each version is a saved copy that can never be changed. New versions come from two sources: approved rewrites and re-imports. When a new version exists, the page shows what changed and what needs re-checking.

### v1-only state

When only one version exists, the page shows:

**Version card** — a single card rather than a table, since there's only one entry:
- Version label and stock color (v1 · white pages)
- Source: how it was created (FDX import / Fountain import / PDF import / paste)
- Import date and actor
- Script metrics: passage count, scene count, page count
- Snapshot hash (collapsible technical detail)
- State: Current

**How new versions are created** — two explanatory cards replacing the current vague info banners:
- **Approved rewrite:** "When a reviewer approves a proposed text change, the new text is saved as the next version. The original stays locked."
- **Re-import:** "Upload a new script file to create the next version. Use this for external revisions done outside ClearCut."

Both cards explain the path but contain no actions — rewrites happen on `#item`, re-imports happen on `#new`.

### v2+ state (multiple versions)

When two or more versions exist, the page shows four sections in a single scrollable layout:

**1. Version history table**

| Column | Content |
|---|---|
| Version | Label + stock color dot (v2 blue, v1 white) |
| Where it came from | "Approved rewrite of CC-110" or "FDX import" |
| Based on | Parent version or "first" |
| Created | Date and actor |
| State | Current / Locked badge |

Newest version first. Each row is expandable to show: snapshot hash, passage count, scene count, page count, and the approval receipt link (for rewrite-sourced versions).

**2. What the rewrite changed**

A side-by-side diff panel showing the original text (struck through, locked badge) and the approved text (inserted, current badge). Below the diff:
- Who approved it and when
- The recorded rationale

Stats (three cards):
- Passages changed: count of total passages
- Flags affected: count with specific IDs (directly changed + nearby in same scene)
- Sources reused: count of evidence records carried forward unchanged

This section appears only for rewrite-sourced versions. Re-import versions show a structural diff summary instead: scenes added/removed/modified, elements changed, and which flags' stable spans were affected.

**3. Selective re-scan**

The re-scan section tracks the durable async job that re-checks affected items against the new version.

**Before trigger:**
- Scope card: names each affected flag, why it's affected (passage rewritten / same scene changed / element moved), and its current state (Queued)
- Stats: directly affected count, nearby count, untouched count, checks saved percentage
- Trigger button: "Re-check the changed scenes" (requires research capability)

**Running:**
- Per-flag progress rows: CC-110 running, CC-109 queued
- Poll-based status updates (3–5 second interval), focus-stable
- Cancel button with preserved partial results
- Live-region announcements: "Re-checking CC-110…", "CC-110 complete, CC-109 starting…"

**Completed:**
- Per-flag results: CC-110 fixed in v2, CC-109 needs your call
- Sources reused summary
- "Watch the sources" navigation to `#watch`

**Failed:**
- Which flags failed with error detail
- Retry button for failed flags
- Succeeded flags keep their results

**Cancelled:**
- Partial results preserved
- "Continue re-check" creates a predecessor-linked run

**4. Re-import history**

If multiple versions came from file re-imports rather than rewrites, a collapsed section shows the import history: version, source format, file name, import date, and structural diff summary.

### Rewrite lifecycle

The rewrite lifecycle spans `#item` (proposal and approval) and `#versions` (version creation and re-scan):

```text
draft → proposed → approved → materialized_in_version → superseded
                 ↘ rejected
                 ↘ withdrawn
```

- **draft:** Editor is composing the replacement text (not yet submitted)
- **proposed:** Editor submits the proposal. Appears on `#item` for review. The proposer cannot approve their own proposal.
- **approved:** A Reviewer or above approves. This atomically creates the new immutable script version, computes the structural diff, identifies affected flags, and queues the selective re-scan job.
- **rejected:** A Reviewer or above rejects with rationale. The proposal stays in history. The Editor may propose again.
- **withdrawn:** The proposer withdraws before approval.
- **materialized_in_version:** The approved text is now part of a committed version.
- **superseded:** A later rewrite on the same passage creates a newer proposal.

Approval is a governed action: rationale field, confirmation dialog, same-transaction audit event with the version creation and re-scan job dispatch.

### Cross-version item identity

Clearance items have stable logical identities that persist across versions. When a new version is created:

- **Unchanged items:** Same text, same span, same evidence. Carried forward with no re-scan needed.
- **Directly affected:** The flagged passage was rewritten. Evidence is invalidated; re-scan required.
- **Nearby affected:** A different passage in the same scene changed. Evidence may be contextually affected; re-scan required.
- **Moved:** The flagged passage moved to a different page/scene but text is identical. Span updated, no re-scan needed.
- **Removed:** The flagged passage was deleted entirely. Item is marked as removed-in-version; prior evidence preserved historically.
- **Added:** A new passage in the new version matches detection criteria. Creates a new item with zero evidence.
- **Split/merged:** Complex structural changes may split one item into two or merge two into one. Lineage records the relationship.

The version diff engine computes this classification using stable element and span identifiers from the parser.

### States

| State | Behavior |
|---|---|
| Loading | Skeleton version cards and table rows |
| Empty — no versions | "No versions yet" + link to `#new` to import a script |
| One version | Single version card + explanatory cards for how new versions are created |
| Multiple versions | Full version table + diff + re-scan section |
| Re-scan running | Per-flag progress with poll-based updates |
| Re-scan failed | Per-flag error detail with retry |
| Recoverable error | Retry preserves page state |
| Not found | Access-safe not-found for unknown project |

## `#watch` — Source monitoring

### Purpose

Sources change after you check them. The monitoring surface lets you set a Search/Extract watch cadence, run manual checks, optionally receive verified Parallel Monitor event-stream signals, review detected changes, and record what those changes mean — without ClearCut ever changing a decision on its own.

### Layout

**Configuration cards (three-column grid):**

1. **How often** — cadence radio buttons: Off, Manual only, Daily, Weekly. Changing cadence is an operational setting (Editor+), not a governed decision. Changes take effect for future scheduled runs; they do not retroactively modify past runs or the released report.
2. **Who follows up** — the default assignee for monitoring review items. Changeable by Editor+ with inline edit (member picker dropdown and escalation hours input appear in place when clicked). Escalation means: if the assignee has not reviewed a detected source change within the configured window, the system creates an urgent-tier notification to the project Owner. This ties into the approved notification taxonomy.
3. **Next look** — the next scheduled check date (derived from cadence), plus the total sources being watched.

**Source changes list:**

The main content area shows all detected changes from the most recent monitoring run. When a run detects multiple changes across different sources, all are listed — each with its own diff and review button. The reviewer can address them in any order.

Each change card has multiple states:

**No check has run:**
- Explanation of what monitoring does
- "Check sources now" button (requires research capability)

**Check running:**
- Progress: "Checking 38 sources…" with a count of completed/total
- Poll-based updates, focus-stable
- Cancel button

**Check complete, no changes:**
- "No changes detected" success banner
- Sources checked count and date

**Check complete, change detected, not yet reviewed:**
- List of change cards, one per detected material change
- Each card shows:
  - Which item and source changed
  - Badge: "Your call needed"
  - Side-by-side diff: verified snapshot text vs. current source text
  - Info banner: "Your prior evidence decision is unchanged — nothing changes until you record what this source change means."
  - "Review the change" button → opens the review dialog for that specific change

**Parallel Monitor signal awaiting verification (conditional capability):**
- Neutral badge: "New web signal"
- Copy: "Parallel detected a potentially relevant update. ClearCut is checking it through Search and selected-source extraction before opening review."
- Safe provider/correlation link to Records
- No review action, materiality badge, or evidence mutation until verification completes

**Monitor disabled or not shipped:**
- Do not render a broken integration or imply reduced evidence integrity
- Scheduled/manual Search/Extract monitoring remains the complete visible product behavior

**Change reviewed:**
- Success banner with the recorded review effect
- "See the review" links to the review record in Records

### Monitoring review dialog

A governed action with rationale and same-transaction audit. The dialog shows:

- **Accepted snapshot:** what was verified originally
- **Current source:** what it says now
- **Review effect** dropdown:
  - "Keep verified evidence; create a follow-up" — evidence decision stands, a follow-up task is created with a due date and assigned to the monitoring owner
  - "Reopen the evidence decision" — creates a superseding review record that moves the item back to "awaiting decision." The prior verified decision is preserved in history, linked to the superseding record, and never deleted.
  - "Refer to a specialist" — creates a referral with specialist type and notes
- **Rationale** text field — recorded with the review
- Confirm button: "Record review"

Each review option creates an immutable record. "Reopen" in particular does not null out or delete the prior decision — it creates a new superseding `MonitoringReview` record that links to the prior `EvidenceDecision`, explains why it was reopened, and moves the item's disposition back to pending. The full history remains navigable.

### Monitoring run lifecycle

```text
scheduled | manual_trigger
→ queued → running → completed
                   ↘ failed → manual_retry
                   ↘ cancelled
```

Each `MonitoringRun` records:
- Trigger: scheduled cadence or manual request
- Actor: system (scheduled) or the user who triggered it
- Sources checked count
- Changes detected count
- Materiality assessment per change
- Review items opened count
- Terminal state and timestamp
- Trigger capability: scheduled Search/Extract, manual Search/Extract, or verified Monitor signal
- Provider event ID/group correlation when applicable

A monitoring run is a durable async job with the same patterns as analysis and re-scan: idempotency key, bounded retries, lease, and reconciliation.

### Source change materiality

Not every source change is material. The monitoring system assesses each change:

- **Material change:** the source content relevant to the evidence claim has changed in substance (registration status changed, ownership transferred, policy revised). Creates a review item.
- **Non-material change:** formatting, layout, or unrelated content changed but the relevant claim is intact. Logged but does not create a review item.
- **Source unavailable:** the URL returns an error or the content is gone. Creates a review item with "source unavailable" status.

The materiality assessment is recorded with the monitoring run. A Monitor signal cannot be classified until a new scoped Search/Extract run produces verified snapshots. Reviewers see only material changes and unavailable sources in the UI; non-material changes and unverified provider signals are visible in Records for audit.

### Check history table

A paginated table of past monitoring runs:

| Column | Content |
|---|---|
| When | Date and trigger type (scheduled / manual) |
| Sources | Count checked |
| Changes | Count of material changes |
| Reviews opened | Count of review items created |
| Outcome | Badge: No change / Awaiting review / Reviewed |

Each row is expandable to show per-source details of what changed.

### Cadence and role behavior

| Role | Can change cadence | Can trigger manual check | Can review changes |
|---|---|---|---|
| Owner | Yes | Yes | Yes |
| Admin | Yes | Yes | Yes |
| Reviewer | No | No | Yes (review dialog) |
| Editor | Yes | Yes | No (review needs Reviewer+) |
| Viewer | No | No | No |

Cadence changes are operational, not governed — no rationale or audit event required. Manual check triggers are operational. Change reviews are governed with rationale and audit.

### States

| State | Behavior |
|---|---|
| Loading | Skeleton configuration cards and change card |
| Empty — no checks | Explanation + manual trigger button |
| Check running | Progress with source count |
| No changes | Success banner |
| Change detected | Accent card with diff and review button |
| Change reviewed | Success banner with recorded effect |
| Check failed | Error with retry |
| Recoverable error | Retry preserves cadence and history |
| Not found | Access-safe not-found for unknown project |

## `#report` — Clearance report

### Purpose

The report is the delivery package: what the script contained, what was checked, what was decided, and what risks were accepted. It is built from exact saved versions so it can be reproduced later.

### Two-phase lifecycle: generation then release

The audit proved that the mock's fused "Generate & release" button and live-mutable released report break reproducibility. Production separates these into two distinct operations:

**Phase 1 — Generate (creates a frozen snapshot):**
- A durable async job that reads the current state of: script version, all flags and their evidence, all decisions, all receipts, monitoring status, AI trust summary, and policy/rubric/prompt bindings.
- Produces an immutable `ReportSnapshot` artifact with a content hash.
- The snapshot is a point-in-time freeze. Subsequent changes to items, evidence, monitoring, or receipts do not alter it.
- Generation can be triggered by Owner, Admin, or Reviewer.
- The generated snapshot is available for preview before release.

**Phase 2 — Release (governed attestation):**
- A governed action with an attestation dialog: the actor confirms the report accurately represents the organization's decisions and is not legal advice.
- Commits the release with a same-transaction audit event.
- The released report becomes available for download/export.
- Only Owner, Admin, and Reviewer may release.
- Multiple snapshots can be generated; only one is released at a time. Releasing a new snapshot supersedes the prior release.

### Report page layout

The report page is split into two zones to avoid excessive scrolling:

**Top zone — Status and actions (fixed, no scrolling):**

Stats bar (four cards):
- Script snapshot: version label, links to `#versions`
- Flags documented: total count, links to `#items`
- Calls recorded: receipt count, links to `#records`
- Still open: count of items without a final disposition, with warning tone if any

Toolbar (state-adaptive):
- Draft state: "Draft preview" badge + "Generate snapshot" button
- Generated state: "Snapshot ready" badge + "Preview" and "Release" buttons
- Released state: "Released" badge with timestamp + "Download" and "See the record" buttons
- Stale state (changes after release): A specific banner naming what changed — e.g., "2 new decisions recorded since release," "1 source change detected," or "Rewrite approved, v3 created." This helps the reviewer judge whether regeneration is necessary. + "Generate new snapshot" button. The released document stays frozen and downloadable. Regenerating starts a fresh generation/release cycle; the prior release remains available until the new snapshot is released.

**Bottom zone — Tabbed exhibit viewer (scrolls independently):**

Instead of one long scrollable document, each exhibit renders in its own tab. Only one exhibit is visible at a time. The tab bar sits between the toolbar and the exhibit content:

```text
[A·Versions] [B·Flags] [C·Sources] [D·Decisions] [E·Trust] [Open items] [Binding]
```

Seven tabs. Clicking a tab shows that exhibit's content in the scrollable area below. A persistent one-line legal disclaimer appears at the bottom of every tab view: "This report is not legal advice and does not certify clearance. Final legal judgement rests with counsel."

The full report still exists as one continuous document for print and PDF export. The tabbed viewer is the on-screen navigation, not a structural change to the document.

### Report document structure

**Exhibit A — Script versions:** version table with source, stock, and snapshot IDs.

**Exhibit B — Flags register:** all items with ID, term, category, scene, status, and owner.

**Exhibit C — Sources & authority:** every retrieved source with authority tier, record name, retrieval timestamp, excerpt, and bearing. This is the complete evidence provenance table.

**Exhibit D — Decisions & receipts:** chronological record of governed actions with receipt ID, action, detail, and timestamp.

**Exhibit E — Source watch & AI trust:** monitoring cadence and status at the time of generation, learning stage and protected-controls confirmation.

**Open items (separate tab):** items without a final disposition, disclosed rather than hidden. "Carried, not hidden." This has a specific audience — the lawyer or insurer who needs to see exactly what's unresolved.

**Binding (separate tab):** exact input versions the report is bound to: script snapshot, sign-off rules, search method, grading method, graded-by model, grade, and snapshot hash. This is the reproducibility proof — re-running with these exact inputs produces the same document.

**Legal disclaimer (persistent):** appears as a one-liner at the bottom of every tab view. "A production record of what was checked, decided, and left open. It is not legal advice and does not certify clearance. Final legal judgement rests with counsel."

### Frozen snapshot vs. live preview

| Field | Draft preview | Released snapshot |
|---|---|---|
| Flags and statuses | Live from current item state | Frozen at generation time |
| Sources and evidence | Live from current claims | Frozen at generation time |
| Decisions and receipts | Live from current records | Frozen at generation time |
| Monitoring status | Live cadence and review state | Frozen at generation time |
| Binding versions | Current active versions | Exact versions used at generation |
| Snapshot ID | "computed at release" | Immutable content hash |

This means: if you generate a snapshot, then change the monitoring cadence, then release, the released report shows the cadence at generation time, not the current cadence. The audit proved this is necessary — the mock's live binding allowed post-release mutations to alter Exhibit E and insert new receipts while keeping the same snapshot ID.

### Report generation job

```text
triggered → queued → running → completed → available_for_release
                             ↘ failed → manual_retry
```

The generation job:
- Reads all required state within a single consistent database snapshot
- Produces the report artifact (structured data, not rendered HTML/PDF)
- Computes the content hash
- Records exact version bindings
- Stores the artifact in object storage
- Creates an audit event for generation

### Release attestation dialog

```
┌─────────────────────────────────────────────────────┐
│ Release the clearance report?                        │
│ The report captures this exact snapshot and lists    │
│ anything still open.                                 │
│                                                      │
│ Made from: Script snapshot v2, graded 90/100         │
│ against rubric 2.4 under sign-off rules 3.2.        │
│                                                      │
│ Still open (7): CC-101, CC-102, CC-103…             │
│                                                      │
│ ⚠ Attestation                                       │
│ {actor} confirms this report accurately represents   │
│ {org}'s decisions — and that it is not legal advice. │
│                                                      │
│ [Cancel]  [Release]                                  │
└─────────────────────────────────────────────────────┘
```

### Download and export

After release:
- **Download PDF:** renders the frozen snapshot as a paginated PDF document
- **Download JSON:** exports the structured snapshot data for integration with legal/insurance systems
- Both downloads are from the frozen artifact, not live data
- Download URLs are short-lived signed URLs regenerated on demand

### Role eligibility

| Role | Can generate | Can release | Can download |
|---|---|---|---|
| Owner | Yes | Yes | Yes |
| Admin | Yes | Yes | Yes |
| Reviewer | Yes | Yes | Yes |
| Editor | No | No | Yes (released reports only) |
| Viewer | No | No | Yes (released reports only) |

The mock incorrectly gates Admin and Reviewer from release. Production corrects this per the approved team-settings design: Owner, Admin, and Reviewer may perform governed report generation/release within authorized projects.

### Print behavior

The report page is marked for print isolation with `report-page` class:
- App chrome (header, sidebar, mobile nav) is hidden
- Stat bar and toolbar are hidden
- The print stylesheet overrides tab visibility to render all exhibits sequentially as one continuous document, regardless of which tab is active on screen
- Exhibits do not split across page breaks (`break-inside: avoid` on each exhibit)
- The "Skip to main content" link does not print
- The legal disclaimer appears once at the end, not repeated per exhibit
- Sticky exhibit tab bar does not print

### States

| State | Behavior |
|---|---|
| Loading | Skeleton stat cards and report document |
| Empty — no analysis run | "Run the analysis first" + link to `#new` |
| Draft — live preview | Full report from live data, "Generate snapshot" button |
| Generating | Progress indicator, poll-based |
| Generated — ready for release | "Snapshot ready" badge, Preview and Release buttons |
| Released | "Released" badge with timestamp, Download and See Record buttons |
| Stale — state changed after release | "State has changed since release" warning + "Generate new snapshot" button |
| Generation failed | Error with retry |
| Recoverable error | Retry preserves report state |
| Not found | Access-safe not-found for unknown project |

## Accessibility

All three surfaces:
- Render through the shared `page()` wrapper with breadcrumb
- Keyboard navigable: cadence radios, review dialog controls, exhibit tab navigation, sort/expand controls, and all action buttons
- Focus management: dialogs trap focus and restore on close; poll-based updates are focus-stable; exhibit tab navigation moves focus to the exhibit heading
- Coarse-pointer targets at least 44px
- Live regions announce: re-scan progress, monitoring check progress, generation progress, review confirmation, release confirmation
- Exhibit nav uses `aria-controls` linking tabs to exhibit sections
- Diff sections use `<del>` and `<ins>` with appropriate ARIA labels
- Reduced-motion honored
- Both themes across 320–1440px

## Responsive behavior

- **1440px:** Full layout, three-column monitoring config, side-by-side diffs, full exhibit tables
- **900px:** Monitoring config cards stack to two columns; diff panels stack vertically; exhibit tables may scroll horizontally
- **700px:** Single-column everywhere; exhibit nav scrolls horizontally; bottom nav
- **375px/320px:** Full-width cards; monitoring config stacks completely; report exhibits use card-based layouts instead of wide tables

## Required mock corrections

1. Separate the "Approve & create v2" button into a proposal flow (on `#item`) and a separate approval action (on `#item` by a different user). The versions page shows the result, not the trigger.
2. Replace synchronous selective re-scan with durable async job states: queued, running per-flag, completed, failed, cancelled.
3. Replace hard-coded `RESCAN_AFFECTED` IDs and stats with values computed from the structural diff between versions.
4. Replace destructive monitoring "reopen" (which nulls the prior decision) with superseding review records that preserve history.
5. Make the "See the review" button after monitoring review navigate to an addressable review record, not be inert.
6. Create an addressable follow-up task when "keep + follow-up" is selected.
7. Separate report generation from release into two distinct operations with separate buttons.
8. Make the released report read from a frozen snapshot, not live mutable state.
9. Correct role gating: Admin and Reviewer should be able to generate and release reports.
10. Fix print isolation: hide "Skip to main content," prevent exhibit page splits, prevent legal disclaimer orphaning.
11. Add cadence change rationale to Records (operational log, not governed audit).
12. Add complete loading, empty, running, failed, cancelled, stale, and error states to all three surfaces.
13. Add monitoring check progress (source count) during a running check.
14. Add materiality assessment to monitoring: distinguish material vs. non-material source changes.
15. Add re-import version support to `#versions` with structural diff summary.

No additional mock implementation changes are authorized by this document alone.

## Domain entities established

This design establishes the need for, without fixing final table or column names:

- `ScriptVersion` with immutable content, parent lineage, source type (import/rewrite), snapshot hash, and metadata
- `VersionDiff` with structural comparison: elements unchanged, modified, added, removed, moved, split, merged
- `RescanRun` with durable lifecycle, affected-item manifest, predecessor link, and per-item status
- `RewriteProposal` with full lifecycle: draft → proposed → approved/rejected/withdrawn → materialized → superseded
- `MonitoringRun` with trigger, source count, change count, materiality assessments, and terminal state
- `MonitoringChange` with verified-snapshot diff, materiality classification, and review-item link
- `MonitoringReview` with review effect (keep/reopen/refer), rationale, supersession link to prior decision, and audit event
- `FollowUpTask` with due date, assignee, source item, and completion state
- `ReportSnapshot` with frozen content, exact version bindings, content hash, and generation audit event
- `ReportRelease` with attestation, actor, timestamp, snapshot link, and release audit event
- `ReportExport` with format (PDF/JSON), signed URL, and download audit event

## Architecture gate

This approval completes the full surface review. Combined with the evidence workspace and notifications designs, it permits:

- Full preliminary database schema design across all domain entities
- Full preliminary OpenAPI contract design
- Version lineage and structural diff engine
- Durable re-scan, monitoring, and report-generation job infrastructure
- Frozen report snapshot and artifact storage
- Print/export rendering pipeline

The remaining surfaces (`#marketing`, `#sitemap`, `#states`) are public and prototype-only and do not affect the domain schema.

## Verification expectations

When implementation targets exist, verify:

- Maker/checker split: proposer cannot approve their own rewrite
- Rewrite approval atomically creates version, computes diff, and dispatches re-scan job
- Re-scan follows durable lifecycle with per-flag progress, cancellation, and continuation
- Cross-version item identity correctly classifies unchanged/affected/moved/removed/added items
- Monitoring runs follow durable lifecycle with source-count progress
- Materiality assessment distinguishes material, non-material, and unavailable changes
- Monitoring review creates superseding records, never deletes prior decisions
- "Keep + follow-up" creates an addressable follow-up task
- Report generation creates an immutable frozen snapshot with content hash
- Released report reads from frozen snapshot; post-release changes do not alter it
- Report release is a governed attestation with same-transaction audit
- Admin and Reviewer can generate and release reports
- Multiple snapshots can exist; releasing a new one supersedes the prior
- Download serves the frozen artifact via short-lived signed URLs
- Print hides chrome, prevents exhibit splits, and does not orphan the disclaimer
- Cadence changes are operational and do not require governed audit
- All durable jobs have idempotency, retries, leases, and reconciliation
- Keyboard, focus, live-region, 44px target, both-theme, and 320–1440px responsive behavior
- Loading, empty, running, failed, cancelled, stale, and error states on all three surfaces
- Cross-tenant and unauthorized access returns access-safe not-found

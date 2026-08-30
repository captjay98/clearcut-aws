# Evidence Workspace UI Design

**Date:** 2026-08-29
**Status:** Approved
**Surfaces:** `#project`, `#workspace`, `#items`, `#item`
**Depends on reviewed surfaces:** `#trust`, `#records`, `#team`, `#settings`, `#auth`, `#onboarding`, `#invite`, `#projects`, `#new`, `#notifications`

## Purpose

This design establishes the evidence workspace — the project overview, annotated screenplay, flags list/board, and single item detail — where reviewers read the script, examine evidence, make governed decisions, and manage clearance workflow. It defines the orthogonal item state model, evidence presentation, source provenance requirements, decision governance, assignment model, discussion semantics, and the relationship between these four surfaces.

The mock at `misc/clearcut-flow/` remains the visual and interaction source of truth. This document does not authorize mock implementation changes beyond the approved layout corrections already applied.

## Approved decisions

1. `#project` is a read-only project health summary with navigation entry points to the other surfaces. No governed actions happen here.
2. The project overview uses a two-column grid ("Needs a decision" + "Progress" side by side). The duplicate sidebar cards ("Next step" and "The final call") are removed. The contextual primary action lives in the page header only.
3. `#workspace` uses a three-panel layout: scene rail (left), screenplay text (center), evidence drawer (right). Mobile uses three tabs: Script, Scenes, Evidence.
4. The screenplay page uses a fixed width of `min(100%, 76ch)` to maintain the screenplay document metaphor. The page does not grow when panels collapse.
5. The scene rail is a spatial navigator — scene groups with flags showing derived status badges. No filtering; that lives on `#items`.
6. The evidence drawer supports quick governed decisions via the same confirmation dialog as `#item`. Actions available in the drawer: Verify, Rule out, Refer to specialist, Full record. Complex actions (rewrite, reassign, comment) go to `#item`.
7. The drawer shows the best source plus a count and conflict summary ("4 sources · 1 disagrees") linking to `#item`. It does not show the full source table.
8. The drawer content is state-adaptive: different layouts for research-running, no-sources, sources-found, research-failed, disposition-recorded, and referred states.
9. The screenplay shows the current (latest) version by default with a version switcher to view earlier locked versions.
10. `#items` uses filter buttons derived from the orthogonal state model, applied consistently to both List and Board views. Filter state is URL-addressable.
11. `#items` supports bulk actions via checkboxes: bulk assign, bulk set due date, bulk refer. Governed per-item decisions (verify, rule out, dispose) are not available as bulk actions.
12. `#items` Board view groups columns by derived status: Needs attention, Awaiting decision, Conflicting, Referred, Resolved, Unresolvable. An item appears in exactly one column.
13. `#item` actions live in the sidebar only (2×2 button grid). The main column is purely informational: script context, evidence, and discussion. No duplicate action buttons.
14. `#item` actions are state-adaptive — only applicable actions for the current item state are shown.
15. `#item` supports prev/next navigation through the filtered item set that the reviewer entered from.
16. Comments are per-item, chronological, one-level-deep threaded, with edit history preserved. System-generated action entries appear in the same timeline. Comments support @mentions that trigger notifications.
17. Items are URL-addressable with stable deep links. Unknown or unauthorized item IDs show a proper not-found state, never silently fall back to a different item.

## Orthogonal item state model

Each clearance item has six independent state dimensions. The UI derives a single display badge from these dimensions, but the badge is never stored as the source of truth.

### Dimension 1: Research execution state

```text
not_started → queued → running → completed
                               ↘ failed → manual_retry
                               ↘ cancelled
```

Tracks whether mandatory Parallel Search has run and what happened. Search completion does not wait for optional Extract enrichment when a complete attributable Search snapshot is already available.

### Dimension 1b: Extract enrichment state

```text
not_requested → queued → running → completed
                            ↘ partial
                            ↘ failed → manual_retry
```

Tracks bounded enrichment for up to three server-selected Search URLs. `partial` and `failed` never erase valid Search snapshots. This dimension changes provenance/diagnostic presentation, not the human disposition.

### Dimension 2: Evidence assessment

```text
pending → supporting | conflicting | insufficient | unavailable
```

Derived from source analysis after research completes. `pending` while research is running. `unavailable` when research returned no usable sources.

### Dimension 3: Workflow

```text
unassigned → assigned → referred → referral_acknowledged
                      ↘ reassigned
```

Tracks who owns the item and whether it's been sent to a specialist.

### Dimension 4: Remediation

```text
none → draft_proposed → proposed → approved | rejected | withdrawn
                                 → materialized_in_version → superseded
```

Tracks the rewrite lifecycle for this item.

### Dimension 5: Disposition

```text
pending → verified | ruled_out | fixed_in_rewrite | deferred
```

The final human call. Only recorded through a governed action with rationale and audit.

### Derived display badges

The UI calculates a display badge from the five dimensions:

| Display badge | Derivation |
|---|---|
| Searching… | Research = running |
| Research failed | Research = failed |
| No sources | Research = completed, assessment = unavailable |
| Needs your call | Research = completed, disposition = pending, no referral |
| Sources disagree | Research = completed, assessment = conflicting, disposition = pending |
| With specialist | Workflow = referred |
| Must fix | Disposition = pending, remediation has blocking policy finding |
| Verified | Disposition = verified |
| Fixed in v2 | Disposition = fixed_in_rewrite |
| Ruled out | Disposition = ruled_out |
| Deferred | Disposition = deferred |
| Overdue | Any unresolved item past its due date |

## `#project` — Project overview

### Layout

The page header shows the project name, production details, and two contextual actions:
- "Open screenplay" (always)
- A primary action that changes based on project state: "Work the flags that need you" → "Re-check the changed scenes" → "Review the source change" → "Release the clearance report" → "Read the record of actions"

Below the header, a stat grid shows: Flags raised, Sources verified, Needs attention, Current version.

Below the stats, a two-column grid:
- **Needs a decision** — list of attention items (blocked, conflicting, referred) with click-to-open navigation to `#item`. Empty state when all items are resolved.
- **Progress** — checklist card showing milestone completion (Script imported, Sources checked, Rewrite approved, Changes re-checked, Source change reviewed, Report released) with a verification percentage bar.

### Project isolation

The overview renders only the selected project's real data, scoped by authenticated `org_id` + `project_id`. Selecting a project with no imported script shows appropriate empty states (dashes in stat cards, empty decision list, only "Script imported" as pending).

### States

| State | Behavior |
|---|---|
| Loading | Skeleton stat cards and list rows |
| Empty — no script | Stats show dashes, progress shows only first milestone |
| Empty — no flags | "Nothing blocking" empty state in the decision section |
| Recoverable error | Retry preserves project context |
| Not found | Access-safe not-found for unknown project slug |
| Success | Full dashboard with live stats |

## `#workspace` — Annotated screenplay

### Three-panel layout

**Scene rail (left, 220–260px):**
- Grouped by scene number with slug and flag count
- Each flag shows: severity glyph, term, category badge, derived status badge
- Click a scene to scroll the center panel; click a flag to select it and open the drawer
- No filtering — the rail is a spatial index

**Screenplay text (center, flexible):**
- Script pages at `min(100%, 76ch)` on a dark stage background
- Colored stock strips on the left edge (white for v1, blue for v2, etc.)
- Flagged terms are underlined inline with severity-coded border and margin marks in the left gutter
- Clicking a flagged term selects it (highlighted, `aria-pressed`) and opens the evidence drawer
- Version switcher at the top: dropdown to switch between v1, v2, etc.
- Rewritten passages show a revision asterisk in the right margin

**Evidence drawer (right, min(400px, 32vw)):**
- Opens when a flag is selected; closes with the × button
- Header: category, term, ID/scene/page, close button
- Body content is state-adaptive (see below)
- Footer: governed action buttons

### Drawer content by item state

**Research running:**
- Spinner + "Searching for sources…"
- Progress text: "Checking 3 of 10 categories"
- No actions

**Search complete, Extract enrichment running:**
- Render admitted Search excerpts immediately when complete enough for review
- Inline status: "Reading selected sources for stronger excerpts…"
- No false completed-enrichment indicator

**Extract partial or failed:**
- Preserve every valid Search/Extract source card
- Warning: "Some selected pages could not be read — 2 enriched · 1 unavailable"
- Link to the filtered Records attempts
- Governed actions remain available only when at least one snapshot independently passes evidence admission

**Research complete, no sources:**
- Empty state: "No sources retrieved — Parallel search returned no results for this term"
- Confidence: N/A
- Actions: Full record only

**Research complete, sources found (normal case):**
- Status badge + priority
- Best source card: authority tier, record name, excerpt, retrieval date, provenance link
- Source summary: "4 sources · 1 disagrees" linking to `#item`
- Conflict banner if applicable
- Confidence meter with text percentage
- Assignee + due date
- Actions: Verify / Rule out / Refer / Full record

**Research failed:**
- Error state: "Source search failed"
- Retry button if retryable
- Actions: Full record

**Disposition recorded:**
- Recorded decision badge (Verified / Fixed in v2 / etc.)
- Who recorded it and when
- Actions: Full record only

**Referred to specialist:**
- Referral badge + specialist name
- "Awaiting specialist review"
- Actions: Full record only

### Drawer actions and governance

"Verify this source" and "Rule this source out" in the drawer open the same governed decision dialog used on `#item` — with rationale field, confirmation, and same-transaction audit event. After recording, the flag's severity marker and drawer state update in place without leaving the screenplay.

Actions available in the drawer:
- Verify this source (Reviewer+)
- Rule this source out (Reviewer+)
- Refer to specialist (Editor+)
- Full record (navigates to `#item`)

Actions not in the drawer (require `#item`):
- Propose rewrite (needs text editor)
- Reassign (needs member picker)
- Comment (needs thread context)
- Approve/reject rewrite (needs full evidence review)

### Mobile (≤900px)

Three tabs: Script, Scenes, Evidence.
- Script tab: read the screenplay with flagged highlights; tap a flag to auto-switch to Evidence tab
- Scenes tab: scene rail as a full-screen list; tap to scroll Script tab
- Evidence tab: drawer content as a full-screen panel

### Version switching

The version switcher is a dropdown at the top of the screenplay stage. Switching versions re-renders the script text with that version's content. Margin marks and flag highlights remain for flagged terms that exist in the selected version. Rewritten passages are visible in v2+ with revision marks.

## `#items` — Flags list and board

### Filter buttons

Derived from the orthogonal state model and applied consistently to both List and Board views:

| Button | Query |
|---|---|
| **All** | Everything |
| **Needs attention** | Overdue OR source-changed-after-verify OR research-failed |
| **Awaiting decision** | Research complete + no disposition |
| **Conflicting** | Evidence assessment = conflicting |
| **Referred** | Workflow = referred |
| **Resolved** | Disposition recorded (verified, fixed, ruled out, deferred) |
| **Unresolvable** | Research complete + no usable sources |

Filter state is URL-addressable: `#items?filter=attention&sort=due`.

Additional filter controls:
- Search box (term, ID)
- Category dropdown (ten categories)
- Assignee dropdown
- Due date range
- Scene range

### Sort options

Term, Severity, Confidence, Scene, Due, Status (derived badge).

### Group options

No grouping, Scene, Category, Owner, Due date.

### List view rows

| Column | Content |
|---|---|
| Checkbox | Selection for bulk ops |
| Term | The flagged term |
| ID + Category | CC-101 · Brands & trademarks |
| Scene | Scene 3 · p.2 |
| Sources | 4 sources · 1 disagrees |
| Confidence | 92% |
| Assignee | Avatar + initials |
| Severity | High / Medium / Low |
| Status | Derived display badge |

On mobile, rows become cards with primary info (term, status, assignee, severity) visible and secondary info (sources, confidence, scene) stacked below.

### Board view

Columns grouped by derived status:

| Column | Items |
|---|---|
| **Needs attention** | Overdue, source-changed, research-failed |
| **Awaiting decision** | Research done, no disposition |
| **Conflicting** | Sources disagree |
| **Referred** | With specialist |
| **Resolved** | Verified, fixed, ruled out |
| **Unresolvable** | No usable sources |

An item appears in exactly one column. Filters hide entire columns when empty or excluded. Column headers show counts. Cards are not drag-and-drop — changing an item's status requires the proper governed action flow.

### Bulk actions

When one or more checkboxes are selected, a bulk action bar appears:

```
3 selected   [Assign to…]  [Set due…]  [Refer…]   Clear
```

Available bulk actions:
- Bulk assign — assign multiple items to one person
- Bulk set due date — set the same deadline
- Bulk refer — refer multiple items to the same specialist

Not available as bulk actions:
- Verify / rule out (need per-item rationale)
- Propose rewrite (need per-item text)
- Dispose (need per-item reasoning)

Each bulk action opens a confirmation dialog and commits atomically with audit events for each affected item.

### States

| State | Behavior |
|---|---|
| Loading | Skeleton rows, filter controls visible but disabled |
| Empty — no items detected | "No flags found" + link to run analysis |
| Empty — filters match nothing | "No items match" + clear-filters action |
| Recoverable error | Retry preserves filters |
| Not found | Access-safe not-found for unknown project |
| Success | Filtered, sorted, grouped list or board |

## `#item` — Single item detail

### URL addressability

Each item has a stable deep link: `/orgs/{org_slug}/projects/{proj_slug}/items/{item_id}`.

Unknown or unauthorized item IDs show a not-found state that echoes the typed ID. The page never silently falls back to a different item.

### Layout

**Main column (left):**

1. **Script context** — the flagged line with surrounding text, anchored to a stable span. Shows which script version the context is from.
2. **Evidence** — primary source card (highest authority), full source table, confidence meter, conflict banner.
3. **Discussion** — chronological timeline of comments and system-generated action entries.

**Sidebar (right):**

1. **Your call** — 2×2 button grid of available governed actions. State-adaptive: only applicable actions are shown. Gated by role with focusable restriction explanations.
2. **Ownership** — assignee, due date, priority, version binding, creation date, and reassign/change controls.
3. **Related** — other items in the same category and same scene, clickable to navigate.

### Prev/next navigation

When entering `#item` from a filtered `#items` view, the page header includes prev/next arrows that cycle through the filtered set:

```
← CC-101 Vega Camera                               →
  2 of 4 needing your call
```

"Back to items" returns to the `#items` view with the original filter preserved.

### Actions by item state

| State | Available actions |
|---|---|
| Research running | None — wait for evidence |
| Research complete, no disposition | Verify, Rule out, Refer, Propose rewrite, Reassign |
| Referred | Acknowledge referral (specialist), Reassign |
| Disposition recorded (verified) | Propose rewrite, Reassign (re-decision requires explicit reopen) |
| Disposition recorded (ruled out) | Propose rewrite, Reassign |
| Rewrite proposed | Approve rewrite, Reject rewrite (Reviewer+) |
| Fixed in rewrite | View only — resolved |
| Research failed | Retry research, Reassign |

Actions that don't apply to the current state are not rendered — no disabled buttons for inapplicable actions.

### Evidence section

**Primary source card:**
- Authority tier badge
- Source name and record identifier
- Attributable excerpt
- Retrieval timestamp with exact time
- "Where this came from" expands to full provenance: URL, publisher, query identity, research run ID, snapshot ID

**Full source table:**

| Column | Content |
|---|---|
| Source | Name and record identifier |
| ID | SRC-001, linked to snapshot |
| Retrieved | Date and time |
| Authority | Tier badge |
| What it says | Excerpt |
| Bearing | Supports / Disagrees / Context |

Each row is expandable to show full provenance: URL, publisher classification, stance reasoning, query that found it, research run ID, and snapshot retention status.

**Below the table:**
- Confidence meter with percentage text (not color-only)
- Conflict banner naming which sources conflict and why
- "No sources" empty state if research returned nothing
- "Research failed" error state with retry action

**Version binding:** The evidence section shows which script version it was gathered against. "Evidence gathered on v1 · 4 sources" or "Re-checked on v2."

### Discussion

Comments are per-item, chronological, one-level-deep threaded.

**Comment features:**
- Author avatar + name, timestamp, comment text
- One level of replies: you can reply directly to a comment, but replies cannot have replies
- Edit with full history: edited comments show "(edited)" indicator; clicking reveals the original and all edit history with timestamps
- System-generated action entries in the same timeline: "Mara Voss verified this source — Aug 19" (linked to audit event)
- @mentions with autocomplete from project member list; mentioned users receive an action-required notification
- Immutable action entries are never editable
- Visible to all project members who can access this item (Viewer+)
- Only Editor+ can add comments

### Print behavior

`#item` is printable for offline review or legal handoff. App chrome is hidden. Evidence table and provenance are intact. Same print isolation pattern as the report.

### Role gating

| Role | Capabilities on `#item` |
|---|---|
| Owner | All actions |
| Admin | All actions |
| Reviewer | Verify, rule out, refer, approve/reject rewrite, comment |
| Editor | Refer, propose rewrite, reassign, comment |
| Viewer | Read-only — no action buttons, evidence and discussion visible |

Gated buttons remain focusable with restriction explanations, matching the pattern used across all surfaces.

### States

| State | Behavior |
|---|---|
| Loading | Skeleton for script context, evidence table, and sidebar cards |
| Empty — research running | Spinner in evidence section, no actions available |
| Empty — no sources | "No sources retrieved" with explanation |
| Recoverable error | Retry preserves item context |
| Permanent error | Names the failure without exposing internals |
| Not found | Echoes the typed item ID, never falls back to a different item |
| Success | Full evidence, discussion, and actions |

## Accessibility

All four surfaces:
- Render through the shared `page()` wrapper with breadcrumb navigation
- Breadcrumb sits 16px below the header bar across all surfaces
- Keyboard navigable: all controls, filters, sort buttons, checkboxes, flag highlights, drawer actions, and dialog interactions
- Focus management: selecting a flag moves focus to the drawer; closing the drawer restores focus to the flag; dialogs trap focus and restore on close; prev/next navigation moves focus to the new item heading
- Coarse-pointer targets at least 44px
- Live regions announce: filter changes, bulk action results, governed decision confirmation, new comments, research progress, sort/group changes
- `aria-pressed` on flag highlights and filter buttons
- `aria-current` on active scene in the rail
- Confidence meters have text equivalents, not color-only meaning
- Reduced-motion settings honored
- Script and Night shoot themes maintain equivalent contrast, states, and hierarchy from 320 through 1440px

## Responsive behavior

- **1440px:** Full sidebar, three-panel screenplay, standard list/board, two-column item detail
- **900px:** Sidebar becomes drawer; screenplay tabs replace three-panel; list rows may wrap; item sidebar stacks below main
- **700px:** Bottom nav; single-column layouts; board may become a horizontal scroll or stack
- **375px/320px:** Full-width cards; filter buttons scroll horizontally; screenplay pages fill the screen; item actions stack in single column

## Required mock corrections

### Already applied
1. Removed duplicate sidebar cards ("Next step" and "Final call") from `#project` overview.
2. Changed overview layout from `grid-sidebar` to `grid-2` for "Needs a decision" and "Progress" side by side.
3. Fixed section alignment inside grids: `.grid > .section + .section { margin-top: 0; }`.
4. Tightened breadcrumb to header: page top padding from `--space-8` to `--space-4` across all surfaces.
5. Widened screenplay pages from 68ch to 76ch to eliminate margin-mark overflow.
6. Removed duplicate action buttons from `#item` main column.
7. Changed `#item` sidebar action layout from `stack-sm` to `grid grid-2` (2×2 buttons).

### Still required for production
8. Make `#item` URL-addressable with stable item IDs; show not-found for unknown IDs.
9. Add prev/next navigation on `#item` preserving the filter context from `#items`.
10. Fix Board view to respect active filters (currently shows all items while filter button stays pressed).
11. Add source count column ("4 sources · 1 disagrees") to `#items` list rows.
12. Replace drawer's single-source view with best source + count/conflict summary.
13. Make drawer content state-adaptive for all research/workflow/disposition states.
14. Add version switcher to `#workspace` screenplay stage.
15. Add version binding display to `#item` evidence section.
16. Implement one-level-deep threaded comments with edit history and @mentions.
17. Add system-generated action entries to the discussion timeline.
18. Scope all data to authenticated `org_id` + `project_id`; eliminate cross-project data leaks.
19. Add bulk action bar for multi-item selection on `#items`.
20. Add complete loading, empty, error, not-found, and research-in-progress states to all four surfaces.
21. Add print isolation for `#item`.
22. Enforce role gating on all actions with focusable restriction explanations.

No additional mock implementation changes are authorized by this document alone.

## Domain entities established

This design establishes the need for, without fixing final table or column names:

- `ClearanceItem` with five orthogonal state dimensions and stable identity across versions
- `EvidenceClaim` with mandatory `SourceSnapshot` provenance (URL, retrieval time, excerpt, publisher/authority, stance, query/run identity)
- `EvidenceDecision` (verify, rule out) with rationale, actor, version binding, and audit event
- `SpecialistReferral` with specialist type, notes, referral state, and audit event
- `RewriteProposal` with proposed text, rationale, proposer, and lifecycle state
- `Assignment` with assignee, due date, priority, and audit event
- `Comment` with author, timestamp, optional parent (one level), edit history, and @mentions
- Derived display badge computation from the five state dimensions
- Filter/sort/group query model operating on real state dimensions
- Bulk action model for assign, due date, and refer operations
- Prev/next navigation context (the filtered item set and current position)

## Architecture gate

This approval, combined with the notifications design, permits preliminary schema and API design for:

- ClearanceItem with orthogonal state dimensions
- EvidenceClaim and SourceSnapshot provenance
- EvidenceDecision, SpecialistReferral, and RewriteProposal records
- Assignment, Comment, and @mention records
- Filter/sort/group query endpoints
- Bulk action endpoints with atomic audit
- Item deep-link routing

Do not freeze the following until their surface reviews are approved:

- Version lineage, cross-version item identity, and selective re-scan schema → requires `#versions` review
- Monitoring lifecycle and source-change review schema → requires `#watch` review
- Report generation, release, snapshot, and export schema → requires `#report` review

## Remaining review order

1. `#versions`, `#watch`, `#report` — revision lineage, selective re-scan, monitoring, report lifecycle.
2. `#marketing`, `#sitemap`, `#states` — public and prototype-only surfaces.

## Verification expectations

When implementation targets exist, verify:

- Five orthogonal state dimensions persist independently and derive correct display badges
- All governed decisions (verify, rule out, refer, approve rewrite) open confirmation dialogs with rationale and commit with same-transaction audit events
- Drawer and `#item` use the same decision dialog and governance path
- Source provenance is complete on every `EvidenceClaim` (URL, retrieval time, excerpt, publisher/authority, stance, query/run identity, snapshot ID)
- Zero-evidence items show unresolved state, never clearance
- Project isolation: selecting a different project shows only that project's data
- Item URL addressability: direct links resolve to the correct item; unknown IDs show not-found
- Prev/next navigation cycles through the filtered set and preserves filter on Back
- Filters apply consistently to both List and Board views
- Bulk actions commit atomically with per-item audit events
- One-level-deep threaded comments with edit history preservation
- @mentions trigger action-required notifications
- System-generated action entries appear in the discussion timeline
- Version binding is visible on evidence section
- State-adaptive drawer and action set for all item states
- Role gating with focusable restriction explanations
- Print isolation for `#item`
- Keyboard, focus, live-region, 44px target, both-theme, and 320–1440px responsive behavior
- Loading, empty, error, not-found, and research-in-progress states on all four surfaces

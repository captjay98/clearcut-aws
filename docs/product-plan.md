# ClearCut Product Plan

*Migrated 2026-08-28 from hackathons/clearcut · Reconciled with the baseline design (2026-08-19)*
*Original: 2026-08-20 · Concept locked 2026-08-20*

## Product Thesis

Independent producers and screenwriters routinely ship scripts that contain real people, brands, trademarks, music, quotations, identifiable locations, and historical claims. Each of these may require clearance research before production. Without an internal clearance department, the work falls on the producer: read the script, flag every risky item, search the web for current evidence, decide what needs specialist review, and re-do all of it when the script changes.

That process is slow, error-prone, and rarely versioned. It is also the exact kind of friction an agent is good at removing: structured extraction, reproducible search, evidence preservation, and re-evaluation on change.

ClearCut is a **pre-clearance evidence desk**. It does not give legal clearance. It converts a script into a structured, source-backed research workspace where a human makes the final calls.

## Primary Users

- **Independent producers** without an internal clearance department.
- **Screenwriters** evaluating production risk before locking a draft.
- **Production coordinators and clearance researchers** managing evidence and follow-up.
- **Small production legal teams** tracking evidence and specialist referrals.

## User Journey

1. Create an organization and invite team members with fixed roles.
2. Create a film project with production details.
3. Import a screenplay (paste, Fountain, PDF, or Final Draft).
4. Parse scenes, characters, dialogue, props, locations, and music cues.
5. Detect items that may require investigation across 10 clearance categories.
6. Run mandatory Parallel Search for each item and bounded Extract on selected returned URLs.
7. Review evidence cards — sources, conflicts, confidence, provenance.
8. Assign work, set due dates, add comments, or accept a proposed replacement.
9. Refer items to a specialist (status change + notification, not a separate portal).
10. Create a new script version after rewrites; selective re-scan of affected items.
11. Monitor sources manually, daily, or weekly for material changes.
12. Record final dispositions — accountable human calls, not legal conclusions.
13. Generate a version-bound clearance report snapshot, then release that frozen snapshot through a separate accountable action.

## Capabilities

All 47 features are retained and enumerated in the [feature ledger](feature-ledger.md). The ledger maps each feature to its owning plan (01–08) in the baseline design.

### Script ingestion and structure (9 features)
Paste, Fountain, PDF, and Final Draft (.fdx) import. Scene and page references. Character, dialogue, prop, location, and music-cue extraction. Draft/version comparison. Changed-clearance-element detection.

### Detection categories (10 features)
People and likeness. Names and characters. Brands and trademarks. Products and trade dress. Locations and property. Music and lyrics. Artwork and media. Dialogue and quotations. Organizations and insignia. Privacy and sensitive facts.

### Parallel-powered evidence (9 features)
Mandatory Parallel Search runtime calls with bounded Extract enrichment. Search query generation by item type. Current source URLs, titles, dates, excerpts. Source-authority classification. Conflicting-evidence detection. Confidence and unresolved/partial-enrichment states. Evidence freshness. Saved capability/query/response provenance. Scheduled source-change monitoring with conditional Monitor event-stream signals.

### Workflow product (10 features)
Item status workflow. Evidence attachments. Suggested alternatives or rewrites. Re-scan after revision. Clearance progress dashboard. Exportable evidence packet. Assignments and due dates. Comments and notes. Related-item grouping across scenes. Audit trail with agent runs, tool calls, judge evaluations, and learning records.

### Non-AI product (9 features)
Hosted web experience. Project/script storage. Script viewer with scene annotations. Item/evidence database. Search, filters, sort, and grouping. Revision history. Document export. Authentication, organizations, and fixed roles. Secure source and file handling.

## Agent vs Deterministic Responsibilities

### Agent (Gemini + ADK)
- Convert screenplay context into structured candidate items.
- Produce typed item-specific research objectives/queries; deterministic application policy selects provider mode, budgets, URLs, and retry behavior.
- Generate narrow, reproducible searches.
- Synthesize evidence without converting uncertainty into legal conclusions.
- Identify contradictions and missing evidence.
- Propose next actions and lower-risk creative alternatives.
- Re-evaluate affected items after a script change.

### Deterministic (code, not model)
- File parsing and version identifiers.
- Schema validation.
- Evidence/source storage.
- Status transitions and governed-action gates.
- Assignment and deadline rules.
- Capability-guarded authorization (fixed roles, not model-decided).
- Export generation.
- Audit records (transactional, not best-effort for critical decisions).
- Deterministic block/warn gates before output acceptance.
- Judge evaluation orchestration (separate model, separate prompt).

## Partner Necessity (Parallel)

Parallel is load-bearing. ClearCut cannot produce current, sourced evidence without a live web research layer. The integration must be visible in:

- **Code** — mandatory Parallel Search plus bounded Extract through the official `parallel-web` SDK. Conditional Monitor uses only `event_stream` after a recorded go/no-go; Task, FindAll, Responses/Chat, Interactions, Deep Research, snapshot Monitor, alternate research providers, and silent fallbacks are excluded.
- **Tool traces** — safe provider capability, IDs/session, redacted arguments, duration, result/error counts, usage, status, and linked snapshots are recorded. Hidden model/provider reasoning is not logged.
- **Evidence cards** — each card shows the source URL, title, date, excerpt, authority, and stance (supports/disagrees/context) returned by Parallel.

This is what the Technological Implementation criterion (25%, first tie-breaker) rewards: the partner is essential, not decorative.

## Architecture

Defined in the [baseline design](docs/plans/2026-08-19-clearcut-planning-baseline-design.md) §4. Summary:

| Component | Responsibility |
|---|---|
| Astro site (Cloud Run) | Marketing and competition-facing pages |
| TanStack Start app (Cloud Run) | Authenticated workspace |
| FastAPI modular monolith (Cloud Run) | API, ADK agent runtime, background jobs |
| Cloud SQL PostgreSQL | Projects, scripts, items, evidence, decisions, audit |
| Cloud Storage | Uploaded scripts, snapshots, exports |
| Gemini + Google ADK | Detection, search planning, evidence synthesis, rewrite proposals |
| Parallel Search API | Mandatory live source discovery and focused Search excerpts |
| Parallel Extract API | Bounded focused excerpts for selected Search URLs |
| Parallel Monitor event stream | Conditional new-event signals that require Search/Extract verification |
| Cloud Tasks | Durable async execution |
| Cloud Scheduler | Monitoring cadence |
| Configured identity adapter | Local PostgreSQL auth by default; optional Firebase/Identity Platform; PostgreSQL authorization |
| Secret Manager | Provider credentials |

## Collaboration and Authorization

Fixed roles per baseline §8:

- **Owner** — organization lifecycle, ownership, protected settings, and all governed review/report actions.
- **Admin** — membership, projects, providers, operational settings, and all governed review/report actions; protected settings are read-only.
- **Editor** — script import, research, assignment, comments, and rewrite proposals.
- **Reviewer** — evidence decisions, referrals, dispositions, rewrite approval, and governed report generation/release.
- **Viewer** — read-only access to authorized projects and released reports.

Authorization enforced in backend repositories, not only in routes or UI. Capability guards disable controls with a stated reason rather than hiding them.

## Demo Data Strategy

- Entrant-owned original screenplay — no third-party IP in the demo.
- Fictional entities that trigger real Parallel results.
- Demonstrate several clearance-item types across the 10 categories.
- One live mandatory Parallel Search in the demo, plus truthful bounded Extract status. Show a Monitor signal only if the exact deployed candidate passed the Monitor go/no-go and subsequent Search/Extract verification. On provider failure, show a visible unresolved review item. A prior fully provenanced snapshot may be shown only as explicitly stale historical context and cannot satisfy the current research run or become fallback evidence.
- All evidence traces to real Parallel output with real URLs.

## Delivery

Implementation follows Plans 01–08 in the baseline design, with dependency gates and exit criteria between plans. The feature ledger maps every feature to its owning plan.

The mock UI prototype (`misc/clearcut-flow/`) is the design source of truth for the visual identity and interaction patterns of the production application.

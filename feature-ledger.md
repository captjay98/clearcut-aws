# ClearCut Feature Ledger

*Migrated 2026-08-28 from hackathons/clearcut · Reconciled with the baseline design (2026-08-19)*
*Original: 2026-08-20 · Build window: Jul 27 – Sep 9, 2026*

## Ledger Principle

ClearCut competes on **four equally weighted criteria** (Technological Implementation is the tie-break). All 47 features are retained — none deferred, none removed. Build order follows Plans 01–08 in the baseline design, with dependency gates between plans.

The golden path: **paste/Fountain/PDF/FDX script → detect clearance items across 10 categories → Parallel evidence cards with conflicts and provenance → accept a rewrite → re-scan affected items → monitor sources → generate a version-bound clearance report**, on a hosted web app with an annotated screenplay workspace, fixed roles, and governed human decisions.

## Verdict Summary

- **Keep: 47** (full feature universe)
- **Defer: 0**
- **Remove: 0**

## Change Log

| Date | Change |
|---|---|
| 2026-08-20 | Initial ledger created (~44 estimate, actual count 47) |
| 2026-08-28 | Migrated to standalone repo. Reconciled with baseline design. Scope expansions noted below. Build-priority tiers replaced with Plan 01–08 mapping. |

### Scope Expansions (baseline design overrides original scoping)

- **Authentication and project membership** — originally "Keep (minimal) — single-user, do not build team auth." Expanded to full organizations, invitations, memberships, and fixed RBAC (Owner, Admin, Editor, Reviewer, Viewer) per baseline §8.
- **Audit trail** — originally "append-only event log." Expanded to first-class agent runs, tool calls, judge evaluations, and learning records per baseline §6.5, §12, §17.
- **Monitoring** — originally "on-demand change check first, full scheduler is stretch." Expanded to configurable manual/daily/weekly monitoring with review items per baseline §6.4, §7.

---

## Script Ingestion and Structure — 9 features

| # | Feature | Plan | Notes |
|---|---|---|---|
| 1 | Pasted text | 02 | Primary input; simplest, zero parse risk |
| 2 | Fountain import | 02 | Plaintext screenplay format; easy to parse |
| 3 | PDF import | 02 | Via Gemini File API (multimodal PDF → script structure) |
| 4 | Final Draft (.fdx) import | 02 | Open XML format; industry-standard tool |
| 5 | Scene and page references | 02 | Needed for the annotated viewer |
| 6 | Character/dialogue parsing | 02 | Core to detection |
| 7 | Prop, location, music-cue extraction | 02 | Core to detection |
| 8 | Draft/version comparison | 06 | Needed for re-scan — diff at stable element/span level |
| 9 | Changed-clearance-element detection | 06 | The re-scan trigger |

## Detection Categories — 10 features

All 10 categories are retained. Detection is a Gemini agent classification, not separate code paths, so adding categories is low-cost. The "uncertainty stays visible" principle handles hallucination risk on the harder categories.

| # | Feature | Plan | Notes |
|---|---|---|---|
| 10 | People & likeness | 03 | Real-person identity, resemblance, and depiction concerns; current evidence remains bounded and non-legal |
| 11 | Names & characters | 03 | Fictional/real name and character conflicts, with uncertainty visible |
| 12 | Brands & trademarks | 03 | High demo value; Parallel evidence may include registries and brand sources |
| 13 | Products & trade dress | 03 | Product appearance, packaging, distinctive configuration, and visible design context |
| 14 | Locations & property | 03 | Identifiable places, venues, property depiction, and production-use context |
| 15 | Music & lyrics | 03 | Compositions, recordings, titles, lyrics, and rights-context evidence |
| 16 | Artwork & media | 03 | Books, films, artwork, photographs, posters, clips, and other embedded media |
| 17 | Dialogue & quotations | 03 | Quoted, adapted, attributed, or potentially source-derived language |
| 18 | Organizations & insignia | 03 | Organizations, badges, seals, uniforms, and institutional identifiers |
| 19 | Privacy & sensitive facts | 03 | Biographical, health, contact, identifier, and other sensitive factual content |

## Parallel-Powered Evidence — 9 features

| # | Feature | Plan | Notes |
|---|---|---|---|
| 20 | Parallel runtime calls | 03 | Search is mandatory/load-bearing; Extract is bounded enrichment; Monitor event stream is conditional. Exact capability must be visible in code/traces, not just README. |
| 21 | Search query generation by item type | 03 | Core agent work; visible in tool traces |
| 22 | Current source URLs, titles, dates, excerpts | 03 | Search excerpts plus selected Extract enrichment, with origin recorded |
| 23 | Source-authority classification | 03 | Heuristic ranking (official > news > blog); good for trust story |
| 24 | Conflicting-evidence detection | 03 | Key demo beat — shows uncertainty, not false certainty |
| 25 | Confidence and unresolved states | 03 | Includes Search empty/failure and Extract partial/total failure; uncertainty stays visible |
| 26 | Evidence freshness | 03 | Timestamp display; retrieval time |
| 27 | Saved query, response receipt, and provenance | 03 | Store capability, query/attempt identity, provider IDs/session, typed/redacted receipt, immutable origin-labelled snapshots, and protected raw payload only where required |
| 28 | Monitoring for source changes | 07 | Scheduled Search/Extract manual/daily/weekly; conditional signed Monitor signals are re-verified; only verified material change creates review |

## Workflow Product — 10 features

| # | Feature | Plan | Notes |
|---|---|---|---|
| 29 | Item status workflow | 05 | Needs your call, Verified, Sources disagree, With specialist, Could not verify, Must fix, Fixed in v2 |
| 30 | Evidence attachments | 03 | Link evidence to items; core data model |
| 31 | Suggested alternatives or rewrites | 05 | Key demo beat — accept a rewrite, re-scan |
| 32 | Re-scan after revision | 06 | Core golden-path beat; selective, not full re-run |
| 33 | Clearance progress dashboard | 04 | Status counts, stat cards, next-step CTA |
| 34 | Exportable evidence packet | 06 | Version-bound clearance report with Exhibits A–E |
| 35 | Assignments and due dates | 05 | Per-flag assignment with owner and due date |
| 36 | Comments and notes | 05 | Per-ClearanceItem, one reply level only, timestamped, actor-identified, editable through immutable revision history, with mentions |
| 37 | Related-item grouping across scenes | 04 | Group field + query; handles recurring items across a script |
| 38 | Audit trail | 05, 07 | Authoritative immutable `AuditEvent`s; redacted Receipt projections; distinct agent runs, tool calls, judge evaluations, learning records, and provider/security events. Critical decisions commit transactionally. |

## Non-AI Product — 9 features

| # | Feature | Plan | Notes |
|---|---|---|---|
| 39 | Hosted web experience | 01, 08 | Cloud Run; mandatory submission requirement |
| 40 | Project/script storage | 02 | Cloud SQL + Cloud Storage |
| 41 | Script viewer with scene annotations | 04 | The visual centerpiece; annotated screenplay workspace |
| 42 | Item/evidence database | 02, 03 | Cloud SQL PostgreSQL |
| 43 | Search, filters, sort, and grouping | 04 | Live text search, 4 sort columns, grouping by scene/category/severity/status, deep-link filtering |
| 44 | Revision history | 06 | Immutable script versions with stable element identifiers |
| 45 | Document export | 06 | Reproducible clearance report, version-bound |
| 46 | Authentication, organizations, and roles | 02 | Local PostgreSQL auth by default with optional Firebase/Identity Platform adapter, one provider per deployment. Opaque revocable app sessions, five-state invitations, memberships, fixed RBAC (Owner, Admin, Editor, Reviewer, Viewer), and capability-guarded actions. |
| 47 | Secure source and file handling | 02, 08 | Input validation, MIME/magic-byte checks, safe XML, isolated PDF, SSRF protection, prompt-injection defense |

---

## Plan Ownership Summary

| Plan | Features | Scope |
|---|---|---|
| 01 | 39 (partial) | Repo, toolchain, contracts, deploy skeleton |
| 02 | 1–7, 40, 42 (partial), 46, 47 (partial) | Identity, collaboration, storage, ingestion, all 4 parsers |
| 03 | 10–27, 30, 42 (partial) | Detection (all 10 categories), Parallel research, evidence, evaluation spine |
| 04 | 33, 37, 41, 43 | Annotated workspace, dashboard, search/filter/sort/group |
| 05 | 29, 31, 35, 36, 38 (partial) | Collaboration, governed decisions, assignments, comments, receipts |
| 06 | 8, 9, 32, 34, 44, 45 | Rewrites, revisions, selective re-scan, clearance report |
| 07 | 28, 38 (partial) | Monitoring, judge evaluation, bounded learning, Owner-governed protected config, Admin operational config |
| 08 | 39 (partial), 47 (partial) | Production hardening, security, demo, video, submission |

## Golden Path (must work for submission)

1. Create an organization and project.
2. Import an original screenplay (paste, Fountain, PDF, or FDX).
3. Agent detects clearance items across 10 categories.
4. Each item runs a real mandatory Parallel Search; selected URLs may receive bounded Extract enrichment; evidence cards show source origin, conflicts, confidence, and provenance.
5. Assign and review flagged items with governed human decisions.
6. Accept a rewrite suggestion; create a new script version.
7. Selective re-scan updates only affected items.
8. Monitor sources for material changes.
9. Generate a version-bound clearance report snapshot, then release the frozen snapshot separately.
10. All on a hosted URL with an annotated screenplay workspace and fixed roles.

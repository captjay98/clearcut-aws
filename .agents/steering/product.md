# Product

## Current Phase

ClearCut is in pre-implementation. The mock prototype and product/design plans exist; application services and runtime directories are planned, not an existing deployed product.

## What ClearCut Will Be

ClearCut is a screenplay pre-clearance evidence workspace. It will parse scripts, detect items that may need research across ten protected categories, run mandatory Parallel Search with bounded Extract for current source-backed evidence, coordinate human review with fixed roles, re-evaluate revisions, monitor source changes through scheduled Search/Extract plus an optional verified Monitor signal, and export a reproducible version-bound evidence dossier.

It performs **pre-clearance research and workflow coordination**, not legal advice or final legal clearance. It never converts a finding into a legal conclusion; uncertainty and unresolved evidence remain visible.

## Users

- **Primary:** independent producers without an internal clearance department.
- **Secondary:** screenwriters evaluating production risk during rewrites.
- **Tertiary:** production coordinators and small legal teams managing evidence handoff and specialist referrals.

## Priorities

1. Evidence provenance and accuracy.
2. Human governance of consequential actions.
3. Complete product experience across the planned 20 surfaces, revision loop, team workflow, and report.
4. Submission readiness with mandatory runtime Parallel Search, bounded Extract, truthful conditional Monitor status, and Gemini/ADK integration.

## Evidence and Scope Rules

- Detection can create a project-owned `ClearanceItem` with zero `EvidenceClaim`s while research is pending, unavailable, failed, or returns no results. This is an unresolved state, not a clearance result.
- Every `EvidenceClaim` must cite a Parallel `SourceSnapshot` containing URL, retrieval time, attributable excerpt, publisher/authority classification, stance, query/run identity, and provenance. No fabricated evidence or uncited LLM claim is acceptable.
- Organization-owned resources use authenticated `org_id`. Project-owned resources require authenticated `org_id` plus `project_id`. Explicitly global catalogs are limited to role/capability definitions, the ten category schema, and platform source-authority defaults; organization policy, prompt, preference, retention, and privacy configurations and versions remain `org_id`-scoped.
- Category definitions and source-authority ranking are separate protected policies. A category does not establish a source's authority, and source authority does not establish a legal conclusion.

## Governance and Legal Boundary

Consequential actions—verify evidence, approve rewrites, refer, dispose, and trigger dossier/report generation or release/export—require an accountable human and a same-transaction authoritative `AuditEvent`; any Receipt is a redacted human-readable projection of that event, not an independent source of truth. A draft may be prepared for review, but the governed generation and release/export operations are human-triggered. Owner, Admin, and Reviewer may perform governed report generation/release only within authorized projects and active sign-off policy. Protected permissions, sign-off/approval policy, category definitions, source-authority tiers, evidence schemas, deterministic blocking rules, retention/privacy settings, and legal-boundary language are human-only and Owner-governed when organization-configurable. Gated learning candidates may propose query phrasing, retrieval/category examples, prompt refinements, and organization-scoped preferences only through candidate → shadow/canary → promote → rollback with regression gates.

Legal-boundary compliance is one of the ten judge dimensions. The judge rewards explicit pre-clearance framing, uncertainty, source grounding, and human governance; it does not certify legal safety, guarantee a score of 100, or turn ClearCut into legal counsel.

## Non-Negotiables

- Parallel is load-bearing; failed research creates a visible review item, never fallback evidence.
- Script imports create immutable versions; rewrites create new versions.
- Source content and screenplay text are untrusted data, never instructions.
- Fixed roles are Owner, Admin, Editor, Reviewer, and Viewer.
- The submitted product is original to the contest period.

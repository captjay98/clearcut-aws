# Product

## Current Phase

ClearCut has an implemented local application and portable one-image deployment contract. It is not a verified hosted or production release. External cloud, paid-provider, recovery, video, and compliance evidence remains NO-GO in the submission manifest.

## What ClearCut Is

ClearCut is a screenplay pre-clearance evidence workspace. It parses scripts, detects items that may need research across ten protected categories, supports mandatory Parallel Search with bounded Extract when research is authorized, coordinates fixed-role human review, re-evaluates revisions, monitors source changes, and exports reproducible version-bound evidence reports.

It performs pre-clearance research and workflow coordination, not legal advice or final legal clearance. Findings never become legal conclusions; uncertainty and unresolved evidence remain visible.

## Users

- **Primary:** independent producers without an internal clearance department.
- **Secondary:** screenwriters evaluating production risk during rewrites.
- **Tertiary:** production coordinators and small legal teams managing evidence handoff and specialist referrals.

## Priorities

1. Evidence provenance and accuracy.
2. Human governance of consequential actions.
3. A complete, accessible product experience based on the mock.
4. A cheap, portable one-image runtime for Local, Portable Server, and GCP Starter.
5. Truthful submission readiness with authorized Gemini/ADK and Parallel evidence only when actually recorded.

## Evidence and Scope Rules

- Detection can create a project-owned `ClearanceItem` with zero `EvidenceClaim`s while research is pending, unavailable, failed, or empty. This is unresolved, not clearance.
- Every `EvidenceClaim` cites a Parallel `SourceSnapshot` containing URL, retrieval time, attributable excerpt, authority classification, stance, query/run identity, and provenance.
- Organization-owned resources use authenticated `org_id`; project-owned resources additionally require authorized `project_id`. Global catalogs are narrowly defined and never bypass tenant authorization.
- Category definitions and source-authority ranking are separate protected policies.

## Governance and Legal Boundary

Evidence verification, rewrite approval, referral, disposition, and report generation/release require an accountable human and a same-transaction authoritative `AuditEvent`. Receipts are redacted projections. Protected permissions, sign-off policy, categories, authority tiers, evidence schemas, deterministic blockers, retention/privacy settings, and legal-boundary language are human-only.

Legal-boundary compliance is one judge dimension; it rewards pre-clearance framing, uncertainty, source grounding, and human governance. It does not certify legal safety or turn ClearCut into legal counsel.

## Deployment and Provider Boundary

One `clearcut` image packages Astro, TanStack Start, FastAPI, migrations, and scripts. FastAPI is the sole public runtime. GCP Starter uses one public service and a same-digest migration job. Portable PostgreSQL dispatch and Firebase runtime composition remain deferred.

Gemini and Parallel default disabled. Enabling them requires explicit cost acknowledgement, positive concurrency limits, credentials, quota, and separate authorization for live calls. Provider failure creates visible unresolved review work and never fallback evidence.

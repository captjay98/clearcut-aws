# ClearCut Master Implementation Plan

**Status:** planning baseline; implementation not authorized by this document  
**Date:** 2026-08-30  
**Target:** Parallel track, Agentic Cinema submission on September 9, 2026 at 2:00 PM PT

## Goal

Build an open-source hosted screenplay pre-clearance evidence workspace that turns an immutable screenplay version into current, attributable Parallel evidence; preserves uncertainty; coordinates accountable human review; re-checks only revision-affected work; monitors source changes; and releases a reproducible version-bound clearance report without offering legal conclusions.

Before freezing an affected seam, check `docs/DECISION_GAPS.md`. Open conflicts are deliberate stop points, not permission to select a convenient interpretation.

## Delivery strategy

Implement contract-first vertical slices. Each slice starts with failing boundary/behavior tests, adds the smallest production path, produces an evidence pack, and stops at a review checkpoint. Do not create all database tables, API routes, or UI shells before one evidence-bearing vertical slice works end to end.

```text
01 foundation/contracts
  -> 02 identity/tenancy
  -> 03 ingestion/versioning
  -> 04 detection/evaluation
  -> 05 Parallel evidence
  -> 06 design system/shell
  -> 07 evidence workspace/collaboration
  -> 08 revisions/selective re-scan
  -> 09 monitoring/notifications
  -> 10 trust/governance
  -> 11 report/export
  -> 12 infrastructure/submission
```

Plans 04 and 06 may prepare in parallel only after Plan 01 contracts pass. Plan 12 infrastructure foundations may prepare after Plan 01, but no production-release claim is allowed until Plans 02–11 pass their exits.

The numbered files below are roadmap summaries, not direct execution instructions. Implementation agents execute the granular 01a–12b files in `docs/plans/implementation/` and follow that directory's dependency graph. The dated critical path is `docs/DELIVERY_PLAN.md`.

## Active plans

| Slice | Canonical parent | Outcome | Checkpoint |
|---|---:|---|---|
| `01-foundation-contracts.md` | 01 | Reproducible monorepo, OpenAPI, schemas, generated clients, truthful CI | R1 |
| `02-identity-tenancy.md` | 02 | Opaque sessions, organizations, invitations, fixed roles, project scope | R2 |
| `03-ingestion-versioning.md` | 02 | Four safe import paths and immutable normalized v1 | R2 |
| `04-detection-evaluation.md` | 03 | Ten-category detection, deterministic gates, independent judge records | R3 |
| `05-parallel-evidence.md` | 03 | Mandatory Search, bounded Extract, cited claims, conflicts, typed failures, tool traces | R3 |
| `06-design-system-shell.md` | 04 | Astro/TanStack shells and mock-derived design system | R4 |
| `07-evidence-workspace-collaboration.md` | 04/05 | Project/workspace/items/item, decisions, assignments, comments, team notifications | R5 |
| `08-revisions-selective-rescan.md` | 06 | Maker/checker rewrite, immutable v2+, stable diff, affected-only re-scan | R6 |
| `09-monitoring-notifications.md` | 07/05 | Scheduled Search/Extract watch, conditional Monitor signals, governed review, inbox | R7 |
| `10-trust-governance.md` | 07 | Trust/Records, protected configuration, bounded learning, deletion lifecycle | R7 |
| `11-report-export.md` | 06 | Frozen generation, separate governed release, reproducible PDF/report | R8 |
| `12-infrastructure-submission.md` | 08 | GCP deployment, operational proof, original demo, public submission pack | R9 |

## Review checkpoints

- **R1 Foundation:** toolchains pinned; boundaries and contract drift tests pass; no product behavior claimed.
- **R2 Secure intake:** an authorized member imports all four formats into the correct project; cross-tenant and malformed-input tests pass.
- **R3 Evidence vertical slice:** one script produces detection candidates, a mandatory live Parallel Search call, bounded Extract outcomes, cited `EvidenceClaim`s, visible typed failures, and evaluation records.
- **R4 UI foundation:** both apps compile; shared primitives match the mock in both themes; accessibility adapter proof is accepted.
- **R5 Review workspace:** a multi-user evidence decision completes with project scope and same-transaction audit.
- **R6 Revision loop:** a separate reviewer approves a rewrite, v2 is created, and only computed affected items are re-checked.
- **R7 Monitoring/governance:** scheduled Search/Extract rechecks open review work; conditional Monitor signals, when enabled, are re-verified before review; protected rules cannot auto-promote; Records remains redacted and scoped.
- **R8 Delivery:** snapshot generation and release are distinct; released artifacts are immutable and reproducible.
- **R9 Submission:** exact deployed SHA, runtime Gemini/ADK and Parallel traces, hosted URL, public repo, license, video, and Devpost fields are verified.

## Hard invariants

1. A `ClearanceItem` may exist with zero claims. Zero evidence is unresolved, never clearance.
2. Every `EvidenceClaim` cites an immutable Parallel `SourceSnapshot` with URL, retrieval time, attributable excerpt, publisher/authority, stance, query/run identity, and provenance.
3. Project-owned reads and writes require authenticated `org_id`, `project_id`, and current project authorization.
4. Consequential decisions and report generation/release require an accountable human and commit with the authoritative immutable `AuditEvent` in one transaction.
5. Provider boundaries return typed success or typed error results; ambiguous outcomes enter reconciliation, not blind retry.
6. Modules use application services and typed events; no module reads another module's tables.
7. Permissions, sign-off rules, category definitions, authority tiers, required evidence schema, deterministic blockers, retention/privacy rules, and legal-boundary language are human-only.
8. The mock is the visual/interaction source, but production tests—not prototype checks—prove production behavior.
9. No UI, agent, fixture, or fallback invents evidence, provider success, legal certainty, traction, or deployment proof.
10. The submitted profile implements and loads only Gemini through Google ADK for AI and the approved Parallel capabilities in `docs/PARALLEL_INTEGRATION.md`; Search remains mandatory, and no other provider or excluded Parallel agent API is loadable.
11. Adapters may replace infrastructure behind typed ports but cannot change protected core governance, provenance, tenant, audit, retention, or legal-boundary rules.

## Standard plan execution loop

For every task:

1. Confirm authoritative inputs and exact files.
2. Write a failing behavioral, contract, boundary, or security test.
3. Run the narrow test and capture the expected failure.
4. Implement the minimum behavior.
5. Run narrow tests, then the plan gate.
6. Inspect tenant scope, governance, provenance, and error paths.
7. Commit one coherent change.
8. Append an evidence pack with command, output, SHA, scope, and explicit non-claims.

## Lessons adapted from the reference repositories

From HackSteward:

- keep active and archived plans separate;
- maintain a feature-coverage matrix with objective evidence;
- use review checkpoints and evidence packs that state what they do **not** prove;
- prove one vertical slice before route-complete expansion.

From Farmhand:

- freeze high-risk contracts early;
- treat transactional governance, tenant scope, typed provider outcomes, durable claims, and reconciliation as day-one architecture;
- bind readiness claims to exact revisions and fresh behavioral evidence;
- keep demo/marketing claims distinct from runtime and customer proof.

ClearCut does not copy either product's code, domain objects, visual system, credentials, infrastructure identifiers, or deployment state.

## Stop conditions

Stop and escalate if:

- official rules conflict with the submission strategy;
- a contract would weaken evidence provenance or tenant scope;
- a governed action cannot commit atomically with its audit event;
- the only available provider behavior is an untyped fallback;
- a plan relies on a path or command that does not yet exist;
- mock fidelity requires redesign rather than faithful implementation;
- a hard gate fails.

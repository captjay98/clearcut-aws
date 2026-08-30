# Report Generation, Release, and Export Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Generate an immutable version-bound clearance report snapshot, obtain a separate accountable human release attestation, and provide reproducible HTML/PDF export.

**Architecture:** Generation reads one consistent database snapshot and freezes all bindings/content before rendering. Release references the frozen snapshot; exports read only released snapshot data. Later drift creates a new snapshot/release cycle.

**Tech Stack:** FastAPI durable jobs, PostgreSQL, GCS, deterministic HTML/CSS print renderer and PDF tooling, TanStack report UI.

---

**Depends on:** Plans 08–10  
**Checkpoint:** R8

Resolve DG-07 and DG-08 before naming the OpenAPI resources or release command.

### Task 1: Define report snapshot/binding contract

Include project/script version/hash, flags, claims/snapshots, conflicts, decisions/audit references, monitoring status, trust/evaluation, policy/prompt/rubric/model/judge/generator versions, open items, timestamps, content hash. Test missing binding blocks generation acceptance.

### Task 2: Implement durable generation

The human-trigger transaction commits authorization, generation command, `AuditEvent`, job, and outbox. A worker reads one consistent snapshot, renders an immutable structured payload, uploads a temporary/versioned object with hash and generation preconditions, then commits `ReportSnapshot`, object pointer, and terminal job result in a completion transaction. Publication reads only the committed snapshot. Reconciliation deletes or adopts orphan objects and repairs stranded jobs. Test retry/idempotency, crash before/after upload, changed live state during generation, and access/policy checks.

### Task 3: Implement separate governed release

Release UI/dialog must say “Release this frozen snapshot?” and “Release report,” never “Generate & release.” Owner/Admin/Reviewer with project authorization/sign-off may release after attesting accuracy and non-legal boundary. Commit `ReportRelease` + `AuditEvent` together.

```python
async with uow:
    release = snapshot.release(actor=actor, attestation=attestation)
    await uow.add_all(release, AuditEvent.for_report_release(release))
```

### Task 4: Render exhibits and exports deterministically

Exhibits: versions; flags; sources/authority; decisions/audit projections; monitoring/trust; open items; binding. Preserve source disagreement and unresolved appendix. Hide chrome/controls, prevent exhibit/disclaimer splits, retain selectable text and provenance.

### Task 5: Implement stale/superseded lifecycle

Compare live state with release bindings and name drift without changing the artifact. Generating a new snapshot leaves the prior released artifact available until a later release supersedes it. Deletion marks artifacts unavailable honestly.

### Verification

Golden HTML/PDF content, page/print tests, deterministic hash tests, exact-binding property tests, role/scope/concurrency/idempotency, browser tabs/print at target widths/themes, download authorization/expiry, and re-render from retained snapshot.

```bash
uv run pytest services/api/tests/reports services/api/tests/exports -q
pnpm --filter @clearcut/web test:e2e -- report-print
```

Expected: commands exit 0; canonical structured snapshot hashes match. HTML/PDF byte hashes match only under the pinned deterministic renderer/font/metadata profile; otherwise semantic-manifest and rendered-content assertions are authoritative and byte variance is explicitly explained.

### Exit criteria

- Generation and release are separate commands, UI states, records, and audits.
- Released artifact content cannot drift with live state.
- All required bindings/open items/conflicts/legal boundary are present.
- PDF/print has no app chrome/orphans/split exhibits and keeps selectable evidence text.
- A retained snapshot reproduces the artifact or reports why reproducibility was lost.

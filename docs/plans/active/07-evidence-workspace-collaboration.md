# Evidence Workspace and Collaboration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver the project overview, annotated screenplay, flag worklist/detail, assignments, comments, referrals, evidence decisions, and accountable multi-user review.

**Architecture:** Server read models derive counts/status and enforce scope; TanStack routes consume generated clients. Governed decisions run through one application service and transaction regardless of drawer/detail entry point.

**Tech Stack:** FastAPI/PostgreSQL, generated TypeScript client, TanStack Start, ClearCut design system, Playwright.

---

**Depends on:** Plans 02, 05, 06  
**Checkpoint:** R5

Resolve DG-01, DG-02, and DG-03 in `docs/DECISION_GAPS.md` before freezing comment, assignment, or referral contracts.

### Task 1: Implement orthogonal item/read-model contracts

Define research, evidence assessment, workflow, remediation, and disposition dimensions plus derived display status. Property-test valid/invalid transitions and ensure list/detail/dashboard counts read one projection.

### Task 2: Build project overview and annotated screenplay

Create scoped endpoints/routes/components for stats, progress, next action, script pages, scene rail, version selector, margin flags, and adaptive evidence drawer. Test stable span anchors, project switching, superseded version read-only state, and mobile Script/Scenes/Evidence tabs.

### Task 3: Build list/board/filter/group/bulk workflow

Implement URL-addressable filter/search/sort/group contracts, list/board parity, selection, bulk assign/due/referral with atomic per-item audit events. Do not bulk verify/dispose/rewrite.

### Task 4: Build item detail/evidence/discussion

Create stable direct links, access-safe not-found, prev/next filtered context, full source/provenance table, version binding, print isolation, one-level replies, edit history, mentions, and immutable action entries.

### Task 5: Implement governed decision/referral/assignment services

```python
async with uow:
    decision = item.record_evidence_decision(command, policy)
    audit = AuditEvent.for_decision(decision)
    await uow.commit(decision, audit)
```

Use rationale, expected version, idempotency, current actor/capability/project policy. Drawer and item page call the same endpoint. Test races, duplicates, stale evidence, maker/checker prerequisites, deactivation, and rollback on audit failure.

### Task 6: Complete Team and notification-producing events

Implement member/invitation/project-grant management UI against Plan 02 and emit versioned assignment/comment/mention/referral/decision/rewrite events for Plan 09 consumers.

```bash
uv run pytest services/api/tests/items services/api/tests/decisions services/api/tests/collaboration -q
pnpm --filter @clearcut/web test:e2e -- evidence-workspace
pnpm contract:check
```

Expected: all commands exit 0; E2E runs at least Reviewer, Editor, and Viewer paths plus an unauthorized direct link.

### Exit criteria

- Multi-user review completes without client-side authorization bypass.
- Every claim shown has provenance; zero evidence is unresolved.
- List, board, dashboard, drawer, detail, and report-input projections agree.
- Governed actions and audit commit atomically.
- All four surfaces pass state/access/direct-link/print/responsive/accessibility tests.
- R5 states that revision/monitoring/report delivery remains pending.

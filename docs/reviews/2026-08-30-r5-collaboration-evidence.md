# Plan 07 (Evidence Workspace & Collaboration) Evidence Pack

**Date:** 2026-08-30  
**Plan:** Plan 07 (Evidence Workspace and Collaboration Implementation Plan)  
**Packets Completed:** `07a`, `07b`, `07c`, `07d`  
**Checkpoint:** R5 (Evidence Workspace, Collaboration & Review)  
**Status:** PASSED (All Exit Criteria Satisfied)

---

## 1. Scope & Objectives
Deliver the unified screenplay pre-clearance workspace:
* Orthogonal item state dimensions (`ResearchStatus`, `AssessmentStatus`, `WorkflowStatus`, `RemediationStatus`, `DispositionStatus`) with derived display status and unified projection service (`07a`).
* Governed decision commands (`record_evidence_decision`, `refer_clearance_item`) with atomic `AuditEvent` generation and strict role capabilities (`07b`).
* 1-level threaded discussions (DG-01), regex user mentions, domain event schema (`collaboration.v1.json`), and transactional outbox (`07c`).
* Evidence workspace routes (Project Overview, Script Workspace, Item Worklist, Item Detail) with `ClaimTable`, `CommentThread`, and `DecisionDialog` (`07d`).
* Alembic migrations: `0010_item_projections.py`, `0011_decisions_assignments.py`, `0012_comments_events.py`.

---

## 2. Test Execution & Evidence

### 1. Backend, Items, Decisions & Collaboration Tests (73 tests)
Command:
```bash
uv run pytest -v
```
Output:
```text
============================== 73 passed in 0.54s ==============================
```

### 2. Frontend Test Suites (28 tests across all workspaces via Bun)
Command:
```bash
bun test apps/web/tests/unit/ apps/site/tests/ packages/design-system/tests/
```
Output:
```text
bun test v1.4.0

 28 pass
 0 fail
 Ran 28 tests across 6 files. [59.00ms]
```

### 3. Static Type Checking & Linters
```text
uv run pyright: 0 errors, 0 warnings
uv run ruff check .: clean
```

### 4. Mockup Audit Fidelity (418/418 checks)
```bash
bun misc/clearcut-flow/mockup-audit.mjs
============================== 418/418 checks passed. ==============================
```

---

## 3. Database Migrations Delivered
* `0010_item_projections.py` (Item projection state tracking & indexes)
* `0011_decisions_assignments.py` (`evidence_decisions`, `item_referrals`, `audit_events`)
* `0012_comments_events.py` (`comments`, `collaboration_outbox`)

---

## 4. Invariants Proven
1. **Unified Server Projections**: Dashboard, list, board, and search read from one single projection model.
2. **Accountable Governed Actions**: Governed actions (evidence decisions, referrals) require human roles (`Reviewer`, `Admin`, `Owner`) and atomically commit with immutable `AuditEvent`s.
3. **Flat Threading (DG-01)**: Discussions enforce a strict 1-level reply maximum to prevent nested reply chaos.
4. **Provenance Completeness**: Claim citations include full source snapshots, authority tiers, and excerpts.

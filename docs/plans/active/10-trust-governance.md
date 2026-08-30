# Trust, Records, and Governance Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Provide scoped, redacted, reproducible Trust/Records views; version protected organization configuration; and permit only bounded low-risk learning through regression, shadow, canary, promotion, and rollback.

**Architecture:** Records exclusively owns the cross-module Records API/UI and composes authorized projection ports rather than querying foreign tables directly. Source modules own records and projection ports, not Records routes. AuditEvent remains authoritative; Receipt is rebuildable display. Protected configuration and learning use separate capabilities and immutable version bindings.

**Tech Stack:** FastAPI/PostgreSQL, typed projection APIs, ADK judge adapters, TanStack Trust/Records/Settings surfaces.

---

**Depends on:** Plans 04, 05, 07, 09  
**Checkpoint:** R7

### Task 1: Implement immutable audit/receipt projection consistency

Test governed state cannot commit without audit and Receipt can be rebuilt/redacted from authoritative events. Separate run/tool/provider/security records from governed audit even when chronologically combined.

### Task 2: Build scoped/redacted Records projections

Implement activity, runs/tools, evaluations, policies, operations with immutable IDs, cursor pagination, filters, correlation links, unknown/unauthorized parity, and redaction reasons. Add leak tests for tokens, credentials, signed URLs, scripts/source bodies, raw payloads, hidden reasoning.

### Task 3: Build Trust evaluation projections

Show exact run/rubric/prompt/policy/model/judge bindings, ten dimensions, aggregation method, blockers/warnings, stale/incomplete/invalid states, and linked Records detail. A blocker visually and programmatically outranks score.

### Task 4: Implement protected configuration lifecycle

```text
draft -> validated -> active -> superseded
```

Only Owner activates after recent reauth, typed confirmation, rationale, optimistic version, and regression/compatibility checks. Admin can inspect, not mutate. Global catalogs remain read-only.

### Task 5: Implement bounded learning lifecycle

Allowlist query phrasing, retrieval/category examples, prompt refinements, and organization preferences. Test protected-field diff rejection, corpus/gate/budget/shadow/canary thresholds, idempotent promotion, automatic/manual rollback, organization isolation, and private-data consent boundary.

```python
PROTECTED_SCOPES = {"permissions", "sign_off", "categories", "authority_tiers", "evidence_schema", "blockers", "retention", "legal_boundary"}
assert candidate.changed_scopes.isdisjoint(PROTECTED_SCOPES)
```

### Task 6: Implement no-age retention and deletion lifecycle

Build impact preview, Owner schedule/restore, 30-day read-only grace, signed-link/job revocation, idempotent purge, tombstone, and explicit report reproducibility loss. No selective claim/audit deletion.

```bash
uv run pytest services/api/tests/records services/api/tests/learning services/api/tests/deletion -q
pnpm --filter @clearcut/web test:e2e -- trust records governance
```

Expected: commands exit 0; protected-mutation, leakage, and gate-bypass tests fail closed.

### Exit criteria

- Records counts/details/links are correctly scoped and redacted.
- Audit/Receipt consistency and exact bindings pass.
- Protected configuration cannot be altered by Admin/model/learning.
- Low-risk candidate traverses every gate and rolls back safely.
- Deletion/restore/purge behavior is proven without rewriting history.
- Trust language never implies legal safety or clearance.

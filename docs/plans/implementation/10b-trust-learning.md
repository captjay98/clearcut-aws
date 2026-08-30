# Trust, Protected Configuration, and Bounded Learning Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Expose evaluation bindings and permit only gated low-risk organization-scoped learning.  
**Architecture:** Protected configuration and learning candidates have distinct capabilities and immutable versions.  
**Tech Stack:** FastAPI, PostgreSQL, Gemini judge, TanStack Start.

---

**Files:** Create `evaluation/domain/configuration.py`, `evaluation/domain/learning.py`, `evaluation/application/configuration_commands.py`, `application/learning_pipeline.py`, `services/api/alembic/versions/0018_trust_learning.py`, `apps/web/src/routes/o.$orgSlug.trust.tsx`; test `services/api/tests/learning/test_protected_diff.py`, `test_canary_rollback.py`, `test_org_isolation.py`, `apps/web/tests/e2e/trust.spec.ts`.

1. Add failing ten-dimension binding, blocker precedence, protected-scope rejection, recent-reauth, regression/shadow/canary/budget/promotion/rollback tests.
2. Add migration 0018; implement Owner-only protected activation and allowlisted learning with automatic rollback.
3. Run trust/learning/migration/contract/UI-state tests; expect no automated protected change or fabricated complete score.
4. Record evidence; commit `feat: add governed trust and learning lifecycle` after authorization.

**Exit:** Protected rules remain human-only and a candidate can promote and roll back through every gate.

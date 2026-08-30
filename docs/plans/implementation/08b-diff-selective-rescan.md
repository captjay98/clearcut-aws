# Version Diff, Lineage, and Selective Re-scan Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Materialize immutable v2+, compute structural lineage, and research only affected items.  
**Architecture:** Approval transaction creates version/diff/affected projection/job/audit; workers checkpoint per item.  
**Tech Stack:** Python, Hypothesis, PostgreSQL, durable jobs.

---

**Files:** Create `scripts/domain/diff.py`, `scripts/application/materialize_revision.py`, `research/application/selective_rescan.py`, `services/api/alembic/versions/0014_version_lineage_rescan.py`; test `services/api/tests/versions/test_diff_properties.py`, `test_atomic_materialization.py`, `services/api/tests/rescan/test_selective_calls.py`.

1. Add failing deterministic identity/lineage/classification properties and partial retry/cancel/stale worker/no-duplicate-call tests.
2. Add migration 0014; implement atomic materialization and checkpointed rescan preserving unaffected claim lineage.
3. Run property/rescan/migration/evidence-evaluation tests; expect zero new calls for unaffected items.
4. Record evidence; commit `feat: add selective version rescan` after authorization.

**Exit:** Affected scope is computed and unchanged items produce zero new research calls.

# Rewrite Proposal and Maker-Checker Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement draft/propose/approve/reject/withdraw rewrite lifecycle with separate actors.  
**Architecture:** Proposals never mutate versions; approval is governed and atomic with audit/outbox.  
**Tech Stack:** FastAPI, PostgreSQL, OpenAPI.

---

**Files:** Create `decisions/domain/rewrites.py`, `decisions/application/rewrite_commands.py`, `services/api/alembic/versions/0013_rewrite_proposals.py`; test `services/api/tests/rewrites/test_lifecycle.py`, `test_maker_checker.py`.

1. Add failing lifecycle, same-actor, stale-version, scope, rationale, idempotency, and audit rollback tests.
2. Add migration 0013 and semantic propose/approve/reject/withdraw operations; preserve original text/history.
3. Run rewrite/migration/contract tests; expect proposer approval rejection and immutable source version.
4. Record evidence; commit `feat: add maker checker rewrites` after authorization.

**Exit:** No actor approves their own proposal and no proposal mutates its source version.

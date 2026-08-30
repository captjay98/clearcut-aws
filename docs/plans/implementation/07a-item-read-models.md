# Item State and Read Models Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement orthogonal item state plus consistent dashboard/list/board/search projections.  
**Architecture:** One scoped server projection derives every display count/status; URLs carry typed filters.  
**Tech Stack:** FastAPI, PostgreSQL, Hypothesis, OpenAPI.

---

**Files:** Create `detection/domain/item_state.py`, `detection/application/item_projection.py`, `detection/delivery/http.py`, `services/api/alembic/versions/0010_item_projections.py`; test `services/api/tests/items/test_state_machine.py`, `test_projection_consistency.py`, `test_filters.py`.

1. Add failing property/contract tests for five independent dimensions, derived labels, invalid transitions, cursor/filter/group/search, and projection agreement.
2. Add migration 0010/index query-plan tests; implement scoped read API and generated operations.
3. Run item/property/migration/contract/API-only tests; expect list/board/dashboard equality and safe unauthorized results.
4. Record evidence; commit `feat: add consistent clearance item projections` after authorization.

**Exit:** Every consumer reads one scoped projection and all query contracts are stable.

# Deterministic Gates and Staged Evaluation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Admit safe detection output and persist honest stage-eligible judge evaluations.  
**Architecture:** Deterministic blockers precede an independent judge; unavailable dimensions remain explicit.  
**Tech Stack:** Python, Hypothesis, Gemini judge adapter, PostgreSQL.

---

**Files:** Create `evaluation/domain/gates.py`, `domain/rubric.py`, `application/evaluate.py`, `ports/judge.py`, `adapters/gemini_judge.py`, `services/api/alembic/versions/0007_evaluation.py`, `demo/fixtures/evaluation/`; test `services/api/tests/evaluation/test_gates.py`, `test_stage_dimensions.py`, `test_aggregation.py`.

1. Add failing tests for invalid spans/categories/scope/legal certainty/injection and all ten dimension states (`scored`, `incomplete`, `not_applicable`, `failed`).
2. Add migration 0007 with immutable rubric/prompt/policy/model bindings and nullable scores only when a declared state explains them.
3. Implement gate registry, staged aggregation, and separate Gemini judge identity; a blocker always outranks score.
4. Run `uv run pytest services/api/tests/evaluation -q` and corpus regression; expect ten declared dimensions and no fabricated later-stage scores.
5. Record evidence; commit `feat: add deterministic gates and staged evaluation` after authorization.

**Exit:** Detection-stage evaluation is complete for its stage, not falsely complete for the whole product.


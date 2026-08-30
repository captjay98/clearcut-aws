# Gemini ADK Detection Runtime Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Detect typed candidates across the ten protected categories with Gemini/ADK and durable execution.  
**Architecture:** `ModelRuntimePort` isolates SDK details; the contest registry accepts only `GeminiAdkRuntime`.  
**Tech Stack:** Google ADK, Gemini, Pydantic, Cloud Tasks port, PostgreSQL.

---

**Files:** Create `detection/domain/candidates.py`, `ports/model_runtime.py`, `adapters/gemini_adk.py`, `application/detect.py`, `operations/domain/jobs.py`, `operations/application/worker.py`, `services/api/alembic/versions/0006_detection_jobs.py`; test `services/api/tests/detection/test_categories.py`, `test_detection_jobs.py`, `tests/conformance/test_model_runtime.py`.

1. Add failing positive/negative/ambiguous/injection fixtures for ten categories and job lifecycle/idempotency/lease/reconcile tests.
2. Add migration 0006 and contest-profile manifest validation; run tests expecting missing runtime/models.
3. Implement typed ADK invocation, structured output, exact prompt/model/input binding, and visible shared provider failures.
4. Run detection/conformance/migration/contract tests and one redacted development call trace; expect exit 0.
5. Record evidence; commit `feat: add gemini adk detection runtime` after authorization.

**Exit:** Production cannot register a non-Google or fake model runtime; no detection output is a human decision.


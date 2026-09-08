# Revision Matching Work Preflight Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reject over-budget fuzzy revision matching before expensive per-pair character-multiset filtering while preserving exact/contextual matching and existing under-budget behavior.

**Architecture:** Keep the existing same-type pair-count preflight first. Reuse the grouped unmatched indexes to compute a conservative raw same-type Cartesian character-work bound as `sum(sum_before_lengths[type] * sum_after_lengths[type])`; when it exceeds the character budget, skip the entire fuzzy phase before candidate generation, while retaining the later eligible-candidate check as defense in depth.

**Tech Stack:** Python 3.12, pytest, Ruff, Pyright, uv.

---

### Task 1: Add deterministic RED instrumentation

**Files:**
- Modify: `services/api/tests/versions/test_diff_properties.py`

**Step 1: Write the failing test**

Add a 100×100 same-type unmatched fixture with long, high-distinct-character texts whose raw same-type Cartesian work exceeds `MAX_SIMILARITY_CHARACTER_WORK` while its pair count remains at the allowed limit. Monkeypatch `_can_affect_similarity_choice` with a counted wrapper and assert it is never called. Also assert two repeated diff calculations are identical and produce only deterministic ADDED then REMOVED rows.

**Step 2: Run the focused test to verify RED**

Run: `uv run pytest services/api/tests/versions/test_diff_properties.py::test_raw_character_work_is_rejected_before_candidate_filtering -q`

Expected: FAIL because `_can_affect_similarity_choice` is called before the current late character-work rejection.

### Task 2: Add the early conservative work preflight

**Files:**
- Modify: `services/api/src/clearcut/scripts/domain/diff.py`

**Step 1: Implement the minimal preflight**

After the existing pair-count check, compute per-type sums of normalized text lengths from `before_by_type` and `after_by_type`, then sum their products. Return `[]` when this raw character-work upper bound exceeds `MAX_SIMILARITY_CHARACTER_WORK`. Leave candidate generation and the later eligible-candidate work check after this guard.

**Step 2: Run the focused test to verify GREEN**

Run: `uv run pytest services/api/tests/versions/test_diff_properties.py::test_raw_character_work_is_rejected_before_candidate_filtering -q`

Expected: PASS.

### Task 3: Validate preserved behavior and quality

**Files:**
- Verify: `services/api/src/clearcut/scripts/domain/diff.py`
- Verify: `services/api/tests/versions/test_diff_properties.py`
- Verify: `services/api/tests/rescan/test_selective_calls.py`

**Step 1: Run affected tests**

Run: `uv run pytest services/api/tests/versions services/api/tests/rescan/test_selective_calls.py -q`

Expected: PASS, including ordinary modified matching, 99×99 under-budget matching, 40-line distant reorder, exact/contextual matching, and deterministic over-budget fallback.

**Step 2: Run scoped static checks**

Run: `uv run ruff check services/api/src/clearcut/scripts/domain/diff.py services/api/tests/versions/test_diff_properties.py`

Run: `uv run pyright services/api/src/clearcut/scripts/domain/diff.py services/api/tests/versions/test_diff_properties.py`

Expected: both PASS.

**Step 3: Review the diff**

Run: `git diff --check` and inspect the scoped diff. Confirm no protected, provider, network, cloud, or pre-existing untracked paths changed.

### Task 4: Commit the verified follow-up

**Files:**
- Stage only the implementation, regression, and this plan.

**Step 1: Commit**

Run: `git add docs/plans/2026-09-08-revision-matching-work-preflight.md services/api/src/clearcut/scripts/domain/diff.py services/api/tests/versions/test_diff_properties.py && git commit -m "fix(scripts): preflight revision matching work"`

**Step 2: Capture evidence**

Report the RED failure, GREEN and full validation outputs, diff review, clean scoped status (noting pre-existing `semantic-review/`), and the new commit SHA.

# Detection and Evaluation Spine Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Detect candidate clearance items across all ten protected categories and persist deterministic gates plus the detection-eligible portion of an independently judged evaluation.

**Architecture:** ADK/Gemini produces typed candidate proposals from normalized script elements. Deterministic validators admit/reject output before an independently configured judge scores it. Neither model makes legal conclusions or authorization decisions.

**Tech Stack:** Google ADK/approved Gemini SDK, Pydantic structured output, FastAPI durable jobs, pytest/property tests, OpenTelemetry.

---

**Depends on:** Plans 01 and 03  
**Checkpoint:** R3 with Plan 05

### Task 1: Freeze ten-category and candidate schemas

**Files:** Create protected category schema, detection contracts, fixtures for every category and negative/ambiguous overlaps.

```python
class CandidateItem(BaseModel):
    category: ClearanceCategory
    element_id: UUID
    span_start: int
    span_end: int
    rationale: str
    uncertainty: str
```

Test invalid category, out-of-span citation, duplicate overlap, and unsupported certainty.

### Task 2: Implement durable detection orchestration

**Files:** Create detection domain/application/jobs, model port/ADK adapter, outbox/task adapter tests.

Test queued/running/retry/fail/cancel/idempotency/lease/reconciliation and typed model errors. Persist exact model alias, prompt/policy versions, inputs hash, output, tokens, latency, and cost.

### Task 3: Implement deterministic acceptance gates

**Files:** Create evaluation gate registry and tests.

Block invalid spans/schema/category, cross-project/version links, unsafe legal certainty, prompt-injection policy breach, and missing required rationale/uncertainty. Keep block/warn/info separate from judge scoring.

### Task 4: Implement independent judge and rubric bindings

**Files:** Create rubric schema, judge port/adapter, `AgentEvaluation`/`JudgeVerdict` migrations and API projections.

Persist the exact ten baseline dimensions, but score only dimensions supported by the current run. Evidence, rewrite, and re-scan dimensions are `not_applicable` or `incomplete` until Plans 05 and 08 provide their required bindings. Never infer a score from missing work. High scores cannot override blockers. Test arithmetic over eligible dimensions, incomplete aggregation, and separate model/prompt identity.

### Task 5: Add evaluation corpus and regression report

**Files:** Create `demo/fixtures/evaluation/`, regression runner, CI report artifact.

Track false positives/negatives, category confusion, span accuracy, blocker/warning drift, judge dimensions, latency/tokens/cost. Seed no third-party protected screenplay.

```bash
uv run pytest services/api/tests/detection services/api/tests/evaluation -q
uv run clearcut-eval --corpus demo/fixtures/evaluation --check
```

Expected: tests exit 0; the regression report contains ten categories and all ten declared judge dimensions, with detection-eligible scores and explicit incomplete/not-applicable states for later dimensions.

### Exit criteria

- All ten categories have positive, negative, ambiguous, and injection cases.
- One imported script produces scoped candidate items and complete detection-stage evaluation records without fabricated later-stage scores.
- Deterministic blockers fail closed and remain independent of judge score.
- Model/provider failures are typed and visible.
- R3 evidence identifies model/SDK/runtime call proof without claiming research evidence until Plan 05.

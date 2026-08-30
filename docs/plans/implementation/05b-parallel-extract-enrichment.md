# Bounded Parallel Extract Enrichment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enrich at most three server-selected Search URLs with focused Parallel Extract excerpts while preserving valid Search evidence and exposing every partial or failed enrichment.  
**Architecture:** Extract is a second capability under the existing durable `ResearchRun`, never an alternate research provider or discovery path. URL eligibility is derived deterministically from persisted Search results; the provider adapter returns per-URL typed results/errors and uses the Search session ID.  
**Tech Stack:** Python 3.12, `parallel-web`, Pydantic, PostgreSQL, OpenTelemetry, pytest.

---

**Depends on:** 05a  
**Governing inputs:** `docs/PARALLEL_INTEGRATION.md`, `docs/EVIDENCE_POLICY.md`, `docs/SECURITY_AND_PRIVACY.md`  
**Non-goals:** full-page archival, arbitrary URL extraction, claims, decisions, Task, Monitor.

### Task 1: Freeze Extract and partial-success contracts

**Files:**
- Modify: `packages/contracts/openapi.yaml`
- Create: `services/api/src/clearcut/research/ports/url_extract.py`
- Create: `services/api/src/clearcut/research/domain/extraction.py`
- Test: `services/api/tests/research/test_extract_contracts.py`
- Test: `services/api/tests/conformance/test_url_extract_port.py`

**Step 1:** Add failing tests for one-to-three URLs, focused objective/queries, shared session ID, `full_content=False`, 18,000-character ceiling, per-URL success/error, batch warnings/usage, and closed typed failures.

**Step 2:** Run the tests; expect missing contract failures.

**Step 3:** Implement typed models:

```python
class UrlExtractPort(Protocol):
    def extract(self, request: ExtractRequest) -> ProviderResult[ExtractBatchResponse]: ...

class ExtractBatchResponse(BaseModel):
    extract_id: str
    session_id: str
    results: tuple[ExtractedPage, ...]
    errors: tuple[ExtractedPageError, ...]
    warnings: tuple[ProviderWarning, ...]
```

`ExtractBatchResponse` may contain both results and errors. A successful HTTP/provider response with only URL errors is a completed batch whose enrichment outcome is `failed`, not a fabricated provider success with evidence.

**Step 4:** Run contract generation/drift checks and conformance tests; expect pass.

### Task 2: Select and authorize URLs deterministically

**Files:**
- Create: `services/api/src/clearcut/research/application/select_extract_targets.py`
- Test: `services/api/tests/research/test_extract_target_selection.py`
- Test: `services/api/tests/security/test_extract_target_scope.py`

**Step 1:** Add failing tests for provider relevance order, canonical duplicates, authority-policy input, three-URL ceiling, unsafe schemes, redirects, private/local addresses, model-injected URLs, URLs from another run/project, and zero eligible targets.

**Step 2:** Run tests; expect missing selector failures.

**Step 3:** Implement a pure selector that accepts only persisted canonical HTTPS Search results from the same org/project/item/version/run. Model output may not add or reorder URLs after Search. Authority classification remains a proposal and cannot bypass URL safety or scope.

**Step 4:** Run tests; expect the selected set to be deterministic and never exceed three URLs.

### Task 3: Implement the official Parallel Extract adapter

**Files:**
- Create: `services/api/src/clearcut/research/adapters/parallel_extract.py`
- Create: `services/api/tests/fixtures/parallel/extract_success.json`
- Create: `services/api/tests/fixtures/parallel/extract_partial.json`
- Create: `services/api/tests/fixtures/parallel/extract_all_errors.json`
- Test: `services/api/tests/research/test_parallel_extract_adapter.py`

**Step 1:** Add failing normalization tests using sanitized real captures with `extract_id`, `session_id`, results, per-URL errors, title, publication date, excerpts, warnings, usage, and capture metadata.

**Step 2:** Run the tests; expect adapter absence.

**Step 3:** Implement the bounded SDK call:

```python
response = client.extract(
    urls=[str(url) for url in request.urls],
    objective=request.objective,
    search_queries=list(request.search_queries),
    max_chars_total=request.max_chars_total,
    session_id=request.session_id,
    client_model=request.client_model,
)
```

Do not enable `full_content`. Normalize results/errors independently and reject any returned URL that cannot be bound to an authorized target.

**Step 4:** Map batch transport/auth/config/schema/ambiguous failures through the shared taxonomy while retaining URL-level extraction errors inside a successful batch result.

**Step 5:** Run adapter/conformance tests; expect pass.

### Task 4: Persist enrichment without weakening Search evidence

**Files:**
- Create: `services/api/src/clearcut/research/application/run_extract.py`
- Modify: `services/api/src/clearcut/bootstrap/adapter_registry.py`
- Test: `services/api/tests/research/test_run_extract.py`
- Test: `services/api/tests/research/test_extract_partial_outcomes.py`
- Test: `services/api/tests/security/test_extract_redaction.py`

**Step 1:** Add failing tests for Search empty/failure short-circuit, no eligible URLs, full/partial/total Extract outcome, timeout/retry, duplicate dispatch, cross-scope result, excerpt injection, and Search snapshot preservation.

**Step 2:** Run tests; expect application failures.

**Step 3:** Implement the durable Extract attempt using the 0008 shared attempt/snapshot tables. Each extracted page creates a new immutable `extract_excerpt` snapshot linked to its authorizing Search result and attempt. Each URL error is retained as a visible attempt result.

**Step 4:** Prove that valid `search_excerpt` snapshots remain unchanged when Extract fails and that no `extract_excerpt` snapshot exists without an authorizing Search result from the same run.

**Step 5:** Register `ParallelExtractAdapter` as the only production `UrlExtractPort` and reject alternate/fake bindings at startup.

**Step 6:** Run research/security/migration/contract tests; expect pass.

### Task 5: Verify budgets, traces, and evidence handoff

**Files:**
- Create: `services/api/tests/live/test_parallel_extract_live.py`
- Modify: `scripts/verify-runtime-profile.mjs`
- Create: `docs/reviews/<date>-05b-parallel-extract-evidence.md`

**Step 1:** Add failing assertions for maximum target count, characters, timeout, two-attempt retry ceiling, `parallel.extract` span, safe result/error counts, source links, and absence of full page bodies.

**Step 2:** Run the full 05a–05b research suite and contract drift checks; expect pass.

**Step 3:** With explicitly authorized credentials, run Extract on one or two URLs returned by the recorded live Search run. Record safe provider/session IDs, status, latency, result/error counts, and snapshot IDs. Do not claim Extract success when only Search succeeded.

**Step 4:** Stage and commit only after owner authorization with `feat: add bounded parallel extraction`.

### Exit criteria

- Extract is bounded enrichment, not discovery and not a condition for contest Search eligibility.
- Every URL was returned by and linked to the same scoped Search run.
- Partial and total failures are visible and do not erase valid Search evidence.
- No full content, arbitrary URL, raw payload, or excluded Parallel agent capability enters the runtime.


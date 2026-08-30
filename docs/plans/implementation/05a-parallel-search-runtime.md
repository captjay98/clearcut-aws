# Parallel Search Runtime and Provenance Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make a real Parallel Search API call the mandatory first step of every evidence research run and persist complete immutable query, attempt, result, and snapshot provenance.  
**Architecture:** Gemini/ADK produces a bounded typed `ResearchPlan`; the research application service enforces budgets and calls a `WebSearchPort`. The submitted composition root binds only the official Parallel Search adapter, and evidence remains unresolved on empty or failed searches.  
**Tech Stack:** Python 3.12, FastAPI, Pydantic, SQLAlchemy/Alembic, PostgreSQL, Google ADK, `parallel-web`, OpenTelemetry, pytest.

---

**Depends on:** 04a, 01b  
**Governing inputs:** `docs/PARALLEL_INTEGRATION.md`, `docs/EVIDENCE_POLICY.md`, `docs/SECURITY_AND_PRIVACY.md`, `docs/API_CONTRACT.md`, `docs/ARCHITECTURE.md`  
**Non-goals:** Extract implementation, claim admission, human decisions, Monitor, Task, FindAll, Responses/Chat, Interactions, Deep Research.

### Task 1: Freeze Search contracts and the shared research-attempt seam

**Files:**
- Modify: `packages/contracts/openapi.yaml`
- Create: `packages/contracts/schemas/research-plan.schema.json`
- Create: `services/api/src/clearcut/research/domain/queries.py`
- Create: `services/api/src/clearcut/research/domain/snapshots.py`
- Create: `services/api/src/clearcut/research/ports/web_search.py`
- Create: `services/api/alembic/versions/0008_research_snapshots.py`
- Test: `services/api/tests/research/test_search_contracts.py`
- Test: `services/api/tests/research/test_snapshot_provenance.py`
- Test: `services/api/tests/migrations/test_0008_research_snapshots.py`

**Step 1:** Add failing schema tests for a 20–600 character objective, exactly two or three concise queries, closed Search modes, provider result/error unions, operation kind, and org/project/item/version scope. Verify unknown fields fail.

```python
def test_research_plan_rejects_four_queries() -> None:
    with pytest.raises(ValidationError):
        ResearchPlan(objective="Find attributable evidence for the detected item.", search_queries=["a b", "c d", "e f", "g h"])
```

**Step 2:** Run `uv run pytest services/api/tests/research/test_search_contracts.py -q`. Expect failure because the research contracts do not exist.

**Step 3:** Define closed typed request/response models. `SearchResponse` must contain ClearCut correlation ID, provider `search_id`, provider `session_id`, warnings, usage, ordered normalized results, and timing. `ProviderFailure` uses the shared taxonomy and never carries the raw provider exception.

```python
class WebSearchPort(Protocol):
    def search(self, request: SearchRequest) -> ProviderResult[SearchResponse]: ...
```

**Step 4:** Add migration 0008 for `research_runs`, `research_queries`, `provider_attempts`, and immutable `source_snapshots`. Include composite org/project foreign keys, attempt operation kind (`search` or `extract`), provider/session/receipt fields, immutable timestamps, excerpt origin, hashes, and uniqueness preventing cross-project bindings. Do not add claims in this migration.

**Step 5:** Test upgrade, downgrade, foreign-key rejection, uniqueness, indexes, and immutable-update rejection. Run `uv run pytest services/api/tests/research/test_search_contracts.py services/api/tests/research/test_snapshot_provenance.py services/api/tests/migrations/test_0008_research_snapshots.py -q`; expect pass.

**Step 6:** Run `pnpm contract:generate && pnpm contract:check`; expect generated TypeScript/Python clients to be clean.

### Task 2: Implement bounded Gemini-to-Search planning

**Files:**
- Create: `services/api/src/clearcut/research/application/plan_research.py`
- Create: `services/api/src/clearcut/research/domain/limits.py`
- Test: `services/api/tests/research/test_query_planning.py`
- Test: `services/api/tests/research/test_research_limits.py`

**Step 1:** Add failing positive, negative, ambiguous, duplicate-query, overlong, prompt-injection, cross-category, and least-data tests. The planner may receive bounded script context but must not emit the full screenplay, tenant names, private comments, or arbitrary URLs.

**Step 2:** Run the two tests; expect contract/limit failures.

**Step 3:** Implement normalization and hard ceilings from `docs/PARALLEL_INTEGRATION.md`: two or three queries, 24,000 result characters, eight-second timeout, two attempts, and an application-owned mode. Normalize whitespace/case only for deduplication; retain the exact submitted text in protected attempt provenance.

**Step 4:** Add a table-driven category fixture so all ten protected categories produce self-contained objectives without changing protected category or authority policy.

**Step 5:** Run `uv run pytest services/api/tests/research/test_query_planning.py services/api/tests/research/test_research_limits.py -q`; expect pass.

### Task 3: Implement the official Parallel Search adapter

**Files:**
- Create: `services/api/src/clearcut/research/adapters/parallel_search.py`
- Create: `services/api/src/clearcut/research/adapters/parallel_errors.py`
- Create: `services/api/tests/fixtures/parallel/search_success.json`
- Create: `services/api/tests/fixtures/parallel/search_empty.json`
- Create: `services/api/tests/fixtures/parallel/search_warnings.json`
- Test: `services/api/tests/research/test_parallel_search_adapter.py`
- Test: `services/api/tests/conformance/test_web_search_port.py`

**Step 1:** Add failing adapter tests using sanitized captures that retain capture time, API/SDK version, request mode, `search_id`, `session_id`, warnings, usage, URLs, titles, dates, and excerpts. Fixtures must never invent a source or claim.

**Step 2:** Run the adapter/conformance tests; expect failure because the adapter is absent.

**Step 3:** Implement one official SDK call and normalize it immediately:

```python
response = client.search(
    objective=request.objective,
    search_queries=list(request.search_queries),
    mode=request.mode,
    max_chars_total=request.max_chars_total,
    session_id=request.session_id,
    client_model=request.client_model,
)
```

The adapter must not expose the SDK object or raw dictionary. Pin the SDK version in the workspace dependency lock and record it on attempts.

**Step 4:** Map rate limit, timeout/network, authentication, configuration, validation/schema, permanent, and ambiguous outcomes to the closed failure taxonomy. Empty results are `SearchSuccess(results=[])`, not `ProviderFailure`.

**Step 5:** Canonicalize only HTTP(S) URLs, retain returned URL separately, reject unsafe schemes/redirect results, bound excerpts, preserve provider ordering, and retain warnings. Do not fetch URLs locally in this packet.

**Step 6:** Run the adapter/conformance tests; expect pass with no raw provider type crossing the port.

### Task 4: Persist the durable Search workflow

**Files:**
- Create: `services/api/src/clearcut/research/application/run_search.py`
- Create: `services/api/src/clearcut/research/application/reconcile_search.py`
- Modify: `services/api/src/clearcut/bootstrap/adapter_registry.py`
- Test: `services/api/tests/research/test_run_search.py`
- Test: `services/api/tests/research/test_search_reconciliation.py`
- Test: `services/api/tests/security/test_research_scope.py`
- Test: `services/api/tests/security/test_research_redaction.py`

**Step 1:** Add failing authorization, idempotency, lease, retry, cancellation, cross-project, empty-result, partial-normalization, ambiguous-outcome, and redaction tests.

**Step 2:** Run the tests; expect failures at the missing application service/registry.

**Step 3:** Implement authorize → create run/query/attempt/outbox atomically → call provider in worker → persist terminal attempt and immutable Search snapshots → enqueue Extract eligibility. A request handler never waits through provider retries.

**Step 4:** Retry only `retryable` and `rate_limited` outcomes within the two-attempt ceiling. Reconcile `ambiguous` outcomes by attempt/provider receipt before another external call. Manual retry creates a linked attempt.

**Step 5:** Register `ParallelSearchAdapter` as the only production `WebSearchPort`; startup must fail on missing credentials or any alternate/fake production binding.

**Step 6:** Run the application/security tests; expect pass and zero cross-tenant reads/writes or secret/raw-body leakage.

### Task 5: Prove Search eligibility and runtime behavior

**Files:**
- Create: `services/api/tests/live/test_parallel_search_live.py`
- Modify: `scripts/verify-runtime-profile.mjs`
- Create: `docs/reviews/<date>-05a-parallel-search-evidence.md`

**Step 1:** Add failing runtime-profile checks for the official `parallel-web` dependency, the `client.search` call path, mandatory Search adapter registration, and absence of Task, FindAll, Responses/Chat, Interaction, Deep Research, or alternate research runtime imports/configuration.

**Step 2:** Run all narrow tests and `pnpm contract:check`; expect pass.

**Step 3:** With explicitly authorized development credentials, run one bounded live Search against an entrant-owned fictional item. Record timestamp, source SHA, SDK/API version, mode, safe query hash, status, latency, provider IDs, result count, snapshot IDs, and explicit non-claims. Never commit the API key, raw payload, full script, or hidden reasoning.

**Step 4:** Run `uv run clearcut-eval --check-provenance`; expect no Search snapshot missing its query/run/attempt/version binding.

**Step 5:** Stage and commit only after owner authorization with `feat: add parallel search provenance path`.

### Exit criteria

- A real Parallel Search call is the only submitted discovery path and is machine-detectable.
- Every Search run is scoped, bounded, durable, typed, redacted, retry-safe, and traceable.
- Empty and failed Search leave the item unresolved and create visible work.
- No claim admission, Extract, Monitor, or excluded Parallel capability is smuggled into this packet.
- One live trace proves development behavior but does not claim deployment or submission readiness.


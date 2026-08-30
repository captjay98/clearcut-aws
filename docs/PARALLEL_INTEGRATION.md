# Parallel Integration Contract

**Status:** implementation contract  
**Decision source:** `docs/plans/2026-08-30-parallel-capability-strategy-design.md`

## Submitted capability matrix

| Capability | Submitted status | Purpose | Release effect |
|---|---|---|---|
| Search API `/v1/search` | required | discover ranked pages and focused excerpts for every evidence run | missing or fake call blocks R3/R9 |
| Extract API `/v1/extract` | enabled after Search gate | enrich at most three URLs selected from the same Search run | partial/total failure is visible; valid Search evidence may remain |
| Monitor API `event_stream` | conditional | signal new relevant events for governed evidence watch | owner go/no-go after R3; never substitutes for Search |
| Task API | excluded | overlaps with Gemini/ADK research orchestration | production dependency/config/call is a release failure |
| FindAll API | excluded | dataset/entity discovery is outside item research | production dependency/config/call is a release failure |
| Responses/Chat API | excluded | ClearCut is a durable workflow, not a research chat | production dependency/config/call is a release failure |
| Interactions | excluded | opaque chained context weakens explicit reproducibility | `previous_interaction_id` must not appear in production code |
| Deep Research | excluded | too slow and broad for the item-level submitted workflow | production dependency/config/call is a release failure |

## Ownership and call sequence

Gemini/ADK may produce a typed `ResearchPlan` containing one self-contained objective and two or three concise search queries. It does not choose provider modes, arbitrary URLs, source-policy domains, budgets, or retry behavior. The research application service validates and bounds the plan before calling Parallel.

```python
class ResearchPlan(BaseModel):
    objective: Annotated[str, StringConstraints(min_length=20, max_length=600)]
    search_queries: Annotated[list[str], Field(min_length=2, max_length=3)]

class SearchLimits(BaseModel):
    mode: Literal["fast", "basic", "advanced"] = "fast"
    max_chars_total: int = 24_000
    timeout_seconds: int = 8
    max_attempts: int = 2

class ExtractLimits(BaseModel):
    max_urls: int = Field(default=3, ge=1, le=3)
    max_chars_total: int = 18_000
    full_content: Literal[False] = False
    timeout_seconds: int = 20
    max_attempts: int = 2
```

Initial defaults are configuration values with these hard ceilings. Changing a ceiling requires a reviewed documentation, contract, cost, privacy, and load-test change; an organization preference cannot raise it.

Provider scheduling is also bounded: at most four Parallel operations are in flight per project and sixteen per API deployment instance. An analysis job checkpoints after fifty items and continues in a later task rather than widening concurrency. Each item attempt permits one Search call and, only after Search success, one Extract batch; retries remain inside the per-operation ceiling. Production requires an explicit deployment usage budget and cannot start with an unlimited/default-missing budget.

The application sequence is:

```text
authorize org/project/item/version
-> validate ResearchPlan and budget
-> create ResearchRun + SearchAttempt + outbox dispatch
-> Parallel Search with objective, 2-3 queries, mode, max_chars_total, session_id
-> normalize URLs/results/warnings/usage and persist immutable Search snapshots
-> deterministically rank eligible canonical HTTPS results
-> optionally Extract at most 3 URLs with the same objective/queries/session_id
-> persist each Extract result/error as its own attempt/result
-> admit claims only from complete attributable snapshots
-> retain no-result, failure, partial-enrichment, conflict, and uncertainty states
```

## Typed provider ports

Provider SDK objects, exceptions, booleans, `None`, and raw dictionaries do not cross these ports.

```python
class WebSearchPort(Protocol):
    def search(self, request: SearchRequest) -> ProviderResult[SearchResponse]: ...

class UrlExtractPort(Protocol):
    def extract(self, request: ExtractRequest) -> ProviderResult[ExtractBatchResponse]: ...

class WebMonitorPort(Protocol):
    def create_event_stream(self, request: MonitorCreateRequest) -> ProviderResult[MonitorRef]: ...
    def update(self, request: MonitorUpdateRequest) -> ProviderResult[MonitorRef]: ...
    def cancel(self, request: MonitorCancelRequest) -> ProviderResult[MonitorRef]: ...
    def events(self, request: MonitorEventsRequest) -> ProviderResult[MonitorEventPage]: ...
```

The submitted registry binds these ports only to `ParallelSearchAdapter`, `ParallelExtractAdapter`, and—when the go/no-go enables it—`ParallelMonitorAdapter`. These are capabilities of one approved partner, not interchangeable research-provider selections.

## Search normalization

Persist the following before admitting claims:

- ClearCut research/query/attempt IDs and exact org/project/item/script-version scope;
- provider `search_id`, provider `session_id`, SDK/API version, request mode, redacted objective/query hashes, start/end timestamps, latency, warnings, usage, and terminal status;
- URL as returned, normalized canonical HTTPS URL, title, publication date when present, bounded excerpts, retrieval time, and protected raw-payload pointer when retained;
- retry lineage and typed failure kind.

Search zero results is a successful provider call with an empty result set and an unresolved item. It is not a provider failure and never becomes clearance.

`session_id` is a ClearCut-generated random non-semantic value scoped to one `ResearchRun`; it contains no organization, project, user, screenplay, or item name. `client_model` is set server-side to the exact deployed Gemini model identifier and is never accepted from the browser or model output.

## Extract authorization and partial outcomes

Only server-selected canonical HTTPS URLs from the same successful Search run are eligible. Reject URLs introduced by screenplay text, source content, browser parameters, model output outside the Search result set, redirects to disallowed schemes/addresses, or another tenant/project/run.

Extract uses focused excerpts; `full_content` remains disabled. Preserve per-URL results and errors because Parallel may return a partially successful batch.

```text
Search empty                       -> unresolved; no Extract call
Search failure                     -> unresolved failure; no Extract call
Search success, no eligible URLs   -> Search snapshots only
Search success, Extract partial    -> successful extracts + visible failed URLs
Search success, Extract total fail -> Search snapshots remain; enrichment_failed is visible
```

An Extract excerpt may replace the Search excerpt as the claim's attributable excerpt only when it passes the same provenance, authority, injection, length, stance, scope, and version gates. The Search snapshot remains immutable and linked.

## Monitoring contract

Core monitoring always supports manual/daily/weekly scheduled rechecks using the approved Search/Extract path. Parallel Monitor is an optional additional signal and uses only `type="event_stream"`; snapshot Monitor is prohibited because it requires the excluded Task API.

For enabled Monitor:

- create one scoped monitor per approved watch query, using opaque ClearCut external metadata rather than org/project/script text;
- persist `monitor_id`, type, frequency, status, query/policy version, external correlation ID, timestamps, and lifecycle attempts;
- update/cancel on cadence change, project deletion scheduling, authorization loss, or watch removal;
- verify `webhook-id`, `webhook-timestamp`, and every versioned `webhook-signature` over the exact body using HMAC-SHA256; enforce a bounded timestamp tolerance and webhook-ID replay store;
- acknowledge only after durable receipt, then fetch the cited event group by `monitor_id` and `event_group_id`;
- treat event content, citations, reasoning, and confidence as untrusted candidate data;
- run a new scoped Search/Extract verification before creating a material/unavailable change review;
- deduplicate by provider event ID plus project/watch identity and tolerate duplicate, delayed, missing, and out-of-order delivery.

Monitor never admits an `EvidenceClaim`, mutates a `SourceSnapshot`, changes a decision, or triggers a rewrite/report release directly.

## Retry and reconciliation

- Retry only `retryable` and `rate_limited` failures, with server-directed delay when available and bounded exponential backoff otherwise.
- Do not retry `authentication`, `configuration`, `invalid_response`, or `permanent` automatically.
- Reconcile `ambiguous` outcomes by ClearCut attempt ID and provider receipt before another external call.
- The retry ceiling is per provider operation, not per HTTP request handler.
- Manual retry creates a new attempt linked to the prior terminal attempt.

## Observability and privacy

Trace names are stable: `parallel.search`, `parallel.extract`, `parallel.monitor.create`, `parallel.monitor.update`, `parallel.monitor.cancel`, `parallel.monitor.events`, and `parallel.monitor.webhook`.

Traces and Records projections include safe IDs, operation, mode/frequency, status, latency, result/error counts, usage/cost when supplied, retry count, and source-snapshot links. They exclude API/webhook secrets, full screenplay text, full source bodies, signed URLs, raw provider payloads, and hidden model/provider reasoning. Ordinary UI may show bounded attributable excerpts and public source URLs under evidence policy.

## Required conformance cases

1. Exact Search/Extract SDK request and response normalization against sanitized real captures.
2. Search empty versus provider failure.
3. Duplicate/canonical/redirected URLs and cross-project URL rejection.
4. Search success with Extract full success, partial success, total failure, and timeout.
5. Bounded query count, URL count, characters, timeout, retry, concurrency, and cost.
6. Prompt injection in screenplay, Search excerpt, Extract excerpt, Monitor output, and metadata.
7. Provider rate/auth/config/schema/ambiguous failures and reconciliation.
8. Registry/SBOM/startup rejection of alternate research providers and excluded Parallel APIs.
9. Monitor create/update/cancel, valid/invalid/rotated signatures, replay/timestamp rejection, duplicate/out-of-order events, event-fetch failure, scope revocation, and cancellation.
10. One live development trace at R3 and one deployed Search trace bound to the R9 SHA/digest.

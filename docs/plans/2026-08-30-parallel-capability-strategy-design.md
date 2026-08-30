# Parallel Capability Strategy Design

**Date:** 2026-08-30  
**Status:** Approved  
**Decision owner:** Product owner  
**Applies to:** Agentic Cinema Parallel-track submission and the initial open-source release

## Decision

ClearCut uses the smallest Parallel capability set that is load-bearing for the product and legible to judges:

1. **Search API is mandatory and release-blocking.** Every submitted evidence run starts with a real Parallel Search call. Search is the contest-required runtime integration and the primary discovery source for attributable web evidence.
2. **Extract API is bounded enrichment.** ClearCut may extract focused excerpts from no more than three server-selected Search result URLs per research run. Extract is never called on an arbitrary model- or browser-supplied URL, never requests full page content in the submitted profile, and may partially fail without erasing valid Search snapshots.
3. **Monitor API is conditional and non-blocking.** After the R3 Search/Extract evidence slice is stable, the owner may enable Parallel `event_stream` monitors as an additional signal for new relevant web events. A Monitor event is untrusted candidate input; ClearCut verifies it through the normal Search/Extract provenance path before opening governed review.
4. **Task, FindAll, Responses/Chat, Interactions, and Deep Research are excluded from the submitted runtime.** They add latency or opaque conversational/research state, overlap with Gemini/ADK orchestration, or solve dataset-building problems outside the screenplay-item workflow.

The submitted division of responsibility is explicit:

```text
Gemini through Google ADK
  -> detects candidate items and plans bounded research objectives/queries
Parallel Search
  -> discovers ranked URLs and attributable excerpts
Parallel Extract
  -> enriches up to three selected Search URLs with focused excerpts
ClearCut deterministic gates
  -> admit snapshots/claims, retain conflicts, enforce scope and provenance
Accountable human
  -> records decisions, referrals, rewrites, monitoring reviews, and releases
Parallel Monitor event_stream (conditional)
  -> surfaces candidate changes; never changes evidence or decisions directly
```

## Considered approaches

### A. Search only

Lowest delivery risk and sufficient for contest eligibility, but weaker on difficult pages/PDFs and less convincing for the product's continuing evidence-watch story.

### B. Search + bounded Extract + conditional Monitor — selected

Keeps Search visibly mandatory, improves source capture without turning Parallel into the product's reasoning layer, and leaves Monitor behind a go/no-go gate so it cannot endanger the evidence vertical slice.

### C. Full Parallel agent suite

Using Task, Responses/Chat, Interactions, FindAll, and Deep Research would broaden surface area without strengthening the screenplay clearance workflow proportionally. It would also blur Gemini/ADK's required agent role and make version-bound evidence harder to reproduce.

## Architectural consequences

- Core domain contracts expose capability-specific ports: `WebSearchPort`, `UrlExtractPort`, and optional `WebMonitorPort`. The contest composition root binds all enabled capabilities to the official Parallel SDK; no other research provider or silent fallback is registered.
- `SearchAttempt` and `ExtractAttempt` are distinct immutable attempt records under one `ResearchRun`. They share a ClearCut-generated correlation/session key and retain the provider-returned `search_id`, `extract_id`, and `session_id` where present.
- A `SourceSnapshot` records whether its admitted excerpt came from `search_excerpt` or `extract_excerpt`, while retaining the Search result/query that authorized the URL.
- Extract enriches only canonical HTTPS URLs returned by the same scoped Search run. Search results remain usable if Extract partially or wholly fails, provided the Search excerpt independently satisfies the evidence admission policy.
- Monitor uses `event_stream`, not snapshot monitors, because Parallel snapshot monitors depend on Task runs and Task is intentionally excluded. Exact retained-URL rechecks use scheduled bounded Extract; Monitor supplies new-event signals.
- The open-source interfaces are extensible after the contest, but the submitted dependency graph and production registry contain only Gemini/ADK and the approved Parallel capabilities.

## Release gates

- **R3 blocker:** real Search call, persisted provenance, typed failures, no-result behavior, bounded optional Extract, and one live trace.
- **Extract gate:** Search behavior and evidence admission must pass before Extract is enabled. Extract failure cannot change a valid Search result into invented evidence or a false success.
- **Monitor go/no-go:** owner decision after R3 based on remaining schedule, live credentials/quota, webhook verification proof, and completed golden-path tests. A no-go does not block submission; scheduled Search/Extract monitoring remains the product path.
- **R9 blocker:** the video and immutable submission manifest prove a live Search call from the deployed SHA. Extract and Monitor are claimed only if their deployed traces and user-visible behavior are also verified.

## Official references

- Parallel Search: https://docs.parallel.ai/search/search-quickstart
- Parallel Extract: https://docs.parallel.ai/extract/extract-quickstart
- Parallel Monitor event stream: https://docs.parallel.ai/monitor-api/monitor-quickstart
- Parallel webhook verification: https://docs.parallel.ai/resources/webhook-setup
- Agentic Cinema rules: https://agentic-cinema.devpost.com/rules


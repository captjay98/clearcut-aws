# Parallel Evidence Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn candidate items into current, attributable, conflict-aware evidence using mandatory Parallel Search and bounded Extract while making empty, partial, and failed research explicitly unresolved.

**Architecture:** The ADK agent plans narrow typed objectives/queries; application-owned limits authorize Parallel Search and up to three Extract targets from that Search result set. Capability-specific ports normalize results into immutable origin-labelled snapshots. Claims are admitted only through provenance gates and remain separate from human decisions.

**Tech Stack:** Parallel official SDK/supported integration, Google ADK/Gemini, FastAPI jobs, PostgreSQL, protected object storage, OpenTelemetry.

---

**Depends on:** Plan 04  
**Checkpoint:** R3

### Task 1: Define typed research/provider contracts

**Files:** Create research OpenAPI/schema changes, provider port/result unions, source/claim/conflict migrations and contract tests.

```python
ResearchResult = ResearchSuccess | ProviderFailure
```

`ProviderFailure.kind` uses the shared closed taxonomy in `docs/ARCHITECTURE.md`: `retryable`, `rate_limited`, `authentication`, `configuration`, `invalid_response`, `permanent`, or `ambiguous`. Require query/run identity, URL/title/publisher, retrieved/published timestamps, excerpt, authority proposal, stance, provider receipt, and raw-payload protection pointer.

### Task 2: Implement query planning and mandatory live Parallel Search

Write failing tests for category-specific bounded queries, query normalization, timeout/rate/auth/schema errors, no results, duplicate URLs, redirect/canonicalization, and redaction. Implement the adapter without returning raw dicts.

### Task 3: Enrich selected Search results with bounded Extract

Select no more than three canonical HTTPS URLs returned by the same scoped Search run. Reuse the provider session ID, request focused excerpts only, preserve per-URL partial errors, and never erase a valid Search snapshot when enrichment fails. Test arbitrary/model-injected/cross-project URLs, full/partial/total failure, timeout, prompt injection, and hard character/attempt ceilings.

### Task 4: Persist snapshots before claims

Store each completed Search/Extract attempt and immutable origin-labelled snapshot; then admit cited claims through deterministic provenance/tenant/version gates. Test that a claim cannot exist without its source/query/version, an Extract snapshot cannot exist without its authorizing Search result, and no claim can cite another project.

### Task 5: Compute conflicts, authority, confidence, and unresolved states

Use versioned protected authority policy and deterministic conflict inputs. Model synthesis may explain but not erase source disagreement. Test zero results, only low-authority sources, conflicting sources, unavailable source, and unsupported certainty.

### Task 6: Expose source-module projections and live runtime proof

Add scoped item-evidence endpoints plus typed projection ports consumed later by Records. Do not create Records routes in this plan. Persist tool, redacted arguments/result, status, duration, token/cost, provider receipt ID, and linked snapshots. Capture a live development trace with timestamp/model/query/status/latency/source IDs; never commit credentials/raw payloads.

```bash
uv run pytest services/api/tests/research services/api/tests/evidence -q
uv run clearcut-eval --check-provenance
pnpm contract:check
```

Expected: tests exit 0 and the provenance check reports zero claims missing a source snapshot/query/run binding.

### Exit criteria

- Parallel is imported/configured and actually called in the runtime path.
- Search is mandatory; Extract is bounded enrichment with visible partial/failed outcomes.
- Every `EvidenceClaim` has complete attributable provenance.
- No-result/failure paths create unresolved items and visible review work.
- Conflicts and uncertainty survive synthesis and UI contracts.
- Evidence-stage evaluation completes grounding, provenance, authority/freshness, conflict, uncertainty, and tool-efficiency dimensions while later rewrite/re-scan dimensions remain explicit.
- Tool totals derive from attempt records.
- R3 proves one live evidence vertical slice and states it is not production/deployment proof.
- Task, FindAll, Responses/Chat, Interactions, Deep Research, snapshot Monitor, alternate providers, and silent fallbacks are absent.

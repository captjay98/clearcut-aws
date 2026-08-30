---
name: observability-patterns
description: Correlation IDs, structured logging, and distributed tracing
---

# Observability Patterns

## 1. Correlation IDs

Every operation must have a traceable ID across the stack.

- Client generates `X-Request-ID` (UUID)
- Propagate through all service calls
- Include in error reports and logs

## 2. Structured Logging

Never log just the message. Log the context:
- Request ID, user/actor, operation name
- Domain-relevant metadata (truncated)
- Error code and stack trace

## 3. ClearCut-Specific Observability

### Research Pipeline Tracing

Every Parallel Search, Extract, and enabled Monitor operation is recorded as an `AgentToolCall` or provider-attempt projection with:
- Tool name (`parallel.search`), target (category + term)
- Duration in milliseconds
- Source count returned
- Conflict count
- Terminal status (`ok`, `timeout`, `partial`, `error`)
- Parent `AgentRun` ID for grouping

These are first-class domain records, not just logs. The Records surface (`#records`) exposes them to users. The judge evaluation references them.

### Governed Action Audit Trail

Every consequential action produces an authoritative `AuditEvent`:
- Actor identity (who), action type (what), timestamp (when)
- Item/project/org scope (where)
- Decision payload hash (what exactly)
- Stable event ID and references used to build a redacted human-readable Receipt projection

The `AuditEvent` commits transactionally with the decision—never best-effort. A Receipt is a rebuildable read projection, not an independently mutable audit authority.

### Evidence Provenance Chain

Log the full chain for debugging evidence integrity:
```
ResearchRun → SearchAttempt → SearchSnapshot → ExtractAttempt? → ExtractSnapshot? → EvidenceClaim → EvidenceConflict
MonitorEvent? → verification ResearchRun → verified snapshot change → governed review
```

Each link carries IDs that trace to the protected provider-response record. Records exposes only typed/redacted summaries and authorized `SourceSnapshot` excerpts; it never displays unrestricted provider payloads.

### Judge Evaluation Records

Every graded run logs:
- All 10 rubric dimension scores
- Deterministic gate results (pass/warn/block)
- Model used, prompt version, rubric version, policy version
- Latency and estimated cost

### Sensitive Data Redaction

**Always redact in logs and traces:**
- Screenplay text and dialogue
- Evidence excerpts beyond 50 characters
- API keys and provider credentials
- Invitation tokens
- User email addresses

**Safe to log:**
- Item IDs, run IDs, receipt IDs
- Category names, severity levels, status values
- Duration, cost, source counts
- Org ID, project ID (for tenant correlation)

## 4. Infrastructure Telemetry

ClearCut uses OpenTelemetry with Cloud Logging and Cloud Trace.

**Key metrics to track:**
- Research run success/failure rates
- Parallel API latency (P50, P95, P99)
- Judge evaluation latency and cost per run
- Cloud Tasks queue depth and processing latency
- Evidence coverage per project (flags with sources / total flags)
- Monitoring change detection rate
- Blocked output rate (deterministic gates)

**Alerting thresholds:**
- Research run failure rate > 10% in 5 minutes
- Parallel API P95 latency > 10s
- Cloud Tasks queue depth > 100
- Any cross-tenant access attempt (immediate alert)

## Decision Guide

**Use when:**
- Adding a new API endpoint or service method
- Implementing research pipeline or evidence processing
- Building governed action handlers
- Setting up production monitoring

**Don't use when:**
- Purely static/presentational code
- Mock prototype changes
- Local development debugging (use console.log)

**Decision tree:**
- New API endpoint? → Add correlation ID propagation + structured logging
- Research/evidence operation? → Create `AgentToolCall` records with full provenance
- Governed action? → Transactional authoritative `AuditEvent` plus redacted Receipt projection
- Production issue? → Check correlation ID trail, then tool call records, then audit events

**Failure modes:**
- No correlation ID → can't trace a request across FastAPI → Cloud Tasks → Parallel
- No tool call records → can't explain what the evidence pipeline did or what it cost
- Best-effort audit → decision recorded but audit event lost on crash
- Unredacted logs → screenplay text or credentials exposed in Cloud Logging

# ClearCut Evidence Policy

## Boundary

ClearCut gathers and organizes pre-clearance evidence. It does not issue legal conclusions, certificates, or guarantees. Final decisions belong to qualified humans; unresolved and conflicting evidence stays visible in every report.

## Claim admission rule

An `EvidenceClaim` is admitted only when it cites one immutable Parallel `SourceSnapshot` with:

- canonical URL and title;
- retrieval timestamp and publication/update time when available;
- short attributable excerpt;
- publisher and authority classification;
- supports/disagrees/context stance;
- query and research-run identity;
- agent/tool/prompt/model/policy/version provenance;
- snapshot hash/identifier and retention state.

No result, provider failure, inaccessible source, or empty search may be converted into a claim. A project-owned `ClearanceItem` with zero claims is valid and unresolved.

## Authority and conflicts

Authority tiers are versioned protected policy, not model truth. The model may propose a classification; deterministic policy validates the allowed tier and records the basis. Conflicting sources remain distinct claims linked by an `EvidenceConflict`; synthesis cannot erase the disagreement.

## Untrusted content

Screenplays, PDFs, XML, websites, excerpts, metadata, and provider payloads are data, never instructions. They cannot change system prompts, tool permissions, tenant scope, approval policy, source authority, or retrieval targets. Server-side fetching enforces SSRF controls and bounded content handling.

## Freshness and monitoring

Every claim displays retrieval time. Scheduled monitoring rechecks retained URLs through bounded Extract and topic/query watches through mandatory Search. Conditional Parallel Monitor `event_stream` signals are untrusted candidates and must pass a new scoped Search/Extract run before comparison. Monitoring compares verified old/new snapshots and classifies the change as non-material, material, or unavailable. It opens review work; it never rewrites an accepted decision.

## Redaction and retention

Records shows bounded excerpts and redacted tool summaries, not raw provider payloads, full screenplay/source bodies, credentials, tokens, signed URLs, or hidden model reasoning. Core evidence and governed audit have no age-based deletion; whole-project/organization deletion follows the documented grace/purge process and marks reproducibility loss.

## Evaluation gates

Deterministic admission blocks:

```text
missing citation
missing attributable excerpt
missing query/run identity
unsupported stance or authority value
cross-project source reference
legal-certainty language
unresolved prompt-injection signal
```

Judge scores may warn or prioritize review but never override an admission blocker.

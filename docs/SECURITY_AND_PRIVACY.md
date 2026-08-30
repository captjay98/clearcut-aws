# ClearCut Security and Privacy

## Threat priorities

1. Cross-tenant or cross-project disclosure.
2. Forged/stale authorization and role escalation.
3. Fabricated or provenance-stripped evidence.
4. Prompt injection and unsafe server retrieval.
5. Malicious screenplay/file processing.
6. Secret/token/signed-URL/raw-payload leakage.
7. Duplicate or unaudited governed actions.
8. Destructive deletion without recoverability/attribution.

## Session boundary

The browser holds an opaque revocable application session in a `__Host-` Secure HttpOnly SameSite cookie. State-changing requests require a session-bound CSRF token and validated Origin. Session rotation follows sign-in, reauthentication, recovery, and privilege-sensitive account changes. No long-lived API bearer token is stored in browser storage.

## Authorization

- Identity providers establish identity only.
- PostgreSQL membership/project grants are authoritative.
- Every repository query takes ownership scope explicitly.
- Counts, search suggestions, activity, notifications, exports, and direct links use the same authorized set.
- Cache keys include identity, org/project, membership version, and capability/policy version; deactivation invalidates immediately.

## Upload and parser controls

One-time upload capabilities bind org, project, actor, object key, max bytes, allowed type, expected hash, nonce, expiry, and object generation. Server finalization verifies bytes, not client claims.

- FDX: disable DTD/entities/XInclude/network/schema retrieval; cap depth/nodes/text.
- PDF: isolated non-networked worker, CPU/memory/page/time caps; ignore embedded actions/scripts/links/forms/attachments.
- Fountain/paste: encoding/size limits and deterministic normalization.
- All: MIME/magic/extension checks, malware/content scan where approved, stored-byte hash, and safe filenames.

## Provider and content safety

Parallel/Gemini calls use least data necessary. Search receives a bounded objective and two or three queries, not a full screenplay; Extract receives at most three canonical HTTPS URLs returned by the same scoped Search run and never requests full content. Prompts fence screenplay/web/provider content as untrusted. Tool targets are server-derived/allowlisted; locally followed URLs and redirects pass scheme, DNS/IP, redirect, and response-size SSRF controls. Raw payloads live only in protected storage when necessary and never cross ordinary API/UI contracts.

Conditional Parallel Monitor webhooks are verified over the exact body using the versioned HMAC-SHA256 signature, webhook ID, and timestamp before JSON parsing or durable dispatch. Timestamp tolerance, constant-time comparison, secret rotation, webhook-ID replay protection, monitor/event-group scope lookup, delayed/out-of-order delivery, and duplicate idempotency are mandatory. Provider metadata never establishes organization/project authorization.

## Logging and observability

Structured logs/traces include request/run/correlation IDs, safe types, timing, status, and costs. They exclude credentials, session/CSRF/invitation/recovery tokens, signed URLs, full script/source bodies, attributable excerpts unless explicitly bounded, and hidden reasoning. Redaction tests use seeded secret canaries.

## Deletion and recovery

Only an Owner with recent reauthentication and typed confirmation may schedule whole-project/organization deletion. Grace is 30 days and reversible. Final purge is idempotent, produces a tombstone/audit record, removes signed access and sensitive artifacts, and reports lost reproducibility honestly.

## Required test classes

Cross-tenant matrices; unknown/unauthorized parity; CSRF/origin/session fixation/revocation; invitation replay/wrong account; project-grant changes; upload replay and object swap; XML/PDF bombs; SSRF redirects/DNS rebinding; prompt injection; raw-payload/secret leak scans; idempotency/concurrency; audit atomicity; deletion grace/restore/purge.

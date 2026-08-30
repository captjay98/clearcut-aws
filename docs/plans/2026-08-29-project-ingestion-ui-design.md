# Project Creation & Ingestion UI Design

**Date:** 2026-08-29
**Status:** Approved
**Surface:** `#new`
**Depends on reviewed surfaces:** `#trust`, `#records`, `#team`, `#settings`, `#auth`, `#onboarding`, `#invite`, `#projects`

## Purpose

This design establishes the project-creation, script-import, parsing, upload-security, immutable-versioning, and initial-analysis behavior for ClearCut's `#new` surface. It determines the durable boundaries between Project, Script, ScriptVersion, ImportArtifact, ParseRun, UploadIntent, AnalysisRun, DetectionRun, and ResearchRun before those contracts are frozen.

The mock at `misc/clearcut-flow/` remains the visual and interaction source of truth. Its three-step details → import → check flow is the production information architecture. This document does not authorize mock implementation changes.

## Approved decisions

1. Project is created durably after Step 1; ScriptVersion is created only after successful parsing and explicit user confirmation.
2. "Start checking" is an explicit human trigger after v1 is confirmed. Detection runs first; Parallel research fans out per detected item afterward.
3. PDF parsing is provider-dependent (Gemini for scanned/complex pages) with per-page confidence, model warnings, and user confirmation before v1 is committed.
4. Upload security uses layered client-then-server validation: extension/MIME/size hints on the client; pinned object generation, server-computed byte hash, magic-byte/type validation, parser hardening, resource limits, and replay checks on the server.
5. Accepted file extensions: `.fountain`, `.spmd`, `.txt` (Fountain parser), `.fdx` (Final Draft XML parser), `.pdf` (PDF parser). Paste uses Fountain-style inference.
6. Re-import creates a new version; no version is ever replaced or deleted. The version model is append-only with immutable lineage.
7. Cancellation preserves eligible completed immutable outputs. Continuation creates a predecessor-linked AnalysisRun, reuses only succeeded outputs with matching version/policy fingerprints, and reruns incomplete or mismatched work.
8. The frontend polls the durable AnalysisRun status endpoint. Updates are focus-stable, reload-safe, and announced through live regions.

## Three-step flow

Step availability is derived from real project state:

- Step 1 (Describe the production): always available for the active project.
- Step 2 (Bring in the script): available after project details are saved.
- Step 3 (Check the script): available after v1 is confirmed.

## Project creation (Step 1)

Owner and Admin only. The "New project" button is capability-gated; Editor, Reviewer, and Viewer see a focusable control with an explanation of the restriction.

Submitting production details creates a durable Project in one transaction:

- Project with immutable `project_id`, tenant-scoped to authenticated `org_id`.
- Stable project slug.
- Inherited ProjectMemberships for every active Owner and Admin.
- Monitoring cadence seeded from the organization default.
- Immutable project-created audit event.

The operation is idempotent. Retries return the existing project without duplicates.

After success, Step 2 unlocks with a real project-bound upload capability.

## Script import (Step 2)

### Accepted formats

| Extension | Parser | Deterministic |
|---|---|---|
| `.fountain`, `.spmd`, `.txt` | Fountain | Yes |
| `.fdx` | Final Draft XML | Yes |
| `.pdf` | PDF with optional Gemini | No (scanned pages) |
| Paste | Fountain-style inference | Yes |

Future format adapters (`.fadein`, `.celtx`, `.highland`) are possible through the parser port but out of initial scope.

### Upload flow (file imports)

1. Client validates extension against the allowlist, MIME type, and file size (configurable, default 50 MB maximum). Client checks are usability hints, never a security boundary.
2. Client requests a one-time signed upload capability bound to organization, project, actor, object key, content type, client-declared content hash, maximum size, and nonce.
3. Client uploads directly to object storage using the signed URL.
4. Client calls finalize with the idempotency key, expected object generation/version, and client-declared hash.
5. Server pins the immutable stored object generation, streams those exact bytes, recomputes the cryptographic hash itself, verifies object size and type/magic bytes, compares the computed hash with the capability and finalize declaration, and atomically consumes the one-time capability. Client metadata or object-store metadata alone never establishes integrity.
6. FDX is plain XML, not a ZIP container. Parsing disables DTDs, external/general/parameter entities, XInclude, schema/network retrieval, and any parser network access; it enforces document-size, element-count, nesting-depth, attribute, and text limits.
7. PDF parsing runs in an isolated, non-networked worker with page-count, decompressed-size, memory, CPU, and wall-clock limits. Encrypted PDFs require an explicit supported-password flow or are rejected. Embedded JavaScript, actions, launch/URI behavior, forms, portfolios, and attached files are ignored or rejected and never executed or extracted as trusted input.
8. Replaying finalize with the same idempotency key and the same pinned object generation returns the existing result. Replaying with different bytes, object generation, or metadata is rejected as a conflict and security event.
9. Successful finalization creates an ImportArtifact bound to the server-computed hash and immutable object generation, then queues a durable ParseRun.

### Paste flow

- Maximum 500K characters (configurable).
- Content goes directly to the API; no signed URL or object-storage upload.
- Same ParseRun, warning, and confirmation flow as file imports.

### Parsing

Fountain, FDX, and text-layer PDF parsing are deterministic. Scanned or complex PDF pages use Gemini File API through the model provider port with bounded retries and cost tracking.

A successful parse returns structured warnings at three severity levels:

- **Info:** formatting normalization, minor encoding fixes.
- **Warning:** ambiguous scene boundaries, unrecognized element types, low-confidence PDF page extractions.
- **Error:** missing required structure, unreadable pages, truncated content.

Any **Error** blocks v1 creation entirely; there is no organization-configurable threshold that can waive parser errors. The user must fix the source and re-import. Info and Warning results remain visible and require explicit confirmation before v1 is committed; confirmation accepts the recorded limitations but does not relabel them as successful validation.

- **Accept with warnings** → v1 is committed with warnings permanently attached.
- **Reject and re-import** → no version is created; the import artifact, parse results, and warnings are preserved for diagnosis.

### Version creation

Successful confirmation atomically writes:

- Script (if first import for this project).
- Immutable ScriptVersion with content hash, source format, parent version, and creation timestamp.
- ScriptElements and ElementSpans with stable identifiers for cross-version diffing.
- Parse warnings attached to the version.
- Import audit event.

Failed parsing creates no ScriptVersion. The ImportArtifact and ParseRun failure details are preserved.

### Re-import

Importing again after v1 exists creates a new version (v2, v3, etc.). No version is ever replaced, mutated, or deleted. Version lineage records the parent version and the import source (file re-import vs. approved rewrite). Selective re-scan applies to items affected by structural differences between versions.

## Analysis run (Step 3)

### Trigger

"Start checking" is an explicit human action after v1 is confirmed. It transactionally creates one idempotent parent AnalysisRun and outbox record. The idempotency key prevents duplicate runs from double-clicks or retries.

### Detection phase

A durable DetectionRun executes across all ten categories. Each detected item becomes a ClearanceItem with zero EvidenceClaims. Zero evidence is an unresolved state, not a clearance result. Detection must complete before research begins.

### Research phase

Per-item durable ResearchRuns fan out only after detection has produced item and query scope. Parallel must not start before detection completes. Each ResearchRun follows the approved durable lifecycle:

```text
queued → claimed → running → succeeded
                           ↘ retry_wait → running
                           ↘ failed → manual_retry
                           ↘ cancelled
```

Leases, unique idempotency keys, retry counters, and reconciliation prevent duplicate or stranded execution. Provider results distinguish retryable failure, permanent failure, rate limiting, authentication or configuration failure, and invalid response. Permanent failures and exhausted retries create visible review items. ClearCut never converts a failed research run into invented fallback evidence.

### Cancellation and continuation

- Cancellation immediately stops dispatching new detection or research tasks.
- Already-completed immutable detection and research outputs are preserved; in-flight attempts may finish or time out and record their terminal result.
- The AnalysisRun is marked `cancelled` with timestamp, actor, completed-output manifest, and predecessor-safe checkpoint.
- The user can see partial results, but incomplete detection or research remains unresolved.
- A later "Continue checking" creates a new AnalysisRun with its own idempotency key and `predecessor_run_id`; a cancelled run is never changed back to running.
- Detection output may be reused only when the predecessor DetectionRun reached `succeeded` for the same script version, category-schema version, detection prompt/model version, and policy inputs. Otherwise the continuation reruns full detection and reconciles stable item identities.
- Each reusable research result must be `succeeded` and match a deterministic fingerprint over organization/project, script version, stable item identity and normalized context, category, normalized query plan, provider, source-authority policy, prompt/model, and relevant policy versions.
- Missing, failed, cancelled, stale, or fingerprint-mismatched work receives a new ResearchRun. Reuse records immutable lineage rather than copying or mutating prior claims.
- Cancellation and continuation each write an authoritative audit event and Receipt projection.

### Progress and reconnection

The frontend polls the AnalysisRun status endpoint at a 3–5 second interval. Each response includes current run state, step completion, item counts, elapsed time, and any failures.

The three-card layout updates in place without stealing focus, scrolling to top, or re-announcing the route heading. A screen-reader live region announces meaningful transitions:

- "Detection complete — 10 items found."
- "Research in progress — 4 of 10 items."
- "Run complete — 38 sources across 10 items."
- "Run cancelled — 7 items preserved."

Page reload reconnects to the durable run and shows current progress. Navigating away and returning shows the run's real state.

## Untrusted-content and artifact boundary

Screenplay text, extracted PDF/XML content, filenames, parser messages, model output, and provider/source content are untrusted data. They are rendered as text through escaped components, never inserted as executable markup, and cannot alter prompts, tools, policy, permissions, routing, or approval state. Model-assisted PDF parsing receives an explicit data-only instruction boundary and its structured output is schema-validated before persistence.

Original files, diagnostic artifacts, and parse exports download from an isolated artifact origin or equivalent hardened response boundary with a pinned server-owned MIME type, `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`, restrictive CSP, short-lived authorization, and no ambient cross-tenant access. Uploaded filenames never control response headers or object keys.

## State completeness

| State | Behavior |
|---|---|
| Loading | Skeleton placeholders for project creation, upload progress bar, parse progress, run card updates |
| Empty | Locked-step explanatory cards; no-upload state; no-parse-result state |
| Recoverable error | Retry with preserved upload; re-run parse; manual-retry for failed tasks |
| Permanent error | Specific error per format: truncated or unsafe XML, unsupported encrypted/active-content PDF, unreadable PDF, size/resource limit exceeded, invalid magic bytes, object-generation mismatch, replay detected, provider unavailable |
| Success | Details saved, v1 confirmed with or without warnings, run complete with navigation to workspace and flags |
| Not found | Access-safe response for unknown project slug, organization slug, or upload session |

## Accessibility

- "New project" is capability-gated with `aria-disabled`, remains focusable, and is described by visible restriction text.
- Form validation uses `aria-invalid` and linked `aria-describedby` inline error messages, not toast-only feedback.
- Upload and parse controls expose `aria-busy` and prevent duplicate submission.
- Run progress updates are focus-stable. No full route re-render, no scroll-to-top, no repeated heading announcement during polling.
- Step indicators carry `aria-current="step"` or equivalent textual status.
- Import format tabs reach 44px minimum height on mobile breakpoints.
- Live regions announce: upload complete, parse warnings present, v1 confirmed, detection complete with item count, research progress, run complete, and cancellation with preserved count.
- Keyboard operation covers all controls including format tabs, upload, confirmation, start/cancel, and post-run navigation.

## Responsive and theme behavior

- 1440px: full sidebar, narrow page wrapper, three run cards side by side.
- 900px: two-column run cards, sidebar becomes drawer.
- 700px: single-column layout, form grids stack, bottom navigation, 44px minimum controls.
- 375px/320px: import tabs scroll horizontally, prerequisite banners stack action below copy.
- Script (light) and Night shoot (dark) themes maintain equivalent contrast, states, and hierarchy across all breakpoints.
- Reduced-motion settings are honored for all transitions and progress animations.

## Required mock corrections

1. Gate "New project" to Owner/Admin with a `create` capability and add it to `ACTION_CAPABILITY`.
2. Replace seeded-project selection with a real project-creation action and "Project created" receipt.
3. Add file input and drop target for Fountain/FDX/PDF modes with client-side extension, MIME, and size validation.
4. Remove the premature "Validated" badge; show validation status only after server verification.
5. Make receipts format-specific: Fountain and PDF modes must not claim an FDX filename.
6. Add a parse-warnings confirmation step between "parse complete" and "v1 committed."
7. Replace the single static FDX truncation error with per-format error dialogs.
8. Separate detection and research into sequential phases with independent status cards.
9. Replace focus-stealing full re-renders during the run with in-place status updates.
10. Add `aria-current="step"`, `aria-invalid`, `aria-busy`, and operation-specific live announcements.
11. Ensure all import tabs and controls reach 44px minimum height at mobile breakpoints.
12. Stack the prerequisite banner action below copy at narrow widths.

No mock implementation changes are authorized by this document alone.

## Domain entities established

This design establishes the need for, without fixing final table or column names:

- Project (with stable slug, tenant-scoped to `org_id`)
- Script (per-project, created on first successful import)
- ScriptVersion (immutable, append-only, with parent lineage, content hash, source format, and attached warnings)
- ImportArtifact (preserves the original uploaded or pasted content)
- ParseRun (with structured warning model and provider-dependency flag)
- ScriptElement and ElementSpan (stable identifiers for cross-version diffing)
- UploadIntent / UploadCapability (one-time, bound to org/project/actor/key/hash/size/type/nonce)
- AnalysisRun (parent, idempotent, with cancellation and resumption semantics)
- DetectionRun (across ten categories, produces ClearanceItems)
- ClearanceItem (zero claims = unresolved, not clear)
- ResearchRun (per-item, fans out after detection, follows durable lifecycle)
- ResearchQuery and EvidenceClaim (linked to Parallel provenance)

## Architecture gate

This approval, combined with the identity-entry and team/settings designs, permits preliminary schema and API design for:

- Project, Script, ScriptVersion, ImportArtifact, ParseRun, ScriptElement, ElementSpan.
- UploadIntent and one-time capability lifecycle.
- AnalysisRun, DetectionRun, ResearchRun, and durable task outbox.
- ClearanceItem with zero-evidence unresolved semantics.

Do not freeze the following until their surface reviews are approved:

- Evidence-decision, referral, disposition, and rewrite-approval schema → requires `#project`, `#workspace`, `#items`, `#item` review.
- Revision diffing, selective re-scan, and monitoring schema → requires `#versions`, `#watch` review.
- Report generation, release, and export schema → requires `#report` review.
- Notification types and delivery → requires `#notifications` review.

## Remaining review order

1. `#project`, `#workspace`, `#items`, `#item` — analysis, evidence, provenance, filtering, assignments, and governed evidence actions.
2. `#versions`, `#watch`, `#report` — revision lineage, selective re-scan, monitoring, version-bound dossier, release, and export.
3. `#notifications` — event types and destinations.
4. `#marketing`, `#sitemap`, `#states` — public and prototype-only surfaces.

## Verification expectations

When implementation targets exist, verify:

- Owner/Admin-only project creation with inherited memberships.
- Idempotent project creation with stable slug.
- Client and server upload validation for each accepted format.
- one-time upload capability consumption, immutable object-generation pinning, server-side byte-hash recomputation, and replay rejection.
- FDX DTD/entity/XInclude/network disablement plus size/depth/count limits, and isolated PDF resource/active-content/encryption handling.
- Deterministic Fountain, FDX, and text-PDF parsing.
- Provider-dependent PDF parsing with per-page confidence.
- Parse warning presentation and user accept/reject flow.
- Successful v1 creation with stable element and span identifiers.
- Failed parse creates no ScriptVersion.
- Re-import creates a new version without mutating previous versions.
- Explicit "Start checking" creates one idempotent AnalysisRun.
- Detection completes before research fans out.
- Zero-evidence ClearanceItems are unresolved, not clear.
- Durable task lifecycle including leases, retries, and reconciliation.
- cancellation preserves only eligible completed immutable results; predecessor-linked continuation reruns incomplete detection and fingerprint-mismatched research.
- untrusted-content escaping, prompt-injection isolation, schema validation, and hardened attachment downloads.
- Poll-based progress with focus-stable updates and live announcements.
- Per-operation loading, empty, recoverable, permanent, success, and not-found states.
- Linked form errors with `aria-invalid` and `aria-describedby`.
- 44px import tabs on mobile.
- Both themes across 320–1440px.
- Same-transaction audit for project creation, v1 commit, and run creation.

# Testing Guidelines

## Commands (when the target exists)

- Unit (Python): `pytest services/api/`
- Unit (TypeScript): `pnpm test`
- Integration: `pytest services/api/ -m integration`
- E2E: `pnpm test:e2e`
- Mock audit: `node misc/clearcut-flow/mockup-audit.mjs` (366 checks)
- Lint/format: `ruff check . && ruff format --check .` and `pnpm lint && pnpm format:check`
- Type check: `pyright && pnpm typecheck`
- Contract drift (when configured): `pnpm --filter contracts generate && git diff --exit-code packages/contracts/`

The repository is currently pre-implementation, so do not claim absent test suites or runtime directories have run.

## Coverage Targets

- Evidence chain (provenance, authority, conflicts): 90%+
- Governed actions (decisions, receipts, audit): 85%+
- Parser suites (Fountain, FDX, PDF, paste): 80%+
- API endpoints: 75%+
- UI components: 60%+

## Priorities

1. Evidence integrity: provenance, authority, conflicts, confidence, and zero-evidence states.
2. Governed action boundaries and same-transaction audit.
3. Parser correctness and stable identities across revisions.
4. Ownership-aware tenant isolation: organization-owned queries use `org_id`; project-owned queries use `org_id` + `project_id`; explicitly global catalogs are limited to role/capability definitions, the ten category schema, and platform source-authority defaults. Organization policy/prompt/preference/retention/privacy versions remain `org_id`-scoped.
5. Judge and bounded-learning gates.
6. Selective affected-item re-scan.
7. Durable jobs, idempotency, retries, leases, and reconciliation.

## Evidence Test Contract

Detection tests must cover a `ClearanceItem` with zero claims for pending, no-result, unavailable, and provider-failure states; these are unresolved, not clear. Evidence tests must reject any `EvidenceClaim` without a recorded Parallel `SourceSnapshot` containing URL, retrieval time, attributable excerpt, publisher/authority classification, stance, query/run identity, and provenance. The category schema and source-authority policy are separate protected policies; do not infer one from the other.

## Deterministic Test Suites (from baseline §14.1)

- Four parser suites and stable element/span identity across revisions.
- Selective affected-item re-scan.
- Ten category schemas and representative cases.
- Evidence, source, conflict, confidence, citation, and provenance normalization.
- Organization, project, global-catalog, role, and tenant isolation.
- Invitation/membership lifecycle and approval/disposition state machines.
- Monitoring cadence/deduplication and durable job behavior.
- Dossier reproducibility and shared provider contract tests for GCS/R2.

## Evaluation Corpus (from baseline §14.2)

Include positive/negative, ambiguous/overlapping, conflicting/missing/stale/low-authority, and prompt-injection cases. Recorded Parallel Search/Extract/Monitor responses may be used in integration tests, but each fixture must retain real capture metadata and provenance: provider capability/IDs/session, source URL, retrieval timestamp, publisher/authority classification, stance, excerpt, query identity, and provider/tool receipt. Cover Search empty versus failure; Extract full/partial/total outcomes and URL authorization; and, when enabled, Monitor signature/replay/scope/dedupe/re-verification. Do not replace Parallel with an uncited fake response or assert invented evidence. Also cover unsupported legal certainty, safe/unsafe rewrites, revision impact, and monitoring changes that should or should not open review.

## E2E and Security

E2E covers org creation, all five invitation states, role enforcement, all import paths, detection, mandatory Parallel Search, bounded Extract outcomes, evidence review, rewrite, selective re-scan, scheduled monitoring, conditional Monitor signal verification when enabled, and export. Accessibility covers keyboard navigation, focus management, dialogs, responsive layouts, and landmarks. Security covers session rotation/revocation, CSRF and Origin enforcement, role escalation, cross-tenant and unknown-versus-unauthorized access, upload replay and pinned-byte hashing, malicious XML/PDF, source/provider prompt injection, SSRF boundaries, Extract URL authorization, Monitor webhook verification/replay when enabled, expired URLs, secret leakage, redaction, and audit/Receipt completeness.

## Anti-patterns

- Test behavior and contracts, not implementation details.
- Do not fabricate evidence or treat zero evidence as a clear result.
- Do not test the mock prototype's JavaScript; its structural audit is the check.
- Do not chase 100% coverage at the expense of the evidence and governance priorities.

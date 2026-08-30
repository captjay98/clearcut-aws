# ClearCut API Contract Rules

**Canonical artifact:** `packages/contracts/openapi.yaml` once Plan 01 creates it  
**Clients:** generated TypeScript and Python; generated output is never hand-edited

## URL and scope

Production browser routes use stable organization slugs and immutable resource IDs. API routes use immutable IDs:

```text
/api/v1/organizations/{org_id}/projects/{project_id}/...
```

Organization-owned endpoints require `org_id`; project-owned endpoints require both. Repository/service signatures make scope mandatory and derive actor/capability from the opaque session.

## Response and error envelopes

```json
{
  "data": {},
  "meta": {"requestId": "...", "nextCursor": null}
}
```

```json
{
  "error": {
    "code": "research_provider_unavailable",
    "message": "Source research is temporarily unavailable.",
    "requestId": "...",
    "retryable": true,
    "details": []
  }
}
```

The closed error-code catalog covers validation, authentication, authorization, not-found, conflict/stale version, rate limit, provider/model typed failures, rejected output, unavailable service, and internal failure. Unknown and unauthorized project-owned IDs share the same safe response/timing class.

## Mutation rules

- JSON edge casing is camelCase; Python/domain/database casing remains native.
- Every retryable mutation accepts `Idempotency-Key` and returns the existing result for the same intent.
- Governed mutations require rationale, expected version, and intent hash.
- Long-running commands return `202` with a run/job resource; status polling is mandatory, SSE optional.
- `DELETE` does not remove core evidence directly; it schedules the approved deletion lifecycle.
- ETags/expected versions protect concurrent human decisions.

## Canonical durable status

All backend run/job contracts use this closed vocabulary:

```text
queued -> claimed -> running -> succeeded
                    |          -> retry_wait -> running
                    |          -> failed -> manual_retry -> queued
                    `----------> cancelled
```

`succeeded` is the stored/API terminal value. UI copy may render it as “Completed,” but `completed` is not a second API value. `manual_retry` means the failed job is eligible for an accountable retry command; a retry creates a new attempt and returns the job to `queued` without rewriting the failed attempt.

## Semantic operations

Operations use intent-revealing IDs rather than generic status updates. The required operation inventory, authorization class, idempotency behavior, and errors are frozen in `docs/API_OPERATIONS.md`. Examples include `recordEvidenceDecision`, `proposeRewrite`, `approveRewrite`, `reviewMonitoringChange`, `generateReportSnapshot`, and `releaseReport`.

## Pagination and filtering

Cursor pagination only for mutable chronologies. Stable sort keys include timestamp plus immutable ID. Filters are typed enums/ranges, authorization is applied before counts, and invalid filters return validation errors rather than broadening scope.

## Contract-first sequence

1. Add/modify schema and examples.
2. Run spectral/schema validation.
3. Regenerate clients.
4. Confirm generated diff.
5. Implement FastAPI behavior against the contract.
6. Run export/drift tests.
7. Add consumer tests in web and worker code.

Planned checks after Plan 01 selects tools:

```bash
pnpm contract:lint
pnpm contract:generate
pnpm contract:check
```

Expected: all exit 0 and `git diff --exit-code -- packages/contracts` after generation.

## Initial endpoint groups

Sessions/auth; organizations/memberships/invitations; projects; upload capabilities/imports/versions; analysis/detection/research/runs; items/evidence/decisions/referrals/rewrites/comments/assignments; monitoring; notifications; evaluations/learning/policies; Records; report snapshots/releases/artifacts.

`docs/API_OPERATIONS.md` owns the semantic operation inventory. Granular implementation packets own exact schema creation and tests; they may add support reads without replacing declared intents with generic CRUD.

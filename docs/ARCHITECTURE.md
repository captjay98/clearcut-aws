# ClearCut Architecture

**Status:** implementation baseline  
**Style:** OpenAPI-first modular monolith with three deployable web/API images

## System context

```text
Browser
  -> clearcut-site (Astro public pages)
  -> clearcut-web  (TanStack Start workspace, same-origin /api boundary)
       -> clearcut-api (FastAPI modular monolith + Google ADK runtime)
            -> Cloud SQL PostgreSQL
            -> Cloud Storage
            -> Cloud Tasks / Scheduler
            -> Gemini through Google ADK
            -> Parallel Search + bounded Extract APIs
            -> conditional Parallel Monitor event-stream signals
            -> Secret Manager / configured identity and email adapters
```

Separate deployability does not mean backend microservices. One API image owns bounded modules and one transactional database while preserving module storage boundaries.

## Planned workspace

```text
apps/site/                  # Astro
apps/web/                   # TanStack Start
services/api/src/clearcut/  # FastAPI modular monolith
packages/contracts/openapi.yaml
packages/contracts/schemas/
packages/contracts/generated/typescript/
packages/contracts/generated/python/
packages/design-system/     # mock-derived components/tokens
packages/config/            # shared TS/build/lint config
infra/gcp/
demo/
```

These paths are targets, not current runtime inventory.

## Backend modules

| Module | Owns | May depend on |
|---|---|---|
| identity | users, credentials/subjects, sessions, security events | shared kernel, provider port |
| organizations | organizations, memberships, invitations, project grants | identity IDs, audit application port |
| projects | projects and project preferences | organization authorization port |
| scripts | artifacts, versions, elements, spans, parse runs | projects, object-storage port |
| detection | analysis/detection runs and candidate items | scripts read port, model port |
| research | queries, source snapshots, claims, conflicts, confidence | item read port, Parallel port |
| decisions | evidence/disposition decisions, referrals, rewrites | item/evidence read ports, audit UoW |
| collaboration | assignments, comments, mentions, notifications | project membership port, event handlers |
| monitoring | policies, runs, changes, review work | research snapshot port, scheduler/task ports |
| evaluation | gates, verdicts, rubric/prompt/policy bindings, learning | run projections, model port |
| export | report snapshots, releases, artifacts | version-bound read projections, storage port |
| records | authorized/redacted projections of audit, runs, operations | module projection ports only |

Modules do not import another module's ORM models or query its tables. Integration uses typed application ports or versioned events.

## Layer rules

```text
domain <- application <- adapters <- delivery
```

- Domain code has no FastAPI, SQLAlchemy, provider SDK, UI, environment, clock, or random-ID dependency.
- Application services receive `Clock`, `IdentifierGenerator`, authorization, provider, task, storage, and unit-of-work ports.
- Adapters translate third-party data into typed domain results/errors.
- Delivery layers authenticate, validate, call one application service, and serialize the declared contract.

## Durable work

Analysis, detection, research, evaluation, re-scan, monitoring, learning checks, report generation, email, and notifications use an outbox-backed run model:

```text
queued -> claimed -> running -> succeeded
                    |          -> retry_wait -> running
                    |          -> failed -> manual_retry
                    `----------> cancelled
```

Each job has organization/project scope, type, input version, idempotency key, attempt, lease owner/expiry, predecessor, checkpoint, terminal result/error, and correlation IDs. Dispatch and domain state are committed together; reconciliation repairs stranded dispatch.

## Provider ports

```python
type ProviderResult[T] = ProviderSuccess[T] | ProviderFailure

class ProviderFailure(BaseModel):
    kind: Literal[
        "retryable", "rate_limited", "authentication", "configuration",
        "invalid_response", "permanent", "ambiguous"
    ]
    safe_message: str
    provider_receipt_id: str | None = None
```

No boolean, `None`, raw dictionary, unrestricted provider payload, or provider exception crosses a module boundary. `ambiguous` outcomes require reconciliation by operation/query identity.

## Open-source adapter boundary

Provider and infrastructure SDKs are registered explicitly in the composition root behind versioned typed ports. The submitted profile registers `GeminiAdkRuntime` as the only model runtime and the official Parallel implementations of `WebSearchPort` and `UrlExtractPort`; `WebMonitorPort` is bound to Parallel only after its recorded go/no-go. It contains no alternate AI/search adapter or silent fallback. Search remains mandatory even when Extract or Monitor is enabled. See `docs/PARALLEL_INTEGRATION.md`.

Identity, object storage, task dispatch, email, report rendering, and telemetry adapters may be replaced when they pass the public conformance suite. Adapters never receive direct module-table access and cannot change protected policy, authorization, evidence provenance, governance, audit, retention, or legal-boundary rules. See `docs/EXTENSIONS.md`.

## Database and object-storage consistency

PostgreSQL and object storage are not treated as one atomic transaction. Artifact workflows use a staged protocol:

1. Commit the authorized command, job, audit event when governed, and outbox message in PostgreSQL.
2. Render and upload to an immutable temporary/versioned object with generation and hash preconditions.
3. Commit the authoritative snapshot/object pointer and terminal job result in PostgreSQL.
4. Publish or release only from the committed snapshot.
5. Reconcile orphan objects and stranded jobs idempotently.

## Deployment invariants

- Browser session/API traffic is same-origin.
- Service-to-service task endpoints are private and authenticated.
- Images are built once and promoted by immutable digest.
- Migrations are a separate gated job, never an application-start side effect.
- Cloud Run service identities are distinct and least-privileged.
- Environment configuration selects adapters; it does not change domain behavior.

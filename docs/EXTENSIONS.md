# ClearCut Extension Policy

ClearCut is open source and adapter-oriented. Extension points keep provider and infrastructure SDKs outside domain logic, make profiles testable, and support deliberate future integrations without changing evidence or governance rules.

## Submitted runtime profile

The Agentic Cinema release permits exactly one AI provider and one research partner:

```text
AI runtime:           Gemini through Google ADK
Research discovery:  Parallel Search API (mandatory when research runs)
Research enrichment: Parallel Extract API (bounded)
Research watch:      Parallel Monitor event_stream (conditional go/no-go)
```

Gemini and Parallel are disabled by default. Enabling either requires explicit cost acknowledgement, a positive concurrency limit, credentials, and authorized quota. Parallel Task, FindAll, Responses/Chat, Interactions, Deep Research, snapshot Monitor, alternate research providers, and silent fallback evidence are excluded. Deterministic fakes are test-only and fail startup in a production profile. `docs/PARALLEL_INTEGRATION.md` owns the capability contract and Monitor decision.

## Public extension surface

Adapters implement core-owned typed ports and register explicitly at the composition root. They do not import another module's storage, modify protected policy, or bypass application services.

Implemented extension categories include:

- identity through built-in opaque sessions; Firebase remains an optional but currently unwired runtime boundary;
- object storage through filesystem, GCS, and S3-compatible adapters;
- task dispatch through local and Cloud Tasks adapters; Portable PostgreSQL dispatch remains deferred;
- secret resolution through local configuration and Secret Manager references;
- email, report rendering, and telemetry ports;
- typed model and research ports, contest-locked to Gemini/ADK and Parallel.

Local, Portable Server, and GCP Starter select approved adapters through validated configuration while using the same `clearcut` image. Adapter selection cannot change domain semantics.

## Non-negotiable invariants

An adapter cannot change tenant scope, evidence provenance, authority policy, protected categories, governed-action rules, audit atomicity, retention/privacy, or legal-boundary language. Provider failure is visible and typed; it never creates fallback evidence. Paid-provider adapters must acquire their configured runtime gate before client resolution or a paid call.

## Contributor artifacts

- `services/api/src/clearcut/` — bounded modules, typed ports, adapters, delivery, and composition.
- `services/api/tests/` — adapter, bootstrap, module, and conformance coverage.
- `packages/contracts/` — OpenAPI source and generated-client contract.
- `docs/compatibility/` and contributing guidance — supported boundaries as they are published.
- `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, and `LICENSE` — project governance.

The architectural rationale is in `docs/plans/2026-08-30-open-source-extension-architecture-design.md`; the deployment decision is in ADR 0004.

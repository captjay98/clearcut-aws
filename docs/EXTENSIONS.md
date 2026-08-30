# ClearCut Extension Policy

ClearCut is open source and adapter-oriented. Extension points exist to keep provider and infrastructure SDKs outside domain logic, make deployments testable, and allow deliberate future integrations.

## Submitted runtime profile

The Agentic Cinema release supports exactly one AI provider and one research partner:

```text
AI runtime:           Gemini through Google ADK
Research discovery:  Parallel Search API (mandatory)
Research enrichment: Parallel Extract API (bounded)
Research watch:      Parallel Monitor event_stream (conditional go/no-go)
```

No other AI model, agent framework, AI API, research provider, or silent fallback belongs in the submitted source, dependency graph, deployment configuration, or demo. Parallel Task, FindAll, Responses/Chat, Interactions, Deep Research, and snapshot Monitor are excluded. Deterministic fakes are test-only and fail startup when selected in a production profile. `docs/PARALLEL_INTEGRATION.md` owns the capability contract and Monitor go/no-go rule.

## Public extension surface

Adapters implement core-owned typed ports and register explicitly at the composition root. They do not import another module's storage, modify protected policy, or bypass application services.

Supported initial extension categories are identity, storage, task dispatch, email, report rendering, and telemetry. Model/research interfaces are public for architectural clarity but contest-locked to Gemini/ADK and Parallel until after the submission.

## Non-negotiable invariants

An adapter cannot change tenant scope, evidence provenance, authority policy, protected categories, governed-action rules, audit atomicity, retention/privacy, or legal-boundary language. Provider failure is visible and typed; it never creates fallback evidence.

## Planned contributor artifacts

- `services/api/src/clearcut/shared/ports/` — stable protocols and typed results.
- `services/api/src/clearcut/bootstrap/adapter_registry.py` — explicit registration.
- `services/api/tests/conformance/` — reusable adapter suites.
- `docs/contributing/adapters.md` — author guide.
- `docs/compatibility/adapters.md` — supported contract versions.
- `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, and root license.

The approved architectural rationale is in `docs/plans/2026-08-30-open-source-extension-architecture-design.md`.

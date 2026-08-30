# Open-Source Extension Architecture Design

**Date:** 2026-08-30  
**Status:** Approved  
**Decision owner:** Project owner

## Purpose

ClearCut is an open-source screenplay pre-clearance evidence workspace, not a disposable contest prototype. Its domain, governance, provenance, and tenant-isolation rules must remain stable while deployments can replace infrastructure adapters and, after the Agentic Cinema submission, add independently maintained integrations.

The submitted Agentic Cinema release remains intentionally specific: Gemini through Google ADK is the only AI runtime, and Parallel is the only research partner. Search is mandatory, Extract is bounded enrichment, and Monitor event-stream support is conditional after a recorded go/no-go. Extensibility must make the system maintainable without weakening the demonstrated Google Cloud and Parallel integration.

## Considered approaches

### 1. Direct SDK integration throughout modules

This is fast initially but couples domain behavior to provider SDKs, makes local testing difficult, and encourages raw provider responses to cross module boundaries. Rejected.

### 2. Arbitrary in-process plugin loader

This maximizes apparent flexibility but introduces supply-chain execution, lifecycle, migration, compatibility, and tenant-isolation risks before the core product is stable. Rejected for the initial release.

### 3. Typed ports with explicit adapter registration

Domain and application modules depend on small typed ports. The composition root registers approved adapters from server configuration. Each adapter publishes a capability manifest and passes a conformance suite. This is the approved approach.

Out-of-process adapters may be added after the contest through the same contracts where latency and transactional boundaries permit. They do not gain direct database access.

## Contest profile

```text
ModelRuntimePort
└── GeminiAdkRuntime          # only submitted implementation

WebSearchPort
└── ParallelSearchAdapter     # required submitted implementation

UrlExtractPort
└── ParallelExtractAdapter    # bounded submitted implementation

WebMonitorPort
└── ParallelMonitorAdapter    # conditional submitted implementation
```

The submitted source and deployment profile must not include another AI model, agent framework, AI API, research fallback, or provider selector. Tests may use deterministic fakes that cannot be selected in production. Sample/cached evidence is never a runtime fallback.

The public documentation may state that the interfaces are extension points, but any non-Google AI or non-Parallel research implementation is post-contest work outside the submitted release.

## Extension categories

| Port | Initial adapter | Extension posture |
|---|---|---|
| `ModelRuntimePort` | Gemini/Google ADK | Contest-locked; future adapter requires a separate compatibility and policy review |
| `WebSearchPort` | Parallel Search | Contest-locked and mandatory; no discovery fallback |
| `UrlExtractPort` | Parallel Extract | Contest-locked and bounded to Search-authorized URLs |
| `WebMonitorPort` | Parallel Monitor event stream | Conditional go/no-go; no Task/snapshot Monitor |
| `IdentityProviderPort` | Local PostgreSQL or Firebase, one per deployment | Replaceable through one normalized identity contract |
| `ObjectStoragePort` | GCS; local test adapter | Replaceable; must preserve generation/hash/precondition semantics |
| `TaskDispatcherPort` | Cloud Tasks; in-memory test adapter | Replaceable; must preserve lease, idempotency, retry, and reconciliation semantics |
| `EmailDeliveryPort` | deployment-selected adapter or explicit disabled mode | Replaceable; delivery outcome remains typed and recorded |
| `PdfExtractionPort` | isolated Gemini-backed worker | Replaceable only if the contest and security profile allow it |
| `ReportRendererPort` | deterministic HTML/PDF renderer | Replaceable only with reproducibility conformance proof |
| `TelemetrySinkPort` | OpenTelemetry | Replaceable; redaction contract is invariant |

## Stable core versus extension surface

Extensions may implement transport and provider behavior. They may not redefine:

- fixed roles or capability evaluation;
- organization/project ownership rules;
- the ten protected categories;
- source-authority tiers or evidence-claim requirements;
- deterministic blockers;
- governed-action and maker/checker rules;
- audit atomicity;
- retention/privacy or legal-boundary language;
- report binding and release semantics.

Those are protected core contracts. A manifest that requests a protected capability is rejected during startup validation.

## Adapter contract

Every adapter declares a manifest similar to:

```python
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class AdapterManifest:
    adapter_id: str
    contract: str
    contract_version: str
    implementation_version: str
    execution: Literal["in_process", "out_of_process"]
    capabilities: frozenset[str]
```

Registration is explicit in the API composition root. Domain modules never discover packages, import entry points, or read environment variables.

Adapters return declared success or error variants. They do not return `None`, booleans, raw dictionaries, provider exceptions, unrestricted payloads, or authorization decisions.

## Compatibility and versioning

- Port contracts use semantic versions.
- Additive optional fields are minor changes; removed fields, changed meaning, or new required behavior are major changes.
- The core supports the current major contract version and a documented deprecation window only when a second version exists.
- Adapter conformance tests are published with the core repository.
- An adapter cannot start when its manifest, contract version, capabilities, or health check fails validation.
- Database migrations remain core-owned. Third-party adapters do not ship migrations against ClearCut-owned tables.

## Failure behavior

Unavailable, ambiguous, rate-limited, authentication, configuration, invalid-response, retryable, and permanent outcomes remain distinct. Ambiguous outcomes enter reconciliation. Exhausted or permanent provider failures create visible review work; they never become invented evidence or silent success.

An optional infrastructure adapter may be disabled only when the product has an explicit degraded mode. Gemini and Parallel Search cannot be disabled in the submitted hosted profile. Extract follows its documented enrichment gate, while Monitor may be absent only under the recorded no-go with scheduled Search/Extract monitoring retained.

## Security boundary

- Extensions receive least-privileged configuration and data.
- Secrets are resolved by the composition root and passed through typed configuration; manifests never expose secret values.
- Out-of-process adapters authenticate mutually and receive scoped requests.
- No extension receives arbitrary SQL access, raw sessions, hidden reasoning, or cross-project data.
- Logs and traces pass through core redaction before export.

## Open-source contributor experience

The repository will publish:

- port protocols and JSON/OpenAPI schemas;
- one first-party reference adapter per supported port;
- deterministic fake adapters for tests only;
- a conformance harness;
- an adapter author guide and compatibility matrix;
- security reporting and responsible-disclosure guidance;
- contribution, review, versioning, deprecation, and release policies;
- examples that never imply an unsupported adapter is part of the contest build.

## Acceptance

The design is accepted when implementation plans require:

1. Gemini/ADK and mandatory Parallel Search to be directly imported, configured, called, traced, and demonstrated; Extract/Monitor are claimed only when their exact deployed integrations are proven.
2. Domain/application tests to run against deterministic fakes without provider SDK imports.
3. First-party adapters to pass the same public conformance suites.
4. Startup to reject duplicate, incompatible, or protected-capability adapters.
5. The submission manifest to name the exact registered adapters and prove no prohibited AI runtime is loaded.

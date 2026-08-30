# Implementation-Agent Packet Index

**Status:** documentation-only execution design  
**Parent roadmap:** `docs/IMPLEMENTATION_PLAN.md`

These packets split the 12 roadmap slices into independently reviewable implementation units. Execute packets only after their dependencies and named decision/contract inputs pass. Packets sharing an OpenAPI schema or migration are sequential unless the owning packet has frozen the seam.

## Required execution protocol

Every packet follows this loop for each numbered task:

1. Read all listed governing inputs and confirm the exact files are unchanged from the packet assumptions.
2. Create the named failing test or contract assertion.
3. Run the exact narrow command and confirm the stated failure reason—not merely a non-zero exit.
4. Add the smallest implementation described by the packet.
5. Run the narrow command until it passes.
6. Run contract generation/drift, tenant/governance/provenance checks, and the packet gate.
7. Update documentation and `docs/reviews/<date>-<packet>-evidence.md` with command, output, SHA, tree status, residual risks, and explicit non-claims.
8. Commit only the packet files with the packet's declared commit message after user authorization.

An agent stops when a listed path has conflicting user changes, a governing input conflicts, a provider behavior is untyped, a migration is unsafe, or a hard invariant fails.

## Frozen workspace conventions

```text
OpenAPI:       packages/contracts/openapi.yaml
JSON schemas:  packages/contracts/schemas/
TS client:     packages/contracts/generated/typescript/
Python client: packages/contracts/generated/python/
Backend:       services/api/src/clearcut/<module>/
Backend tests: services/api/tests/<module>/
Web:           apps/web/src/
Site:          apps/site/src/
Infrastructure: infra/gcp/
```

Plan 01 creates root commands `pnpm contract:lint`, `pnpm contract:generate`, `pnpm contract:check`, `pnpm verify`, and the Python `uv` environment. Later packets may use them only after R1 records their passing behavior.

When a packet says “run” a listed backend test without repeating the shell command, use `uv run pytest <listed-test-paths> -q`. For web unit tests use `pnpm --filter @clearcut/web test -- <named-scope>`; for browser tests use `pnpm --filter @clearcut/web test:e2e -- <named-scope>`. The first run must fail because the named contract/module/behavior is absent, not because dependencies or configuration are broken.

## Packet graph

| Packet | Outcome | Depends on |
|---|---|---|
| 01a | pinned workspace/toolchain and open-source repository policy | none |
| 01b | OpenAPI/schema source, generated clients, drift checks | 01a |
| 01c | API/site/web shells, architecture gates, CI and contributor gates | 01b |
| 02a | identity and opaque sessions | 01c |
| 02b | organizations, projects, resolver | 02a |
| 02c | invitations, memberships, roles and grants | 02b |
| 02d | identity/entry/team UI states | 02c, 06a |
| 03a | staged upload/artifact storage | 02b |
| 03b | four parsers and immutable v1 | 03a |
| 03c | ingestion UI and analysis-run control | 03b, 06a |
| 04a | Gemini/ADK detection runtime and ten categories | 03b |
| 04b | deterministic gates and staged judge evaluation | 04a |
| 05a | mandatory Parallel Search runtime, query/snapshot provenance and live proof | 04a, 01b |
| 05b | bounded Parallel Extract enrichment and partial outcomes | 05a |
| 05c | claims, conflicts, authority, confidence and evidence evaluation | 05b, 04b |
| 06a | mock-derived tokens, primitives, adapter proof and UI test harness | 01c |
| 06b | Astro public site and TanStack application shell | 06a, 02a contract |
| 06c | cross-browser, accessibility, responsive, visual and performance gates | 06b |
| 07a | orthogonal item projections, search/filter/group/read API | 05c |
| 07b | assignment, evidence decision, referral and disposition commands | 07a, 02c |
| 07c | comments, mentions, event production | 07a, 02c |
| 07d | project/workspace/items/item UI | 07a–07c, 06c |
| 08a | rewrite proposal and maker/checker approval | 07b |
| 08b | immutable revision, diff/lineage and selective re-scan | 08a, 05c |
| 08c | Versions UI and cross-version navigation | 08b, 06c |
| 09a | scheduled Search/Extract watch and conditional Parallel Monitor runtime | 05c, 07b, 08b |
| 09b | monitoring materiality and governed review | 09a, 07b |
| 09c | notification taxonomy, recipient projection and delivery backend | 02c, 07c, 09b |
| 09d | Watch and Notifications UI | 09b–09c, 06c |
| 10a | authoritative audit/Receipt consistency and Records API/UI | 07b, 07c, 09b |
| 10b | Trust evaluation, protected configuration and bounded learning | 04b, 05c, 08b, 10a |
| 10c | Settings, retention and deletion lifecycle | 10a, 02c |
| 11a | governed report generation and staged immutable snapshot | 08b, 09b, 10b |
| 11b | release, deterministic rendering, download and supersession | 11a |
| 11c | report preview/release/print UI | 11b, 06c |
| 12a | GCP infrastructure, migration, deploy and recovery pipeline | 01c; integrates incrementally |
| 12b | hosted release gate, original demo, public repository and submission | all product packets, 12a |

## Packet file rule

Every file in this directory names exact create/modify/test targets. When a target already exists because an earlier packet chose a different but accepted structure, stop and update the packet through a reviewed documentation change; do not improvise a second pattern.

For compact `Files` lines, a path beginning with `domain/`, `application/`, `ports/`, `adapters/`, or `delivery/` resolves under the most recently named `services/api/src/clearcut/<module>/` root in that line. A test basename resolves beside the most recently named full test path. A route/page basename resolves beside the most recently named full app path. This deterministic shorthand does not permit choosing another directory.

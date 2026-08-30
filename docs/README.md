# ClearCut Documentation Map

**Current phase:** implementation-agent packets are defined; packet 01a may begin only after explicit owner authorization. No production application is implemented.

## Authority order

1. Official Agentic Cinema rules and published track requirements.
2. Accepted ADRs, versioned contracts, approval/evidence/security policies, and architecture invariants.
3. `feature-ledger.md` and its 47 feature commitments.
4. `product-plan.md`.
5. This implementation roadmap and the active-plan coverage matrix.
6. Numbered active plans.
7. Submission and demo material.

Stop implementation when two higher-authority sources conflict. Record the conflict; do not select the easier interpretation.

## Product and policy documents

- `ARCHITECTURE.md` — system boundaries, deployment shape, module ownership, and dependency rules.
- `DATA_MODEL.md` — aggregate ownership, required records, identity, tenancy, and immutable lineage.
- `WORKFLOWS.md` — end-to-end workflows and durable state machines.
- `APPROVAL_POLICY.md` — roles, capabilities, maker/checker rules, and governed writes.
- `EVIDENCE_POLICY.md` — Parallel provenance, uncertainty, conflicts, retention, and legal boundary.
- `PARALLEL_INTEGRATION.md` — submitted Parallel capability matrix, exact Search/Extract/Monitor contracts, limits, failures, and proof gates.
- `API_CONTRACT.md` — OpenAPI-first rules, envelopes, pagination, idempotency, and client generation.
- `API_OPERATIONS.md` — stable semantic operation IDs, paths, action classes, and ownership.
- `DATABASE.md` — physical ownership, constraints, indexes, and migration rules.
- `EVENTS.md` — domain events, outbox/inbox delivery, notifications, and audit separation.
- `SECURITY_AND_PRIVACY.md` — tenancy, sessions, uploads, untrusted content, redaction, and deletion.
- `UI_SURFACE_CONTRACT.md` — all 20 production-facing prototype surfaces and shared UI invariants.
- `UI_STATE_MATRIX.md` — route-level production state, access, responsive, and accessibility acceptance.
- `EXTENSIONS.md` — open-source adapter policy and contest-locked Gemini/Parallel profile.
- `COMPETITION_AND_JUDGING.md` — verified submission rules, scoring, evidence obligations, and open compliance risks.
- `DECISION_GAPS.md` — unresolved cross-document conflicts and the exact plan boundaries they block.

## Execution documents

- `IMPLEMENTATION_PLAN.md` — dependency graph, checkpoints, and plan sequence.
- `DELIVERY_PLAN.md` — dated critical path, freeze, contingency, and submission buffer.
- `plans/active/README.md` — plan operating rules and active-file index.
- `plans/active/FEATURE_COVERAGE.md` — 47-feature ownership and acceptance-evidence matrix.
- `plans/implementation/README.md` — executable 01a–12b packet graph and protocol.
- `SESSION_HANDOFF.md` — exact next action and stop conditions.
- `reviews/2026-08-30-ui-plan-to-mock-audit.md` — current UI-plan-to-prototype audit.

## Governing rule

Production behavior must be proven at the layer that owns it. A mock interaction is design evidence, a unit test is engineering evidence, a deployed trace is runtime evidence, and a released report is governed product evidence. None substitutes for another.

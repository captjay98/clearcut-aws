# Governance Surfaces Implementation Plan

**Goal:** Build the four capabilities whose surfaces exist in the canonical mock but whose backends were never implemented — protected configuration, notifications, trust/evaluation reads, and the learning-candidate lifecycle — plus the organization settings writes they depend on.

**Status of the ground truth:** the persistence layer is largely already there. Every one of these areas has migrated tables, and three of the four have typed domain models. What is missing is repositories, application services, HTTP routes, and in two cases a contract that matches the domain. This is less work than "build four features" implies, and more work than "wire up four endpoints".

**Date:** 2026-08-31. Submission deadline is 2026-09-09 14:00 Pacific, which is 9 days. Sequencing below is ordered by necessity, not by surface area.

---

## Phase 0 — Protected configuration writes (P0, blocking)

This is not a Trust-surface nicety. It is the reason a freshly onboarded organization cannot run ClearCut at all.

**Verified defect.** `protected_configurations` has **zero writers** anywhere in `services/api/src` — the only inserts are in tests. Meanwhile two runtime paths hard-fail unless exactly one active row exists per org:

- `detection/adapters/sql_candidate_repository.py:145-163` — selects `policy_version, prompt_version WHERE org_id = :org_id AND lifecycle = 'active'`, then `if len(rows) != 1: raise DetectionPersistenceError("Exactly one active organization policy and prompt binding is required.")`
- `research/adapters/sql_research_repository.py:920-940` — identical query and invariant, raising `ResearchPersistenceError`
- `main.py:222-240` — `_SqlActivePolicyGate.is_active()` gates selective rescan on the same row

Organization onboarding writes only `organizations` and `memberships` (`organizations/adapters/sql_repository.py:19,81,207`). So detection, research, and rescan are dead on arrival in any real deployment. This is very likely the same class of failure behind the "Check unavailable" report — worth confirming whether that surfaced the detection-runtime message or this one.

**Build:**

1. Migration `0036_protected_configuration_governance` (revises `0035_revision_selective_rescan`):
   - FKs `protected_configurations.org_id → organizations.id` and `activated_by → users.id ON DELETE RESTRICT` (both currently absent)
   - Partial unique index enforcing at most one `lifecycle='active'` per org, so the "exactly one" invariant lives in the database rather than only in two hand-rolled reader checks
   - `activated_at`, `superseded_by`, `validated_at` columns for the draft → validated → active → superseded lifecycle the domain enum already declares
   - Real `downgrade()`; use `op.batch_alter_table` (schema is asserted against SQLite in `tests/architecture/test_migrated_runtime_schema.py`, whose head assertion at line 53 needs updating)
2. Seed a default active configuration during organization bootstrap, inside the existing bootstrap transaction. Without this, Phase 0 fixes nothing for new orgs.
3. Backfill path for existing orgs that have none.
4. `evaluation/adapters/sql_configuration_repository.py` implementing a new `ports/configuration_repository.py` Protocol.
5. `evaluation/application/protected_configuration.py`: `draft`, `validate`, `activate` as governed commands through `execute_governed_command` (`commanding/template.py:130`), Owner-only via `has_capability(role, "governance:manage")`. Activation must supersede the prior active row and write the `AuditEvent` in the same transaction.
6. Routes for the two already-declared operations `validateProtectedConfiguration` / `activateProtectedConfiguration`, plus a `GET` list (the contract has no list operation — needs adding), replacing the `capability_unavailable` stubs at `evaluation/delivery/http.py:58-67`.

**Contract work:** add `ProtectedConfiguration` component schema; `status` is currently a free-form string while the domain has a closed `ConfigurationLifecycle` enum. Neither operation declares `Idempotency-Key` or `expectedVersion`, so as specified they are not wired for the command kernel — add both.

**Gate:** a new org can onboard, then run detection end to end. Add a regression test asserting detection does not fail with the policy-binding error on a fresh org.

---

## Phase 1 — Trust / evaluation reads

Highest judging value per unit of work, because the engine is already built and only the read path is missing.

**What exists:** `agent_evaluations`, `judge_verdicts`, `deterministic_gate_results`, `ai_judge_invocations`, `ai_provider_attempts` — all migrated, all project-scoped with composite FKs and correctness check constraints (`0007`, `0022`, `0024`). `evaluation/domain/rubric.py` has all ten `JudgeDimension` values and `DimensionStatus`. `SqlEvaluationRepository` (793 lines) already writes evaluations and verdicts transactionally and reads them back. `VertexJudgeAdapter` (513 lines) is a real Gemini judge with closed verdict parsing and no model fallback.

**What is missing:** every trust route returns `capability_unavailable` (`evaluation/delivery/http.py:27,36,47`). `judge_verdicts` has no HTTP reader at all. `deterministic_gate_results` is written by `detection/adapters/sql_candidate_repository.py:586` and **never read**.

**Build:**

1. Typed contract schemas. The contract currently declares `data: {type: object, additionalProperties: true}` for both trust operations, so the generated client returns `Record<string, unknown>` — an untyped bag in front of a fully typed domain. Add `TrustEvaluation`, `JudgeVerdict`, `JudgeDimensionScore`, `GateResult`, and `EvaluationProvenance` schemas, then regenerate the TypeScript client.
2. Read-side repository methods: list evaluations for a project (optionally filtered by `jobId`), fetch one with its verdicts and gate results joined.
3. `evaluation/application/read_evaluations.py` returning typed results, mapping `DimensionStatus` honestly — `incomplete` and `not_applicable` carry a null score by check constraint and must not render as zero.
4. Replace the two stub routes. Keep an honest unavailable state when no evaluation has been persisted, which is what the live `trust.tsx` already does.

**Invariant the mock states explicitly and the API must preserve:** the headline score is the *mean of the ten dimension scores*, never a separately stored number — "the headline now derives from these scores, so it cannot drift from the rows printed beneath it." Compute it from the verdicts on read; do not trust `agent_evaluations.headline_score` as an independent value. Likewise `EVAL_PROVENANCE` (rubric/prompt/policy/judge versions) must come from one source so the trust surface and a released report cannot cite different versions.

**Frontend:** rebuild `trust.tsx` against the mock's `renderTrust` (app.js:4091) — score ring, gates list, provenance card, ten-row rubric table with meters. Delete the four dead `features/trust/*` files.

---

## Phase 2 — Notifications

**What exists:** `notifications` table (`0016`), org-scoped and per-user with `recipient_id → users.id ON DELETE CASCADE` and index `(recipient_id, is_read, created_at)`. `collaboration/domain/notifications.py` has `NotificationTier` and a frozen `Notification`. All five operations are already in `openapi.yaml` (lines 2469-2630) and in the generated client.

**What is missing:** no SQL in `src/` touches the table, and there is no router — the live `notifications.tsx` calls an endpoint the server does not serve. `collaboration/application/recipient_projection.py` computes fan-out to active memberships but persists nothing.

**Three defects to fix on the way:**

1. **Field mismatch.** Contract says `body` / `read` / `link`; the table and domain say `body_redacted` / `is_read` / `destination_path`. The delivery layer must map explicitly.
2. **`tier` is absent from the contract** but the mock's entire inbox is organised by it — urgent / needs-action / informational groups with distinct glyphs and badge tones. Add `tier` to the `Notification` schema and regenerate.
3. **Mutable-at-import default.** `Notification.created_at: datetime = datetime.now(UTC)` is evaluated once at class definition, so every notification built without an explicit timestamp gets the process start time. Same bug in `LearningCandidate` (`evaluation/domain/learning.py`).

**Build:** a `SqlNotificationRepository`, an application service that persists the existing projection's output, and routes for list / markAllRead / markRead. Defer `registerPushSubscription` and `revokePushSubscription` — there is no subscription table, and the mock is explicit that push registers no subscription.

**Invariants from the mock:** a notification is an event plus a structured destination (`{org, project, entityType, entityId}`), never a hand-written sentence with a route guessed beside it. And "a notification is not permission" — `destinationBlock()` returns a reason string when the recipient's access does not cover the destination project, so the row says so instead of navigating somewhere misleading. That check must be server-side. Notification content must carry no prompt id, model name, or rubric version.

---

## Phase 3 — Learning candidate lifecycle

Most new persistence, because the table cannot represent the lifecycle.

**What exists:** `learning_candidates` (`0018`) with `id, org_id, scope, proposed_changes JSON, canary_pass_rate, is_promoted, created_at`. `evaluation/domain/learning.py` has `PROTECTED_SCOPES` (the eight human-only scopes) and `LearningScope` (the four permitted ones).

**Gaps:**

- The table has **no lifecycle state machine** — one `is_promoted` boolean. The mock and AGENTS.md both require candidate → shadow/canary → promoted → rolled-back, with `promoted_at`, `promoted_by`, regression-gate results, and rollback provenance. Migration required.
- No FK on `org_id`, no index, no unique constraint.
- Zero readers and zero writers in `src/`.
- No route at all for the two declared operations.
- `application/learning_pipeline.py:25` returns a bare `bool` and raises `PermissionError` / `ValueError` — contrary to the typed-result rule in AGENTS.md. Rewrite as a typed result/error.

**Build:** migration for the state machine and a canary-run table; repository; governed `promote` / `rollback` commands through the kernel, Owner-only; routes. Enforce that `proposed_changes["target_scope"]` is never in `PROTECTED_SCOPES` — the mock states it as an invariant, and AGENTS.md makes it a hard rule.

**Note the contract mismatch:** the operations return `{candidateId, stage}` where `stage` is an untyped string, and the domain has no stage concept. Define the closed enum and add it to the contract.

---

## Phase 4 — Organization settings writes

**What exists:** nothing. There is no preference, retention, or privacy table anywhere in the migration chain; `organizations` carries only `name` and `slug`. `retention` exists solely as a string inside `PROTECTED_SCOPES`.

**Build:** migration adding `jurisdiction` and default monitoring `cadence` to `organizations`, plus a per-user notification delivery preference. Then an Owner/Admin-gated update command through the kernel, and a personal-preference endpoint that any role may call.

**Follow the mock exactly on two points.** Cadence is stored canonically as `off | manual | daily | weekly` and only ever displayed through a label map — and the audit entry must speak the display vocabulary, not the stored token. Evidence retention has deliberately **no duration field**: evidence is kept until the project is deleted, and the mock's comment says a "90 days" value "only invited a surface to print a promise the product does not make." Do not add one.

---

## Phase 5 — Frontend and cleanup

Rebuild `trust.tsx`, `settings.tsx`, and `notifications.tsx` against `renderTrust` / `renderSettings` / `renderNotifications`. Delete the 22 dead files and `export/adapters/html_pdf_renderer.py` with its determinism test.

---

## Cross-cutting rules

Every governed mutation in this plan goes through `execute_governed_command` (`commanding/template.py:130`) so the domain write, the idempotency receipt, and the `authoritative_audit_events` row commit in one transaction — "any failure here rolls back the domain write, the version advance, and the receipt together."

Copy the `decisions` module chain verbatim as the template: `verify_csrf_origin(request)` first, then `get_request_scope(...)`, then build the typed command with **ids taken from the scope rather than the path** and `actor_role` server-derived, then one `session_scope()`, then typed errors mapped to envelopes. Pydantic bodies use `ConfigDict(extra="forbid")` and `Literal[...]` for closed vocabularies so out-of-vocabulary values are rejected before the handler runs.

Owner-only actions check `has_capability(role, "governance:manage")`, which `ROLE_CAPABILITIES` grants to `Role.OWNER` alone.

Three contract areas need new component schemas and a client regeneration: trust evaluations (currently untyped), notifications (`tier` missing, three fields misnamed), and learning candidates (`stage` untyped). Batch these into one contract change so the client regenerates once.

---

## Recommended sequencing under the 9-day deadline

Phase 0 is mandatory and should land first regardless of anything else — without it no organization can run a detection pass, which undercuts every other claim.

After that, the highest return is Phase 1: the judge, rubric, and persistence already exist, so exposing them converts finished work into a visible governance story. Phase 3 is the natural follow-on because it completes that story, but it carries the most new persistence and is the likeliest to be cut.

Phases 2 and 4 are the least load-bearing for judging. If time runs short, the honest move is to leave `notifications.tsx` and `settings.tsx` rendering explicit unavailable states — which is what `trust.tsx` does today and is consistent with the project's no-fabrication rule — rather than shipping half a write path.

**Open question before Phase 0:** the "Check unavailable — detection runtime is not configured" message you hit is the `GOOGLE_CLOUD_PROJECT` guard in `evaluation/runtime_provider.py`, which is a separate gate from the policy-binding failure above. Both block a real detection run. Confirm whether Vertex credentials will be available for the submission, because if not, Phase 0 unblocks persistence but detection still cannot serve live results.

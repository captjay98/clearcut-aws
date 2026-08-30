# Evidence Claims, Conflicts, Authority, and Confidence Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Admit only attributable Search/Extract snapshots as claims while preserving authority, conflicts, confidence, partial enrichment, and unresolved states.  
**Architecture:** Deterministic provenance and protected authority gates own admission; Gemini may synthesize an explanation but cannot create a claim, erase disagreement, or convert absence into clearance. Search and Extract snapshots remain immutable and origin-labelled.  
**Tech Stack:** Python 3.12, PostgreSQL, Pydantic, Hypothesis, OpenAPI, pytest.

---

**Depends on:** 05b, 04b  
**Governing inputs:** `docs/PARALLEL_INTEGRATION.md`, `docs/EVIDENCE_POLICY.md`, `docs/APPROVAL_POLICY.md`, `docs/DATA_MODEL.md`

### Task 1: Freeze claim, conflict, confidence, and unresolved contracts

**Files:**
- Modify: `packages/contracts/openapi.yaml`
- Create: `services/api/src/clearcut/research/domain/claims.py`
- Create: `services/api/src/clearcut/research/domain/conflicts.py`
- Create: `services/api/src/clearcut/research/domain/confidence.py`
- Test: `services/api/tests/evidence/test_claim_contracts.py`
- Test: `services/api/tests/evidence/test_unresolved_contracts.py`

**Steps:**
1. Add failing closed-schema tests for stance, authority proposal/validated tier, confidence inputs, conflict links, snapshot origin, partial enrichment, and unresolved reasons.
2. Run the tests; expect missing-contract failures.
3. Implement closed types. A claim cites exactly one immutable snapshot; synthesis groups claims but is not itself a claim.
4. Run contract generation/drift and schema tests; expect pass.

### Task 2: Add relational and property-enforced admission gates

**Files:**
- Create: `services/api/alembic/versions/0009_evidence_claims.py`
- Create: `services/api/src/clearcut/research/application/admit_claims.py`
- Test: `services/api/tests/evidence/test_claim_constraints.py`
- Test: `services/api/tests/evidence/test_claim_properties.py`
- Test: `services/api/tests/migrations/test_0009_evidence_claims.py`

**Steps:**
1. Add failing relational/property tests for query/run/attempt/snapshot/version binding, cross-project rejection, Search/Extract origin, unsupported stance/authority, deleted/retention state, and injection blockers.
2. Run tests; expect failures before migration/application service.
3. Add migration 0009 with composite scope foreign keys and claim/conflict uniqueness. The database must reject orphan/cross-project claims even if application validation is bypassed.
4. Implement deterministic admission. A Search excerpt may be admitted when complete; an Extract excerpt may be admitted only with its authorizing Search result. Prefer the stronger admitted excerpt without deleting either snapshot.
5. Run migration/admission/property tests; expect pass.

### Task 3: Preserve conflicts, authority, confidence, and absence

**Files:**
- Create: `services/api/src/clearcut/research/application/evaluate_evidence.py`
- Test: `services/api/tests/evidence/test_conflicts.py`
- Test: `services/api/tests/evidence/test_authority.py`
- Test: `services/api/tests/evidence/test_confidence.py`
- Test: `services/api/tests/evidence/test_unresolved.py`

**Steps:**
1. Add failing fixtures for supporting/disagreeing/context sources, only low-authority sources, Search empty, Search failure, Extract partial/total failure, unavailable URL, stale source, and unsupported legal certainty.
2. Run tests; expect evaluation failures.
3. Implement protected authority validation and deterministic conflict inputs. Confidence is a review-priority signal, not a legal probability or permission to auto-decide.
4. Ensure zero claims is valid and unresolved. Model synthesis may describe disagreement but cannot merge/delete conflicting claims.
5. Run evidence tests; expect pass.

### Task 4: Expose scoped projections and complete eligible evaluation dimensions

**Files:**
- Create: `services/api/src/clearcut/research/application/evidence_projection.py`
- Create: `services/api/src/clearcut/research/ports/evidence_projection.py`
- Test: `services/api/tests/evidence/test_evidence_projection.py`
- Test: `services/api/tests/evidence/test_evidence_evaluation.py`
- Test: `services/api/tests/security/test_evidence_scope.py`

**Steps:**
1. Add failing projection tests for best source, all sources, origin, retrieval/publication dates, conflict summary, partial enrichment, attempt trace links, redaction, and unknown/unauthorized parity.
2. Implement the projection port consumed later by item/Records modules; do not create Records routes here.
3. Complete grounding, provenance, authority/freshness, conflict, uncertainty, and tool-efficiency dimensions. Later rewrite/re-scan/report dimensions remain explicitly incomplete/not-applicable.
4. Run evidence/security/evaluation/contract tests and `uv run clearcut-eval --check-provenance`; expect zero orphan claims and visible unresolved/conflicting states.
5. Record `docs/reviews/<date>-05c-evidence-claims.md` and commit only after owner authorization with `feat: add provenance gated evidence model`.

### Exit criteria

- Every claim is attributable to one Search/Extract snapshot with complete scope and provider provenance.
- Search empty/failure and Extract partial/total failure remain truthful visible states.
- Conflicts, uncertainty, low authority, and unavailable evidence survive into review/report inputs.
- No evidence decision or legal conclusion is automated.


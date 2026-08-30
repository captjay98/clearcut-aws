# Infrastructure, Hardening, and Submission Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deploy the exact verified ClearCut revision to Google Cloud, prove operational/security behavior and live Gemini/Parallel use, and produce a compliant public submission.

**Architecture:** Terraform provisions least-privileged Cloud Run/SQL/Storage/Tasks/Scheduler/Secret Manager/observability. CI builds immutable images once, gates migrations, deploys by digest, runs staging E2E/security/operational proof, then records a frozen submission manifest.

**Tech Stack:** Terraform/OpenTofu decision from ADR, Google Cloud Run/SQL/Storage/Tasks/Scheduler/Secret Manager, Artifact Registry, Cloud Build/GitHub Actions, OpenTelemetry, Semgrep/dependency/SBOM scans.

---

**Depends on:** Plan 01 for foundation; all plans for final R9  
**Checkpoint:** R9

### Task 1: Provision isolated environments and identities

Create Terraform modules/state policy, separate service identities, private task handlers, Cloud SQL/Storage/Tasks/Scheduler/secrets, budgets/alerts/log sinks. Test plan in CI; apply requires explicit approval. No exported service-account keys.

### Task 2: Implement build/migration/deploy pipeline

Build site/web/api images once with SBOM/provenance, scan, push by digest, run pre-migration compatibility and separate Alembic job, deploy staged traffic, smoke, promote, and retain rollback. App startup never migrates.

### Task 3: Add operational and recovery proof

Verify task auth, leases/retries/reconciliation, provider failure visibility, scheduler dedupe, database backup/PITR restore drill, object/artifact access, secret rotation, session revocation, deletion job, telemetry correlation, redaction canaries, cost/budget alerts.

The production composition manifest registers `GeminiAdkRuntime`, `ParallelSearchAdapter`, and `ParallelExtractAdapter`; it registers `ParallelMonitorAdapter` only when the recorded go/no-go is GO and deployed webhook proof passes. Dependency/SBOM/startup validation requires Search and rejects another AI model, agent framework, research provider/fallback, test fake, or excluded Parallel agent API in the production profile.

### Task 4: Run full release gate

```text
clean candidate tree
-> recorded SHA
-> HEAD equals target remote SHA
-> all quality/contract/security/UI gates
-> deploy exact image digests from that SHA
-> authenticated golden path + role/tenant negative paths
-> live Gemini/ADK and Parallel traces
-> operational/recovery checks
-> GO/NO-GO verdict
```

Moving candidates, uncommitted changes, failed hard gates, missing runtime proof, or money/security/evidence ambiguity block GO.

### Task 5: Build original demo and three-minute video

Use an entrant-owned screenplay and disclose demo/sample data. Show import, real agent/detection, a mandatory live Parallel Search trace, bounded Extract outcome, evidence/conflict, governed rewrite by another reviewer, selective re-scan, and snapshot/release. Show a previously delivered Monitor signal only when it is part of the exact deployed candidate and label it as re-verified. Keep under three minutes, public, English/subtitled.

### Task 6: Assemble public repository and Devpost submission

Verify license/About visibility, run instructions from clean clone, architecture/data/authority/limitations docs, all source/assets, hosted URL, repo URL, video URL/duration/visibility, feature/technology/data/learnings copy, Parallel track selection, and exact package/runtime calls.

```yaml
submission:
  gitSha: "<exact-sha>"
  imageDigests: ["clearcut-site@sha256:...", "clearcut-web@sha256:...", "clearcut-api@sha256:..."]
  runtimeProof:
    geminiTraceId: "..."
    parallelSearchId: "..."
    parallelExtractId: "...|not-enabled"
    parallelMonitorId: "...|not-enabled"
  verdict: "GO|NO-GO"
```

### Task 7: Resolve compliance correspondence

Obtain and retain written organizer clarification about development-assistant eligibility before asserting compliance. Do not alter history or misstate how code was produced. Record remaining risk in the submission manifest.

```bash
pnpm verify
uv run pytest services/api -q
pnpm --filter @clearcut/web test:e2e
terraform -chdir=infra/gcp plan -detailed-exitcode
```

Expected: quality commands exit 0; Terraform returns 0 for no changes or reviewed 2 for an intentional plan; the evidence pack records which.

### Exit criteria

- Local/remote/deployed revision and image digests match exactly.
- Clean-clone install/test/run succeeds.
- Authenticated golden path and tenant/role/security negatives pass on hosted target.
- Runtime Gemini/ADK and Parallel traces match video behavior.
- Recovery/observability/redaction/budget checks pass.
- Public repo/license/video/hosted URL/Devpost fields are verified.
- R9 gives a concise GO/NO-GO with explicit limitations; no plan prose substitutes for evidence.

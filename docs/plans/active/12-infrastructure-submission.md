# Infrastructure, Hardening, and Submission Implementation Plan

> **For agents:** Use the executing-plans workflow and stop at every cloud, paid-provider, or release authorization boundary.

**Goal:** Prepare and provider-free verify one portable ClearCut release, then—only after explicit authorization—deploy the exact verified revision, collect hosted operational/provider evidence, and assemble a truthful public submission.

**Architecture:** One immutable `clearcut` image packages Astro, TanStack Start, FastAPI, Alembic migrations, and scripts. FastAPI is the sole public entry point. GCP Starter uses one public Cloud Run service plus a separate same-digest migration job, GCS, Cloud Tasks, Secret Manager, and an existing PostgreSQL database or separately acknowledged Cloud SQL.

**Tech Stack:** Terraform CLI and Google provider, Cloud Run/SQL/Storage/Tasks/Secret Manager, singular Artifact Registry, GitHub Actions with Workload Identity Federation, OpenTelemetry, Semgrep/dependency/SBOM scans.

**Current boundary:** source implementation and provider-free controls exist; infrastructure remains unapplied and the submission verdict remains NO-GO.

---

**Depends on:** implemented product foundation and all product plans for final R9

**Checkpoint:** R9

### Task 1: Complete fail-closed infrastructure definitions

Keep all resource management opt-in. Add only reviewed workload, identity, data, queue, secret, observability, budget, and recovery capabilities. Existing resources require an explicit retain/import/migrate/replace/unmanaged/retire disposition. No exported service-account keys.

### Task 2: Maintain the one-digest release pipeline

Build one `clearcut` image with SBOM/provenance, scan it, and pass one immutable digest through the protected migration workflow and deployment workflow. Run Alembic as a separate same-digest job. Create one no-traffic candidate, run GET-only smoke checks against that exact revision, promote only that revision, and retain rollback evidence. Application startup never migrates.

### Task 3: Prove operational and recovery behavior

After separate cloud authorization, verify task OIDC, leases/retries/reconciliation, provider failure visibility, scheduler dedupe, database backup/PITR restore, object access, secret rotation, session revocation, deletion, telemetry correlation, redaction canaries, and budget alerts. Provider-free tests do not satisfy hosted drills.

The production profile registers Gemini/ADK and Parallel Search/Extract only when each provider is explicitly enabled with cost acknowledgement, credentials, quota, and a positive concurrency cap. Parallel Monitor is registered only after the recorded GO and signed-webhook proof. Startup and dependency checks reject alternate model/research providers, test fakes, silent fallbacks, and excluded Parallel APIs.

### Task 4: Run the full release gate

```text
clean candidate tree
-> recorded SHA equals authorized target SHA
-> all quality/contract/security/UI gates
-> one image digest from that SHA
-> same-digest migration
-> exact no-traffic candidate
-> authenticated golden path + role/tenant negative paths
-> authorized live Gemini/ADK and Parallel traces
-> operational/recovery evidence
-> accountable GO/NO-GO verdict
```

Moving candidates, uncommitted changes, failed hard gates, missing runtime proof, or cost/security/evidence ambiguity block GO.

### Task 5: Build the original demo and three-minute video

Use an entrant-owned screenplay and disclose synthetic/sample data. Show import, authorized live detection/research, mandatory Parallel Search, bounded Extract, evidence/conflict, governed rewrite, selective re-scan, and report generation/release. Show Monitor only when it belongs to the exact deployed candidate and label the previously delivered signal as re-verified. Keep the video public, English or subtitled, and under three minutes.

### Task 6: Assemble the public repository and Devpost submission

Verify clean-clone installation, license and repository visibility, architecture/data/authority/limitations docs, hosted URL, repository URL, video URL/duration/visibility, feature and technology copy, Parallel track selection, and exact runtime calls.

```yaml
submission:
  gitSha: "<exact-sha>"
  imageDigest: "clearcut@sha256:<digest>"
  migrationImageDigest: "clearcut@sha256:<same-digest>"
  deployedRevision: "<exact-candidate-revision>"
  runtimeProof:
    geminiTraceId: "...|not-verified"
    parallelSearchId: "...|not-verified"
    parallelExtractId: "...|not-enabled"
    parallelMonitorId: "...|not-enabled"
  verdict: "GO|NO-GO"
```

### Task 7: Resolve compliance correspondence

Retain written organizer clarification about development-assistant eligibility before asserting compliance. Do not alter history or misstate how code was produced. Record remaining risk in the submission manifest.

### Provider-free checks

```bash
pnpm verify
uv run pytest services/api/tests -q
pnpm --filter clearcut-web test:e2e -- --workers=1
terraform fmt -check -recursive infra/gcp
terraform -chdir=infra/gcp/environments/production init -backend=false -input=false
terraform -chdir=infra/gcp/environments/production validate
terraform -chdir=infra/gcp/environments/production test
```

These checks must not call paid providers, initialize a real backend, plan/apply/import state, or mutate cloud resources.

### Exit criteria

- Local, remote, and deployed revision plus one image digest match exactly.
- Clean-clone install/test/run succeeds.
- Authenticated golden path and tenant/role/security negatives pass on the hosted target.
- Authorized runtime Gemini/ADK and Parallel traces match video behavior.
- Recovery, observability, redaction, and budget checks pass.
- Public repository, license, video, hosted URL, and Devpost fields are verified.
- R9 records a concise GO/NO-GO with explicit limitations; plan prose never substitutes for evidence.

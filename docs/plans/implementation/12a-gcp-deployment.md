# Google Cloud Infrastructure and Deployment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Provision least-privileged environments and promote immutable verified images through gated migrations.  
**Architecture:** Terraform/OpenTofu provisions three Cloud Run services plus Cloud SQL/GCS/Tasks/Scheduler/Secrets/telemetry; images build once and promote by digest.  
**Tech Stack:** GCP, Terraform/OpenTofu, GitHub Actions/Cloud Build, OpenTelemetry.

---

**Files:** Create `infra/gcp/modules/`, `infra/gcp/environments/dev/`, `staging/`, `production/`, `infra/gcp/README.md`, `.github/workflows/build.yml`, `deploy.yml`, `migrate.yml`, `services/api/src/clearcut/bootstrap/production_manifest.py`; test `infra/gcp/tests/`, `services/api/tests/bootstrap/test_contest_profile.py`.

1. Add failing policy tests for distinct identities, private tasks, encrypted storage/SQL, backups/PITR, budgets/alerts, no keys, immutable digest, required GeminiAdkRuntime/ParallelSearchAdapter, bounded ParallelExtractAdapter, conditional ParallelMonitorAdapter, and rejection of alternate providers/excluded Parallel APIs.
2. Implement modules/pipelines with plan review, separate migration job, staged traffic, smoke, rollback, SBOM/provenance/security scans.
3. Run Terraform validation/plan, startup manifest, backup/restore, secret rotation, task auth/reconcile, redaction/correlation tests; expect reviewed plan exit 0/2 and all behavioral checks exit 0.
4. Record evidence; commit `infra: add gated google cloud deployment` only with explicit infrastructure authorization.

**Exit:** Exact digests deploy through reviewed migrations with tested rollback/recovery and only approved contest adapters.

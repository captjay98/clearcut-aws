# ADR 0003: Terraform for Google Cloud Infrastructure

## Status

**Accepted** (2026-08-31). The original deployment-topology premise is superseded by ADR 0004; the Terraform governance decisions below remain accepted.

## Context

At the time of this decision, ClearCut targeted Google Cloud with three separately deployable services (`clearcut-site`, `clearcut-web`, and `clearcut-api`) plus Cloud SQL PostgreSQL, Cloud Storage, Cloud Tasks, Cloud Scheduler, Secret Manager, Artifact Registry, Vertex AI, observability, budgets, and alerts. ADR 0004 later replaced only that workload topology with one portable `clearcut` image and service.

The repository now contains an unapplied Terraform foundation with four fail-closed capability modules. The authorized project already contains manually created resources, including a combined Cloud Run service, a Cloud SQL instance, build buckets, an image repository, and a database secret. Those existing resources remain unmanaged; they are not evidence that the target architecture is deployed and must not be adopted, replaced, or destroyed without explicit review.

ClearCut needs an infrastructure toolchain that is well supported on Google Cloud, works with keyless GitHub authentication, produces reviewable plans, preserves recovery evidence, and does not allow automation to change protected policy or governance rules.

## Decisions

### 1. Canonical infrastructure engine

- Terraform CLI is the canonical infrastructure engine for ClearCut.
- ClearCut uses the Google provider and portable HCL modules.
- Terraform Cloud and Terraform Enterprise are not required.
- Google Infrastructure Manager is not used initially. GitHub Actions remains the controlled plan and apply surface.
- Configuration should avoid unnecessary Terraform-proprietary features so a future OpenTofu migration remains feasible through a separately reviewed ADR and state migration.

### 2. Version and provider control

- The Terraform CLI version is pinned in the repository toolchain configuration.
- Every root module sets a bounded Terraform version constraint.
- Provider constraints are reviewed deliberately; major provider upgrades are never automatic.
- `.terraform.lock.hcl` is committed for each independent root module and updated only through reviewed dependency work.
- `.terraform/`, local state, plan files, crash logs, and override files are never committed.

### 3. Repository structure and environment isolation

- Reusable modules live under `infra/gcp/modules/`.
- Deployable roots live under `infra/gcp/environments/<environment>/`.
- Production does not share a state object or state prefix with development, staging, bootstrap, or recovery tooling.
- Terraform workspaces are not used as the primary production-isolation boundary. Separate roots and state prefixes make ownership explicit.
- The current production root composes the implemented foundation capabilities but manages zero resources by default until its complete plan, controls, and import dispositions are reviewed.

### 4. Remote state bootstrap and protection

- Production state uses a dedicated GCS bucket, not either existing build bucket.
- The state bucket requires uniform bucket-level access, public access prevention, object versioning, soft-delete or retention controls, audit logging, and least-privileged IAM.
- Google-managed encryption is acceptable initially. A customer-managed Cloud KMS key may be adopted when its rotation and recovery ownership are approved.
- State bootstrap is a separate, one-time, human-approved operation. Its local bootstrap state is encrypted, retained only until remote state is verified, and then securely removed according to the approved runbook.
- State objects and saved plans are treated as sensitive because providers may record identifiers or secret-derived values.
- Concurrent production applies are prohibited. CI uses a single protected concurrency group in addition to backend locking.

### 5. Authentication and authorization

- Local inspection and planning use Google Application Default Credentials with service-account impersonation after the least-privileged planning identity exists.
- GitHub Actions uses Google Workload Identity Federation. Long-lived exported service-account keys are prohibited.
- Planning, deployment, migration, and runtime identities are separate and least privileged.
- The personal project-owner account is bootstrap-only and is not the steady-state CI identity.
- The current foundation defines no ClearCut-authored explicit Terraform IAM resources. Enabling approved Google APIs may nevertheless create Google-managed service agents/default identities and role bindings outside explicit Terraform IAM resources; this requires IAM/org-policy review.
- Production project-service management requires `acknowledge_service_identity_side_effects = true`, defaulting to false. That acknowledgement is not apply authorization, and API activation remains deferred to identity/IAM review.
- Production apply requires an accountable human approval through a protected GitHub environment.
- Terraform automation may not alter protected human-only rules, approval policy, evidence schemas, retention/privacy policy, category definitions, source-authority tiers, or legal-boundary language.

### 6. Plan and apply workflow

The required workflow is:

1. Run `terraform fmt -check`.
2. Run `terraform init` against the approved backend.
3. Run `terraform validate`.
4. Run repository infrastructure boundary and security checks.
5. Produce a saved plan with a pinned Terraform CLI and provider lock file.
6. Review resource changes, replacements, IAM grants, network exposure, data retention, deletion behavior, and estimated cost.
7. Retain the reviewed plan as a protected, short-lived artifact without exposing sensitive values.
8. Obtain protected-environment human approval.
9. Apply exactly the reviewed saved plan.
10. Run migrations as a separate one-shot operation.
11. Run candidate health, authorization, and rollback smoke gates before traffic promotion.
12. Record immutable image digests, deployed revisions, migration evidence, and the accountable approver.

No local or CI `terraform apply`, import, state mutation, or resource deletion is permitted before the full root modules and first plan are reviewed.

### 7. Existing-resource adoption

Every existing GCP resource receives one explicit disposition before it appears in managed state:

- **Import and retain:** the resource matches the target design and can be safely adopted.
- **Import and migrate:** the resource must be hardened or reshaped through a reviewed, non-destructive sequence.
- **Replace:** a replacement is created and validated before traffic or data moves; rollback remains available.
- **Leave unmanaged temporarily:** ownership and drift boundaries are documented with an expiry decision.
- **Retire:** deletion occurs only after data retention, backup, rollback, and approval gates pass.

Terraform import blocks or equivalent reviewed import commands must bind exact resource identities. A first plan must show no unintended replacement or deletion. The existing Cloud SQL instance may not be replaced, recreated, or have destructive settings changed until a verified backup and restore path exists.

### 8. Recovery and operational ownership

Before production GO, ClearCut records owners and rehearsed procedures for:

- GCS state-object version recovery and accidental state-change recovery.
- Cloud SQL automated backups, point-in-time recovery, and a retained restore drill.
- Cloud Run revision rollback and traffic restoration.
- Failed database migration recovery.
- Secret rotation without exposing values.
- Workload Identity Federation revocation and CI credential recovery.
- Cloud Tasks authentication, replay, and dead-letter handling.
- Session revocation, deletion, redaction, and access-control drills.
- Drift detection and reconciliation.
- Budget thresholds, alerts, logging, tracing, and incident escalation.

Recovery actions that mutate production remain accountable human-triggered operations. Documentation or local deterministic tests cannot substitute for hosted drill evidence.

### 9. Current readiness boundary

Adopting Terraform does not change the submission verdict. The environment remains NO-GO until the reviewed infrastructure exists and the external evidence in `docs/submission/manifest.yaml` is recorded. `terraform validate` proves configuration validity only; it does not prove deployability, security, provider availability, recovery, or hosted operation.

## Consequences

- ClearCut gains the Google Cloud toolchain with the strongest first-party documentation and examples.
- Internal Terraform use does not require Terraform Cloud or a HashiCorp subscription.
- GCP resources and provider calls remain independently billable.
- Infrastructure changes become reviewable and reproducible, but initial module implementation and resource import require careful up-front work.
- State protection, IAM separation, recovery drills, and human approval add operational overhead intentionally.
- Existing resources cannot be casually brought under management or destroyed.
- Portable HCL preserves a practical path to OpenTofu if licensing, governance, or toolchain requirements change.

## Rejected Alternatives

- **OpenTofu now:** technically compatible with the Google provider and GCS backend, but Google documents and manages Terraform as its first-class IaC path. OpenTofu remains a viable future migration option.
- **Terraform Cloud:** unnecessary for the current project; GitHub Actions, WIF, GCS state, and protected environments provide the required control surface without another hosted control plane.
- **Infrastructure Manager now:** adds a second deployment control plane before ClearCut has complete modules, state ownership, imports, and recovery procedures.
- **Direct `gcloud` scripts as the source of truth:** insufficient for reviewed desired state, drift detection, dependency ordering, and reproducible recovery.
- **Continue unmanaged resources:** preserves ambiguity, broad credentials, and unreviewed drift and cannot satisfy the production evidence gates.

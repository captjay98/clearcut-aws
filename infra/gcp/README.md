# Google Cloud Infrastructure (ClearCut)

> **Status: NO-GO / unapplied scaffold.** No GCP resources are provisioned by the current scaffold. The repository contains provider constraints, explicit environment inputs, and fail-closed workflow shapes only; it does not contain a reviewed Terraform plan or apply evidence.

## Planned hosted architecture

The target architecture has three separately deployable images/services:

- `clearcut-site`: public Astro site.
- `clearcut-web`: public workspace and same-origin API boundary.
- `clearcut-api`: private modular-monolith application runtime behind that boundary.

The planned data and operational services are Cloud SQL PostgreSQL, Cloud Storage, Cloud Tasks, Cloud Scheduler, Secret Manager, Artifact Registry, logging/tracing, budgets, and alerts. These are requirements, not claims about deployed infrastructure.

## Current files

`environments/production/main.tf` pins Terraform and the Google provider and requires an explicit `project_id`. It intentionally has no default production project and currently declares no resources or remote state backend.

The GitHub workflows use OIDC/Workload Identity Federation variable references rather than exported service-account keys. They require protected environments and immutable image-digest inputs. Those controls still require an owner to provision least-privileged service accounts, WIF bindings, migration jobs, Cloud Run services, and environment approvals before execution.

`cloudbuild.yaml` builds a combined validation image only. It cannot deploy or promote traffic and is not one of the required three production images.

## Required work before any apply

1. Review and approve an ADR for Terraform/OpenTofu, remote state, environment isolation, and recovery ownership.
2. Implement modules for least-privileged identities, networking, Cloud Run, Cloud SQL, Storage, Tasks/Scheduler, secrets, observability, budgets, and alerts.
3. Add plan/lint/security checks and review the complete plan without applying it.
4. Obtain explicit GCP project, billing, IAM, and deployment authorization.
5. Apply through a protected workflow, build three images once, deploy by digest, run migration and candidate smoke gates, then record immutable evidence.
6. Run and retain backup/PITR restore, rollback, secret rotation, task-auth, redaction, session-revocation, deletion, observability, and cost-alert drills.

Do not run `terraform apply`, deploy, or incur provider charges solely to satisfy documentation. Missing hosted evidence remains an explicit blocker in `docs/submission/manifest.yaml`.

## Local validation status

Terraform was not available in the local implementation environment, so `terraform fmt` and `terraform validate` have not been claimed. Repository tests verify only the static safety boundaries described above.

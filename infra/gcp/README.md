# Google Cloud Infrastructure (ClearCut)

> **Status: NO-GO / unapplied.** Four capability modules are implemented and locally testable, but this Terraform foundation has not provisioned, adopted, or changed any GCP resource. There is no reviewed plan, apply evidence, hosted release evidence, or authorization to mutate cloud resources.

## GCP Starter topology

GCP Starter packages the application as one immutable `clearcut` image and exposes one public Cloud Run service. FastAPI serves the public Astro site, TanStack workspace, application API, and protected internal task endpoints. A separate migration job reuses the exact image digest; startup never migrates.

The intended hosted dependencies are an existing PostgreSQL database or separately acknowledged Cloud SQL, GCS, Cloud Tasks, Secret Manager, Artifact Registry, and logging/alerting. Built-in opaque sessions remain the default. Firebase runtime composition is not yet wired. Paid Gemini and Parallel providers remain disabled without explicit cost acknowledgement, bounded concurrency, credentials, and quota.

The GitHub release workflows implement one-digest build, migration, no-traffic candidate, GET-only smoke, and exact-revision promotion contracts. They assume pre-existing authorized workload resources and identities; those references are not proof of deployment.

## Singular Artifact Registry contract

The repository contract uses exactly one Docker repository with ID `clearcut`. Environment remains explicit in configuration and labels; the repository ID has no environment or component suffix. Production accepts the nullable `artifact_repository` object and exposes singular `artifact_repository_id` and `artifact_repository_name` outputs. Management is off by default:

```hcl
manage_artifact_registry       = false
artifact_registry_environment = "production"
artifact_repository = {
  repository_id = "clearcut"
  description   = "ClearCut production deployment images"
  keep_count    = 20
  labels = {
    application = "clearcut"
    environment = "production"
    managed_by  = "terraform"
  }
}
```

The module retains `prevent_destroy = true`, `cleanup_policy_dry_run = true`, and a KEEP-only policy with a positive retention count. Existing repositories remain unmanaged; this contract does not authorize adoption, replacement, or apply.

## Implemented Terraform foundation

Four capability modules are implemented:

- `modules/state-bootstrap` defines a protected GCS state-bucket capability.
- `modules/project-services` defines bounded project-service enablement.
- `modules/artifact-registry` defines the guarded singular `clearcut` repository.
- `modules/network-foundation` defines a VPC, subnet, private-service range, and service-networking connection.

`environments/production` composes stable `module.project_services`, `module.artifact_registry`, and `module.network_foundation` addresses. Child resources are gated by explicit `manage_*` inputs that default to `false`, so production manages zero resources by default. Project API management additionally requires `acknowledge_service_identity_side_effects = true`, also defaulting to `false`.

The foundation defines no ClearCut-authored explicit Terraform IAM resources. Enabling Google APIs may create Google-managed service agents/default identities and bindings outside those resources; the acknowledgement records awareness of that possibility and is not apply authorization. API activation remains deferred to identity and organization-policy review.

The production root requires an explicit `project_id`, defines no backend, and fixes the current phase to `us-central1`. `bootstrap/state` is a separate unapplied root at stable address `module.state_bucket`, with management disabled by default. Both roots require Terraform 1.16.x and constrain the Google provider to `~> 5.0`; lock files include `darwin_arm64` and `linux_amd64`.

## Unmanaged and deferred scope

Existing cloud resources remain unmanaged. Manually created Cloud Run, Cloud SQL, bucket, repository, and secret resources have no reviewed adoption disposition and must not be imported, replaced, or destroyed by this source.

Deferred capabilities include:

- workload, migration, planning, and runtime identities plus Workload Identity Federation;
- complete Cloud Run service and migration-job resources;
- Cloud SQL ownership, backups, restore evidence, and network attachment;
- GCS application buckets, Cloud Tasks queues, schedules, and dead-letter policy;
- secrets, rotation, observability, budgets, alerts, and operational evidence;
- Portable Server PostgreSQL dispatch and optional Firebase runtime composition.

`cloudbuild.yaml` builds the unified application image. It cannot deploy or promote traffic.

## Required work before any apply or hosted release

1. Follow ADR 0003 for state, isolation, identity, import safety, approval, and recovery ownership.
2. Follow ADR 0004 for the one-image/service deployment contract.
3. Complete and review every deferred capability and disposition for existing resources.
4. Review a full production plan without applying it; include security, cost, IAM, replacement, and deletion analysis.
5. Obtain explicit project, billing, identity, state-bootstrap, import, database, and deployment authorization.
6. Use protected human-triggered workflows for any bootstrap, import, apply, migration, or release.
7. Retain hosted smoke, backup/restore, rollback, secret rotation, task-auth, redaction, session-revocation, deletion, observability, and cost-alert evidence.

Do not run Terraform mutation commands or incur provider charges solely to satisfy documentation. Missing hosted evidence remains a blocker in `docs/submission/manifest.yaml`.

## Provider-free verification evidence

The repository has passed focused boundary tests plus `terraform fmt`, `terraform init -backend=false`, `terraform validate`, and mock-provider `terraform test` runs. These checks do not include direct `terraform plan`, apply, import, state, destroy, backend initialization, or a cloud API call. They establish source-contract behavior only, not deployability or production readiness.

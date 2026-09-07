# Google Cloud Infrastructure (ClearCut)

> **Status: NO-GO / unapplied.** Four capability modules are implemented and locally testable, but this Terraform foundation has not provisioned, adopted, or changed any GCP resource. There is no reviewed plan, apply evidence, or deployment evidence.

## Deadline Artifact Registry contract

The deadline contract uses exactly one Docker repository with ID `clearcut`. Environment remains explicit in configuration and labels; the repository ID has no environment or site/web/api suffix. This replaces the earlier three-repository requirement independently of the longer-term service architecture below.

Production accepts the singular nullable `artifact_repository` object and exposes `artifact_repository_id` and `artifact_repository_name`. The module accepts `repository` and exposes `repository_id` and `repository_name`. Both outputs are `null` while management is disabled. Configuration alone creates no resources:

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

The module retains `prevent_destroy = true`, `cleanup_policy_dry_run = true`, and one KEEP-only policy with an explicit positive integer retention count. Enabled management requires an explicit repository, environment, and location. The resource address is `module.artifact_registry.google_artifact_registry_repository.repository[0]`; there are no imports or state moves. Existing repositories remain unmanaged, and this source contract does not authorize adoption, replacement, or application against existing state.

## Planned hosted architecture

The target architecture has three separately deployable images/services:

- `clearcut-site`: public Astro site.
- `clearcut-web`: public workspace and same-origin API boundary.
- `clearcut-api`: private modular-monolith application runtime behind that boundary.

The planned data and operational services are Cloud SQL PostgreSQL, Cloud Storage, Cloud Tasks, Cloud Scheduler, Secret Manager, Artifact Registry, logging/tracing, budgets, and alerts. These are requirements, not claims about deployed infrastructure.

## Implemented Terraform foundation

Four capability modules are implemented:

- `modules/state-bootstrap` defines the protected GCS state bucket capability.
- `modules/project-services` defines bounded project-service enablement.
- `modules/artifact-registry` defines the guarded singular `clearcut` image repository.
- `modules/network-foundation` defines the VPC, subnet, private-service range, and service-networking connection.

`environments/production` composes the three production capabilities at stable addresses: `module.project_services`, `module.artifact_registry`, and `module.network_foundation`. The root modules always remain in the composition; their child resources are gated by explicit `manage_*` inputs that default to `false`. Production therefore manages zero resources by default without changing module addresses. Project API management additionally requires `acknowledge_service_identity_side_effects = true`, which also defaults to `false`. Enabling approved Google APIs may create Google-managed service agents/default identities and role bindings outside explicit Terraform IAM resources and therefore requires IAM/org-policy review. The acknowledgement records awareness of those side effects; it is not apply authorization. This foundation defines no ClearCut-authored explicit Terraform IAM resources, but it does not claim that provider-managed IAM side effects cannot occur. Project API activation remains deferred to identity/IAM review. The root requires an explicit `project_id`, has no default production project, and defines no backend. Its single `region` input is fixed to the approved `us-central1` location for this phase and drives the provider, Artifact Registry, network foundation, and canonical regional subnet name; independent repository-location and network-region inputs are intentionally absent.

`bootstrap/state` is a separate, unapplied state-bootstrap root at stable address `module.state_bucket`. Its child resource is gated by `manage_state_bucket`, which also defaults to `false`. Keeping state bootstrap separate prevents production from attempting to create or own its own backend.

Both roots require Terraform 1.16.x and constrain the Google provider to `~> 5.0`. Their lock files select Google provider 5.45.2 and include locks for `darwin_arm64` and `linux_amd64`.

ADR 0003 records the accepted Terraform CLI, portable HCL, protected GCS state, Workload Identity Federation, environment isolation, import, approval, and recovery decisions. Acceptance does not authorize an apply.

## Unmanaged and deferred scope

Existing cloud resources remain unmanaged. The manually created Cloud Run service, Cloud SQL instance, build buckets, image repository, and database secret have not been imported or assigned a reviewed adoption disposition. This foundation must not adopt, replace, or destroy them.

The following capabilities remain deferred:

- identities, IAM bindings, and Workload Identity Federation;
- edge routing and the final public workspace/API boundary;
- deployable site, web, API, migration, and worker workloads;
- application data services, including Cloud SQL and application storage;
- queues and schedules;
- secrets and rotation;
- observability, budgets, alerts, and operational evidence.

The GitHub workflows reference OIDC/Workload Identity Federation variables rather than exported service-account keys. They require protected environments and immutable image digests, but owners must still provision and authorize the deferred identities and workloads before those workflows can deploy.

`cloudbuild.yaml` builds a combined validation image only. It cannot deploy or promote traffic and is not one of the required three production images.

## Required work before any apply

1. Follow ADR 0003 for remote state, environment isolation, import safety, approvals, and recovery ownership.
2. Complete and review the deferred capabilities and explicit dispositions for every existing resource.
3. Add plan, lint, security, cost, and drift checks, then review a complete production plan without applying it.
4. Obtain explicit GCP project, billing, IAM, state-bootstrap, import, and deployment authorization.
5. Use protected human-triggered workflows for any future bootstrap, import, apply, migration, or release action.
6. Run and retain backup/PITR restore, rollback, secret rotation, task-auth, redaction, session-revocation, deletion, observability, and cost-alert drills.

Do not run Terraform mutation commands or incur provider charges solely to satisfy documentation. Missing hosted evidence remains an explicit blocker in `docs/submission/manifest.yaml`.

## Deadline contract verification (2026-09-07)

- Focused Artifact Registry and default-management foundation tests: **7 passed**.
- `terraform fmt -check -recursive infra/gcp`: passed.
- Production with disposable external `TF_DATA_DIR`: `terraform init -backend=false -input=false -no-color`, `terraform validate -no-color`, and `terraform test -no-color` passed; **45 native mock-provider tests passed**.
- TDD red evidence: the new singular-contract foundation assertions failed against the earlier plural interface before implementation; native tests also rejected the missing singular outputs.

These checks use a mock Google provider with plan-time fixture values. No direct Terraform plan, apply, import, state, or destroy command, backend initialization, or cloud API call is part of this verification. The historical broader checks below were not rerun for this scoped change.

## Prior foundation verification

The following provider-free checks passed in this worktree:

- `uv run pytest tests/foundation/test_deployment_boundaries.py -q`: **26 passed**.
- `pnpm verify`: toolchain, feature-coverage, architecture, contract, foundation, and submission verification passed. Its contract-integrity precheck reported **18 passed with 8 warnings**; the main repository suite reported **152 passed with 149 warnings**; and the submission suite reported **9 passed**. The warnings are Python 3.12 deprecations for the default SQLite datetime adapter, not Terraform or infrastructure warnings.
- `terraform fmt -check -recursive infra/gcp`: passed.
- In `bootstrap/state`, using a fresh external `TF_DATA_DIR`:
  - `terraform init -backend=false -input=false -no-color`: passed.
  - `terraform validate -no-color`: passed.
  - `terraform test -no-color`: **5 passed, 0 failed**.
- In `environments/production`, using a separate fresh external `TF_DATA_DIR`:
  - `terraform init -backend=false -input=false -no-color`: passed.
  - `terraform validate -no-color`: passed.
  - `terraform test -no-color`: **41 passed, 0 failed**.
- Both root lock files select Google provider **5.45.2** under `~> 5.0` and contain locks for **darwin_arm64** and **linux_amd64**.

These checks used mock-provider tests. No direct `terraform plan`, `apply`, `import`, `state`, or `destroy` command ran. Backend initialization was disabled. No GCP or Google provider API call, cloud mutation, resource adoption, deployment, or provider charge occurred. Local initialization only prepared disposable external Terraform working data, which was removed after verification.

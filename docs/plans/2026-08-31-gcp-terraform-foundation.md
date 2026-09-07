# GCP Terraform Foundation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build and locally validate fail-closed Terraform modules for protected state bootstrap, reviewed project APIs, Artifact Registry, and baseline private networking without planning, applying, importing, or contacting GCP.

**Architecture:** Four capability-oriented modules expose narrow, nonsensitive interfaces. A separate state-bootstrap root owns future backend infrastructure; the production root composes project-services, artifact-registry, and network-foundation behind management flags that default to false. Existing cloud resources remain unmanaged.

**Tech Stack:** Terraform 1.16.0, HashiCorp Google provider 5.45.2, Terraform mock-provider tests, Python/pytest static safety tests, pnpm workspace verification.

---

## Execution boundaries

- Work only in `/Users/captjay98/projects/clearcut` unless a separately approved worktree is prepared.
- Do not inspect or modify `.clearcut/`, `services/api/.clearcut/`, or `semantic-review/`.
- Do not run `terraform plan`, `apply`, `import`, `state`, `destroy`, or backend initialization.
- Do not call GCP, Gemini, Parallel, or any paid provider.
- Use `TF_DATA_DIR` under `/tmp` and `terraform init -backend=false` only.
- Use Terraform `mock_provider` for all native tests.
- Do not add dependencies or change provider major versions.
- Do not commit, push, or create a PR unless explicitly requested. Treat each task boundary below as an optional commit checkpoint only.
- Preserve `.salvage-from-b/` files and all unrelated work.

## Target tree

```text
infra/gcp/
├── bootstrap/state/
│   ├── .terraform.lock.hcl
│   ├── main.tf
│   ├── outputs.tf
│   ├── variables.tf
│   ├── versions.tf
│   └── tests/state_bootstrap.tftest.hcl
├── environments/production/
│   ├── .terraform.lock.hcl
│   ├── main.tf
│   ├── outputs.tf
│   ├── variables.tf
│   ├── versions.tf
│   └── tests/foundation.tftest.hcl
└── modules/
    ├── artifact-registry/{main,outputs,variables,versions}.tf
    ├── network-foundation/{main,outputs,variables,versions}.tf
    ├── project-services/{main,outputs,variables,versions}.tf
    └── state-bootstrap/{main,outputs,variables,versions}.tf
```

### Task 1: Add failing repository safety contracts

**Files:**
- Modify: `tests/foundation/test_deployment_boundaries.py`
- Reference: `docs/plans/2026-08-31-gcp-terraform-foundation-design.md`

**Step 1: Add tests for the intended tree and prohibited patterns**

Add focused tests that assert:

```python
FOUNDATION_MODULES = {
    "state-bootstrap",
    "project-services",
    "artifact-registry",
    "network-foundation",
}


def test_terraform_foundation_modules_exist() -> None:
    modules = ROOT / "infra/gcp/modules"
    assert FOUNDATION_MODULES <= {path.name for path in modules.iterdir() if path.is_dir()}


def test_terraform_foundation_remains_fail_closed() -> None:
    production = read("infra/gcp/environments/production/variables.tf")
    for variable_name in (
        "manage_project_services",
        "manage_artifact_registry",
        "manage_network_foundation",
    ):
        assert f'variable "{variable_name}"' in production
    assert production.count("default     = false") >= 3


def test_terraform_foundation_has_no_unsafe_ownership_or_access() -> None:
    terraform = "\n".join(
        path.read_text()
        for path in (ROOT / "infra/gcp").rglob("*.tf")
        if ".terraform" not in path.parts
    )
    forbidden = (
        'resource "google_service_account_key"',
        'roles/owner',
        'roles/editor',
        'member = "allUsers"',
        "force_destroy = true",
        'resource "google_compute_firewall"',
        "import {",
    )
    for token in forbidden:
        assert token not in terraform
```

Also assert that the state bucket source contains uniform access, enforced public-access prevention, versioning, and `prevent_destroy`; project services use `disable_on_destroy = false`; the network uses `auto_create_subnetworks = false`; and the production root has no backend block.

**Step 2: Run the tests and verify RED**

Run:

```bash
uv run pytest tests/foundation/test_deployment_boundaries.py -q
```

Expected: FAIL because the four modules and split production files do not exist.

**Step 3: Do not weaken assertions**

Keep tests scoped to security and lifecycle contracts, not formatting or incidental HCL ordering.

**Checkpoint:** Do not commit unless explicitly authorized.

### Task 2: Implement protected state bootstrap

**Files:**
- Create: `infra/gcp/modules/state-bootstrap/versions.tf`
- Create: `infra/gcp/modules/state-bootstrap/variables.tf`
- Create: `infra/gcp/modules/state-bootstrap/main.tf`
- Create: `infra/gcp/modules/state-bootstrap/outputs.tf`
- Create: `infra/gcp/bootstrap/state/versions.tf`
- Create: `infra/gcp/bootstrap/state/variables.tf`
- Create: `infra/gcp/bootstrap/state/main.tf`
- Create: `infra/gcp/bootstrap/state/outputs.tf`
- Create: `infra/gcp/bootstrap/state/tests/state_bootstrap.tftest.hcl`

**Step 1: Write failing mock-provider tests**

Cover:

- `manage_state_bucket = false` creates no bucket.
- Enabling without a bucket name, labels, retention period, or soft-delete duration fails.
- `force_destroy = true` fails variable validation.
- Enabled configuration produces one bucket with enforced public-access prevention, uniform access, versioning, explicit retention, and explicit soft delete.

Use:

```hcl
mock_provider "google" {}

run "disabled_by_default" {
  command = plan

  variables {
    project_id = "clearcut-test"
  }

  assert {
    condition     = length(module.state_bucket) == 0
    error_message = "State bootstrap must manage no bucket by default."
  }
}
```

All native test plans are mock-provider plans only; never run `terraform plan` directly.

**Step 2: Run the test and verify RED**

Run from `infra/gcp/bootstrap/state`:

```bash
TF_DATA_DIR=/tmp/clearcut-terraform-bootstrap-test terraform test
```

Expected: FAIL because the root and module are incomplete.

**Step 3: Implement the module**

Use a single guarded bucket:

```hcl
resource "google_storage_bucket" "state" {
  count = var.enabled ? 1 : 0

  project                     = var.project_id
  name                        = var.bucket_name
  location                    = var.location
  storage_class               = "STANDARD"
  force_destroy               = false
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  labels                      = var.labels

  versioning {
    enabled = true
  }

  retention_policy {
    retention_period = var.retention_period_seconds
    is_locked        = false
  }

  soft_delete_policy {
    retention_duration_seconds = var.soft_delete_retention_seconds
  }

  lifecycle {
    prevent_destroy = true
  }
}
```

Validate that enabled inputs are explicit, durations are positive and within provider limits, labels contain `application`, `environment`, and `managed_by`, and `force_destroy` can never be true. Do not configure IAM or a backend.

**Step 4: Implement the bootstrap root**

The root pins Terraform `>= 1.16.0, < 1.17.0`, Google provider `~> 5.0`, and defaults `manage_state_bucket` to false. Pass explicit configuration to the child module and expose only the bucket name/self-link as nullable outputs.

**Step 5: Run GREEN tests**

Run:

```bash
terraform fmt -recursive . ../../modules/state-bootstrap
TF_DATA_DIR=/tmp/clearcut-terraform-bootstrap-test terraform init -backend=false
TF_DATA_DIR=/tmp/clearcut-terraform-bootstrap-test terraform test
TF_DATA_DIR=/tmp/clearcut-terraform-bootstrap-test terraform validate
```

Expected: all tests pass and validation reports success.

**Checkpoint:** Do not commit unless explicitly authorized.

### Task 3: Implement reviewed project-service activation safeguards

**Files:**
- Create: `infra/gcp/modules/project-services/versions.tf`
- Create: `infra/gcp/modules/project-services/variables.tf`
- Create: `infra/gcp/modules/project-services/main.tf`
- Create: `infra/gcp/modules/project-services/outputs.tf`
- Create or modify: `infra/gcp/environments/production/tests/foundation.tftest.hcl`
- Modify: `infra/gcp/environments/production/main.tf`
- Create: `infra/gcp/environments/production/variables.tf`
- Create: `infra/gcp/environments/production/versions.tf`

**Step 1: Add failing tests**

Test disabled defaults, rejection of unknown APIs, enabled creation only for the supplied allowlist, and rejection of `manage_project_services = true` when `acknowledge_service_identity_side_effects` remains false. The initial reviewed allowlist is data, not an activation instruction:

```hcl
[
  "artifactregistry.googleapis.com",
  "compute.googleapis.com",
  "iamcredentials.googleapis.com",
  "run.googleapis.com",
  "servicenetworking.googleapis.com",
  "sts.googleapis.com",
]
```

Do not include SQL, Tasks, Scheduler, Secret Manager, Vertex AI, logging, monitoring, trace, or budgets until their later phases.

**Step 2: Verify RED**

Run from production:

```bash
TF_DATA_DIR=/tmp/clearcut-terraform-production-test terraform test
```

Expected: FAIL because the module or the production acknowledgement safeguard is missing.

**Step 3: Implement the module**

```hcl
resource "google_project_service" "service" {
  for_each = var.enabled ? var.services : toset([])

  project                    = var.project_id
  service                    = each.value
  disable_on_destroy         = false
  disable_dependent_services = false
}
```

Validate `services` against an exact `allowed_services` set passed by the root. Output only the sorted enabled service names.

**Step 4: Split and wire the production root**

Move Terraform/provider constraints to `versions.tf`; move existing project/region variables to `variables.tf`; keep provider and module calls in `main.tf`. Add `manage_project_services = false`, empty requested-services defaults, and cross-variable validation requiring a nonempty approved subset when enabled.

Add `acknowledge_service_identity_side_effects = false` and reject `manage_project_services = true` unless it is explicitly true. Its description and failure message must state that enabling approved Google APIs may create Google-managed service agents/default identities and role bindings outside explicit Terraform IAM resources, requires IAM/org-policy review, and is not apply authorization. This foundation defines no ClearCut-authored explicit IAM resources, but it does not claim that API activation has no provider-managed IAM side effects. Activation remains deferred to identity/IAM review.

Do not add a backend.

**Step 5: Run GREEN tests**

Run formatter, backend-disabled init, `terraform test`, and `terraform validate` with external `TF_DATA_DIR`.

Expected: mock tests pass; disabled production creates no project-service resources, enabled production requires the acknowledgement, and the exact six-service allowlist remains unchanged.

**Checkpoint:** Do not commit unless explicitly authorized.

### Task 4: Implement Artifact Registry foundations

**Files:**
- Create: `infra/gcp/modules/artifact-registry/versions.tf`
- Create: `infra/gcp/modules/artifact-registry/variables.tf`
- Create: `infra/gcp/modules/artifact-registry/main.tf`
- Create: `infra/gcp/modules/artifact-registry/outputs.tf`
- Modify: `infra/gcp/environments/production/main.tf`
- Modify: `infra/gcp/environments/production/variables.tf`
- Modify: `infra/gcp/environments/production/outputs.tf`
- Modify: `infra/gcp/environments/production/tests/foundation.tftest.hcl`

**Step 1: Add failing tests**

Test that:

- management is disabled by default;
- enabled configuration requires exactly `site`, `web`, and `api` repository keys;
- repository IDs are environment-qualified and valid;
- format is Docker;
- production repositories have `prevent_destroy`;
- cleanup policy is explicit and starts in dry-run mode;
- no existing repository ID or import block is accepted.

**Step 2: Verify RED**

Run the production Terraform tests and confirm the Artifact Registry assertions fail.

**Step 3: Implement the module**

Create one `google_artifact_registry_repository` per supplied repository:

```hcl
resource "google_artifact_registry_repository" "repository" {
  for_each = var.enabled ? var.repositories : {}

  project                = var.project_id
  location               = var.location
  repository_id          = each.value.repository_id
  description            = each.value.description
  format                 = "DOCKER"
  mode                   = "STANDARD_REPOSITORY"
  labels                 = var.labels
  cleanup_policy_dry_run = true

  dynamic "cleanup_policies" {
    for_each = each.value.keep_count == null ? [] : [each.value.keep_count]
    content {
      id     = "retain-recent"
      action = "KEEP"
      most_recent_versions {
        keep_count = cleanup_policies.value
      }
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}
```

Require `keep_count` explicitly when enabled. Do not add a delete policy in this phase. Output repository IDs and canonical repository names only.

**Step 4: Wire production fail-closed composition**

Add `manage_artifact_registry = false`, empty repository configuration, and complete-input validation when enabled. Keep the module invocation at a stable address and pass the management flag through `enabled`; gate child resources with `for_each` so disabled defaults create zero resources without removing the configured `lifecycle { prevent_destroy = true }` protection.

**Step 5: Run GREEN tests**

Run production mock tests and validation. Confirm all repositories remain absent by default.

**Checkpoint:** Do not commit unless explicitly authorized.

### Task 5: Implement baseline private networking

**Files:**
- Create: `infra/gcp/modules/network-foundation/versions.tf`
- Create: `infra/gcp/modules/network-foundation/variables.tf`
- Create: `infra/gcp/modules/network-foundation/main.tf`
- Create: `infra/gcp/modules/network-foundation/outputs.tf`
- Modify: `infra/gcp/environments/production/main.tf`
- Modify: `infra/gcp/environments/production/variables.tf`
- Modify: `infra/gcp/environments/production/outputs.tf`
- Modify: `infra/gcp/environments/production/tests/foundation.tftest.hcl`

**Step 1: Add failing tests**

Test disabled defaults and enabled configuration for:

- custom-mode VPC;
- regional subnet with private Google access;
- subnet flow logs;
- reserved global internal VPC peering range;
- `servicenetworking.googleapis.com` private connection;
- explicit dependency on the reserved range;
- rejected equal/overlapping subnet and private-service CIDRs;
- no firewall, NAT, load balancer, serverless connector, or public route resource.

**Step 2: Verify RED**

Run production Terraform tests and confirm the network assertions fail before implementation.

**Step 3: Implement resources**

Use:

```hcl
resource "google_compute_network" "foundation" {
  count                   = var.enabled ? 1 : 0
  project                 = var.project_id
  name                    = var.network_name
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"
}

resource "google_compute_subnetwork" "foundation" {
  count                    = var.enabled ? 1 : 0
  project                  = var.project_id
  region                   = var.region
  name                     = var.subnet_name
  network                  = google_compute_network.foundation[0].self_link
  ip_cidr_range            = var.subnet_cidr
  private_ip_google_access = true

  log_config {
    aggregation_interval = "INTERVAL_10_MIN"
    flow_sampling        = 0.5
    metadata             = "INCLUDE_ALL_METADATA"
  }
}

resource "google_compute_global_address" "private_services" {
  count         = var.enabled ? 1 : 0
  project       = var.project_id
  name          = var.private_service_range_name
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = var.private_service_prefix_length
  network       = google_compute_network.foundation[0].self_link
}

resource "google_service_networking_connection" "private_services" {
  count                   = var.enabled ? 1 : 0
  network                 = google_compute_network.foundation[0].self_link
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_services[0].name]
  deletion_policy         = "ABANDON"
}
```

Use Terraform CIDR functions in validation to reject invalid or overlapping inputs. Do not invent production CIDRs; enabled configuration requires explicit values.

**Step 4: Wire production fail-closed composition**

Add `manage_network_foundation = false` and explicit nullable network configuration. Add a validated future `api_routing_mode` with only `deferred`, `external-load-balancer`, or `authenticated-web-proxy`; default it to `deferred` and create no routing resources.

**Step 5: Run GREEN tests**

Run production mock tests and validation. Confirm disabled production still creates no resources.

**Checkpoint:** Do not commit unless explicitly authorized.

### Task 6: Add existing-resource disposition and output contracts

**Files:**
- Modify: `infra/gcp/environments/production/variables.tf`
- Modify: `infra/gcp/environments/production/outputs.tf`
- Modify: `infra/gcp/environments/production/tests/foundation.tftest.hcl`

**Step 1: Add failing tests**

Test that dispositions accept only:

- `import-and-retain`;
- `import-and-migrate`;
- `replace`;
- `leave-unmanaged-temporarily`;
- `retire`.

Every entry must include resource type, exact resource identity, and nonempty rationale. Assert that dispositions do not alter module counts or create import blocks.

**Step 2: Verify RED**

Run production Terraform tests and confirm invalid/missing disposition fields are not yet rejected.

**Step 3: Implement documentary input validation**

Add a typed map variable and validation only. Do not pass it to resource arguments and do not add import blocks.

**Step 4: Add nonsensitive outputs**

Return nullable or empty values while disabled. Outputs may include service names, repository IDs, network/subnet self-links, and private-service range/connection identifiers. Mark no output sensitive unless it could genuinely reveal protected information; never output payloads or credentials.

**Step 5: Run GREEN tests**

Run production tests and validation.

**Checkpoint:** Do not commit unless explicitly authorized.

### Task 7: Lock providers and validate every root

**Files:**
- Create: `infra/gcp/bootstrap/state/.terraform.lock.hcl`
- Update only if required: `infra/gcp/environments/production/.terraform.lock.hcl`

**Step 1: Format-check all Terraform**

```bash
terraform fmt -check -recursive infra/gcp
```

Expected: exit 0.

**Step 2: Initialize bootstrap without a backend**

```bash
TF_DATA_DIR=/tmp/clearcut-terraform-bootstrap terraform init -backend=false
terraform providers lock -platform=darwin_arm64 -platform=linux_amd64
TF_DATA_DIR=/tmp/clearcut-terraform-bootstrap terraform validate
TF_DATA_DIR=/tmp/clearcut-terraform-bootstrap terraform test
```

Run from `infra/gcp/bootstrap/state`. Expected: initialization, validation, and mock tests pass; no backend or provider API is contacted.

**Step 3: Initialize production without a backend**

```bash
TF_DATA_DIR=/tmp/clearcut-terraform-production terraform init -backend=false
terraform providers lock -platform=darwin_arm64 -platform=linux_amd64
TF_DATA_DIR=/tmp/clearcut-terraform-production terraform validate
TF_DATA_DIR=/tmp/clearcut-terraform-production terraform test
```

Run from `infra/gcp/environments/production`. Expected: validation and mock tests pass with zero resources under defaults.

**Step 4: Inspect lockfiles**

Confirm both roots select Google provider 5.45.2 under `~> 5.0` and include checksums for macOS ARM64 and Linux AMD64. Do not commit child-module lockfiles.

**Step 5: Verify no generated artifacts entered the repository**

Confirm there are no `.terraform/`, `*.tfstate*`, `*.tfplan`, crash logs, or override files in Git status.

**Checkpoint:** Do not commit unless explicitly authorized.

### Task 8: Update documentation and run complete local verification

**Files:**
- Modify: `infra/gcp/README.md`
- Modify: `tests/foundation/test_deployment_boundaries.py`
- Reference: `docs/adr/0003-terraform-gcp-infrastructure.md`
- Reference: `docs/plans/2026-08-31-gcp-terraform-foundation-design.md`

**Step 1: Update truthful infrastructure status**

Document:

- the four implemented modules;
- production's disabled-by-default behavior;
- the separate unapplied state bootstrap root;
- existing resources remaining unmanaged;
- edge routing and identities remaining deferred;
- exact local validation commands and results;
- no plan, apply, import, backend initialization, provider API call, GCP mutation, or deployment evidence.

Keep the status `NO-GO / unapplied`.

**Step 2: Run focused safety tests**

```bash
uv run pytest tests/foundation/test_deployment_boundaries.py -q
```

Expected: all deployment-boundary tests pass.

**Step 3: Run full repository verification sequentially**

```bash
pnpm verify
```

Expected: toolchain, contract, foundation, architecture, and submission checks pass. Do not run concurrent pytest processes because repository tests share local SQLite defaults.

**Step 4: Run final Terraform verification**

Re-run formatter, backend-disabled validation, and mock tests for both roots. Fresh output is required before claiming completion.

**Step 5: Audit working-tree scope**

Use a scoped status command that excludes protected paths. Confirm only approved Terraform, documentation, tests, ADR/design/plan files, and the preserved salvage files appear. Run `git diff --check` on every changed file.

**Step 6: Report the boundary**

Report modules implemented, exact test counts, provider versions/lock platforms, and remaining deferred work. Explicitly state that no cloud action occurred.

**Checkpoint:** Leave changes uncommitted unless the user explicitly asks for a commit.

## Review checkpoints

Stop and request review if any of the following occurs:

- provider schema differs from the resources/attributes in this plan;
- validation requires a real provider call;
- any test attempts to read ADC or contact GCP;
- production defaults produce a resource;
- an existing resource would need adoption/import behavior;
- a protected retention, budget, IAM, routing, or deletion value must be invented;
- Terraform proposes a destructive convenience or lifecycle bypass;
- unrelated tracked files change.

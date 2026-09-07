# GCP Terraform Foundation Design

**Status:** Approved
**Date:** 2026-08-31
**Scope:** Provider-free Terraform foundation implementation; no plan, apply, import, backend initialization, provider API call, or GCP mutation

## Context

Before this phase, ClearCut selected Terraform CLI through ADR 0003, pinned Terraform 1.16.0, and validated an intentionally empty production root. The target hosted architecture eventually requires three independently deployable Cloud Run services, private data-plane services, keyless automation, durable storage and jobs, observability, and recovery controls.

This phase does not implement that full hosted system. It establishes the reusable Terraform foundation needed before identity, workload, data, queue, secret, and observability phases can be designed and reviewed safely.

Existing manually created GCP resources remain unmanaged. No module may assume ownership, add an import block, or imply that an existing resource matches the target design. Each existing resource must receive a separately reviewed disposition before later adoption, migration, replacement, temporary non-management, or retirement.

## Goals

- Implement capability-oriented Terraform modules for protected state bootstrap, project APIs, Artifact Registry, and baseline networking.
- Compose the environment modules from production behind explicit fail-closed authorization gates.
- Keep the production configuration valid while managing zero resources by default.
- Enforce destructive-change, public-access, naming, labeling, and configuration invariants locally.
- Add deterministic provider-free tests and validation.
- Preserve the no-apply boundary and truthful NO-GO status.

## Non-goals

- Applying, planning, importing, or mutating Terraform state.
- Contacting GCP APIs or changing cloud resources.
- Adopting any manually created GCP resource.
- Creating WIF, service accounts, IAM grants, or service-account keys.
- Enabling APIs, creating repositories, or creating networking without a later explicit authorization.
- Creating Cloud Run services/jobs, Cloud SQL, application buckets, Tasks/Scheduler, secrets, monitoring, alerts, or budgets.
- Selecting the production same-origin API routing design.
- Choosing protected retention, privacy, budget, queue, or escalation policy values.

## Chosen architecture

The foundation uses capability-oriented modules rather than one broad module or wrappers around individual resources.

### `state-bootstrap`

A dedicated module and separate bootstrap root define the future GCS Terraform state bucket. The design requires uniform bucket-level access, public-access prevention, object versioning, explicit retention and soft-delete inputs, auditability, no force-destroy, and production destruction protection.

The bootstrap root is not called by an environment root. State bootstrap has a different lifecycle and recovery boundary from application infrastructure. This phase validates its configuration only. It does not initialize local bootstrap state or create a remote backend.

### `project-services`

This module manages only an explicit allowlist of reviewed Google APIs. Unknown or broad service names are rejected. API management is disabled by default in production, and production rejects `manage_project_services = true` unless `acknowledge_service_identity_side_effects = true`. Destruction must not disable shared project APIs unexpectedly.

The Terraform configuration defines no ClearCut-authored explicit IAM resources, service accounts, or service-account keys. Enabling approved Google APIs may nevertheless create Google-managed service agents/default identities and role bindings outside explicit Terraform IAM resources. The acknowledgement records awareness of those side effects and the need for IAM/org-policy review; it is not apply authorization. API activation remains deferred to the identity/IAM review phase.

### `artifact-registry`

This module defines separate repositories for future site, web, and API images. It requires explicit repository configuration and environment-qualified names. Production repositories receive lifecycle protection. Cleanup behavior must be explicit and must not silently delete untagged or retained images.

Existing repositories remain unmanaged. This phase does not create image build or promotion workflows.

### `network-foundation`

This module defines a custom-mode VPC, regional subnet, reserved private-service range, and private service connection. CIDRs must be valid, distinct, and non-overlapping.

It does not create Cloud NAT, load balancing, serverless attachments, firewall exposure, public invoker access, or API routing. The same-origin boundary remains deliberately deferred. A validated routing-mode contract may reserve future choices without creating edge resources.

## Root composition

The production root composes `project-services`, `artifact-registry`, and `network-foundation`. Each resource-producing path requires an explicit management boolean such as:

- `manage_project_services`
- `manage_artifact_registry`
- `manage_network_foundation`

All management booleans default to `false`. Production defaults therefore manage zero resources.

Enabling a capability requires complete capability-specific configuration. Preconditions reject partial activation. The root passes only necessary values to each child module and exposes only nonsensitive identifiers.

The state bootstrap root remains separate and has its own explicit authorization input.

## Configuration contract

The production root has one regional source of truth: `region`, which is fixed to the approved `us-central1` location for this phase and is passed to the provider, Artifact Registry, and network foundation. Regional network naming derives from that value; there are no independent production repository-location or network-region inputs. The state-bootstrap root retains its separate GCS bucket `location` contract.

Every root requires or validates:

- explicit `project_id`;
- explicit environment identity;
- its approved production region or bootstrap storage location;
- deterministic naming prefix;
- required standard labels;
- fail-closed management booleans;
- exact capability-specific configuration when enabled;
- documentary existing-resource dispositions with exact resource identity and rationale.

There are no permissive fallbacks for production ownership, public access, retention, deletion, or adoption.

Module outputs may expose stable, nonsensitive identifiers such as enabled service names, repository IDs, VPC/subnet self-links, private-service range identity, private connection identity, and state bucket name. They must never expose secret payloads, credentials, tokens, signed URLs, or database passwords.

Modules do not read one another's state and do not create hidden IAM grants.

## Existing-resource boundary

A disposition record is documentation until a later import phase. This foundation accepts no import IDs that trigger Terraform import and includes no import blocks.

Allowed documentary dispositions are:

- import and retain;
- import and migrate;
- replace;
- leave unmanaged temporarily;
- retire.

Every record requires an exact resource identity and rationale. An absent disposition means the existing resource remains unmanaged and outside the target plan.

## Safety and lifecycle rules

- Production resources require environment-qualified names and standard labels.
- The state bucket requires uniform access, public-access prevention, versioning, no force-destroy, and destruction protection.
- Production Artifact Registry repositories require destruction protection.
- Cleanup policies are explicit and fail closed.
- The VPC uses custom subnet mode and no default-network dependency.
- Network ranges must not overlap.
- API management accepts only the reviewed allowlist and uses non-destructive disable behavior.
- No module creates service-account keys, broad project roles, public invoker grants, permissive firewalls, or hidden cross-capability resources.
- Private service connection dependencies are explicit.
- Unsafe input errors identify the exact invalid field and required correction.
- This phase adds no convenient break-glass variable for destructive behavior.

## Backend and local execution

The production backend remains absent. It will be added only after state bootstrap, recovery procedures, IAM identities, and apply authorization are reviewed.

Local validation uses an external `TF_DATA_DIR` and `terraform init -backend=false`. Local state, plan files, plugin caches, credentials, and crash logs must not enter the repository.

The provider lock remains portable across `darwin_arm64` and `linux_amd64`.

## Testing strategy

Implementation is test-first and provider-free.

Tests must prove:

- production defaults manage zero resources;
- each capability requires explicit authorization;
- incomplete enabled configuration fails with a specific message;
- unknown project APIs are rejected;
- state public access and force-destroy are prohibited;
- state versioning and destruction protection are present;
- repository lifecycle protection and explicit cleanup behavior are present;
- custom networking and private-service access are configured correctly;
- CIDRs cannot overlap;
- standard labels and deterministic naming are enforced;
- outputs are nonsensitive identifiers only;
- import blocks, service-account keys, broad IAM, public invokers, permissive firewalls, local state, and plan artifacts are absent.

Validation includes:

```bash
terraform fmt -check -recursive infra/gcp
TF_DATA_DIR=/tmp/clearcut-terraform-<root> terraform init -backend=false
TF_DATA_DIR=/tmp/clearcut-terraform-<root> terraform validate
terraform test
uv run pytest tests/foundation/test_deployment_boundaries.py -q
pnpm verify
```

Tests and validation must not contact GCP APIs or use paid providers.

## Completion criteria

This foundation phase is complete when:

1. The four capability modules and their roots exist and format correctly.
2. Backend-disabled initialization and validation pass for every root.
3. Provider-free Terraform and repository safety tests pass.
4. Production remains disabled by default and manages zero resources.
5. Existing resources remain unmanaged with no import behavior.
6. Documentation truthfully records that no plan, apply, import, backend initialization, provider API call, or GCP mutation occurred.
7. Git audit finds no local state, plan, `.terraform/`, credential, or protected-path changes.

## Deferred decisions and next phase

The next phase designs WIF and separate plan, deploy, migration, site, web, API, task-caller, and scheduler identities. It must not be bundled into this foundation change.

The following remain deferred for later accountable review:

- load balancer versus authenticated web proxy for same-origin API routing;
- exact existing-resource dispositions and imports;
- API activation authorization;
- production CIDRs and connectivity details;
- retention, soft-delete, and cleanup durations;
- budget amounts and alert thresholds;
- queue rates, retries, dead-letter policy, and schedules;
- Cloud SQL, storage, Tasks/Scheduler, secrets, workloads, and observability;
- any cloud plan or apply authorization.

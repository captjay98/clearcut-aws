# Portable Single-Service Deployment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace ClearCut's rejected three-service deployment contract with one immutable application image and safe Local, Portable Server, and GCP Starter profiles.

**Architecture:** FastAPI serves the Astro public site, TanStack workspace, and API from one origin and one image. Validated profile settings select typed storage, identity, secret, and job-dispatch adapters; GCP defaults to Cloud Run, GCS, Cloud Tasks, Secret Manager, and optional Cloud SQL while provider use and infrastructure mutation remain fail-closed.

**Tech Stack:** Python 3.12, FastAPI, Pydantic Settings, SQLAlchemy/PostgreSQL, Astro, TanStack Router, Bun/pnpm, Docker, Terraform 1.16, Google Cloud provider 5.45.2, GitHub Actions, pytest, Vitest, and Playwright.

---

## Guardrails

- Work only in the isolated `feat/portable-single-service` worktree.
- Never inspect or stage `.clearcut/`, `services/api/.clearcut/`, `semantic-review/`, or `.salvage-from-b/`.
- Stage exact files only. Preserve unrelated dirty and untracked work.
- Do not run Terraform plan/apply/import/state/destroy, `gcloud`, Cloud Build submission, or live Gemini/Parallel calls.
- Provider-free tests may use injected fake clients and Terraform mock providers.
- Keep Terraform resource management disabled by default.
- Keep evidence provenance, tenant scope, governed transactions, and legal-boundary behavior unchanged.

### Task 1: Establish the deployment-profile configuration contract

**Files:**

- Create: `services/api/src/clearcut/bootstrap/settings.py`
- Create: `services/api/src/clearcut/bootstrap/container.py`
- Create: `services/api/tests/bootstrap/test_deployment_profiles.py`
- Create: `services/api/tests/bootstrap/test_redacted_summary.py`
- Modify: `services/api/src/clearcut/main.py`
- Modify: `services/api/src/clearcut/database.py`

**Step 1: Write failing profile tests**

Test these exact defaults and validation rules:

```python
@pytest.mark.parametrize(
    ("profile", "storage", "dispatch", "auth", "secrets"),
    [
        ("local", "filesystem", "local", "builtin", "environment"),
        ("portable", "s3", "postgres", "builtin", "host"),
        ("gcp", "gcs", "cloud_tasks", "builtin", "secret_manager"),
    ],
)
def test_profile_defaults(profile, storage, dispatch, auth, secrets):
    settings = ClearcutSettings.model_validate({"profile": profile})
    assert settings.storage.adapter == storage
    assert settings.dispatch.adapter == dispatch
    assert settings.authentication.adapter == auth
    assert settings.secrets.backend == secrets
```

Add negative tests proving hosted profiles reject SQLite, ephemeral filesystem storage, missing PostgreSQL, incomplete Cloud Tasks/GCS settings, Firebase without project/audience, unknown adapters, and contradictory overrides. Assert the redacted summary includes only adapter names and secret-reference presence.

**Step 2: Run tests and confirm RED**

```bash
uv run pytest services/api/tests/bootstrap/test_deployment_profiles.py services/api/tests/bootstrap/test_redacted_summary.py -q
```

Expected: collection fails because `clearcut.bootstrap.settings` does not exist.

**Step 3: Implement minimal settings and composition types**

Create string enums `DeploymentProfile`, `StorageAdapter`, `DispatchAdapter`, `AuthenticationAdapter`, and `SecretBackend`. Add nested frozen Pydantic models and a `ClearcutSettings` model-level validator. Use a discriminated profile-default constructor rather than environment-dependent fallbacks. Add:

```python
@dataclass(frozen=True)
class RedactedDeploymentSummary:
    profile: str
    database_configured: bool
    storage_adapter: str
    dispatch_adapter: str
    authentication_adapter: str
    secret_backend: str
    paid_providers_enabled: tuple[str, ...]
```

Create `ApplicationContainer` and `build_application(settings)` without importing `clearcut.main`. Add `create_app(settings)` to `main.py` while preserving `app = create_app(ClearcutSettings.from_environment())`. Require explicit local SQLite selection; hosted settings may not inherit the database module's `/tmp/clearcut.db` fallback.

**Step 4: Run focused and compatibility tests**

```bash
uv run pytest services/api/tests/bootstrap/test_deployment_profiles.py services/api/tests/bootstrap/test_redacted_summary.py services/api/tests/architecture/test_migrated_runtime_schema.py -q
uv run ruff check services/api/src/clearcut/bootstrap services/api/tests/bootstrap
```

Expected: PASS.

**Step 5: Commit**

```bash
git add services/api/src/clearcut/bootstrap/settings.py services/api/src/clearcut/bootstrap/container.py services/api/src/clearcut/main.py services/api/src/clearcut/database.py services/api/tests/bootstrap/test_deployment_profiles.py services/api/tests/bootstrap/test_redacted_summary.py
git commit -m "feat(config): add fail-closed deployment profiles"
```

### Task 2: Serve Astro, TanStack, and API from one origin

**Files:**

- Create: `services/api/src/clearcut/static_delivery.py`
- Create: `services/api/tests/architecture/test_same_origin_delivery.py`
- Modify: `services/api/src/clearcut/main.py`
- Modify: `apps/web/vite.config.ts`
- Modify: `apps/web/src/router.tsx`
- Modify: `apps/site/src/layouts/PublicLayout.astro`
- Modify: `apps/site/src/pages/index.astro`
- Modify: `apps/site/tests/public_pages.test.ts`
- Modify: affected `apps/web/tests/e2e/*.spec.ts`
- Modify: `scripts/deployment_smoke.py`

**Step 1: Write failing same-origin tests**

Build temporary site/workspace distributions and install routes into a minimal FastAPI app. Assert:

```python
assert client.get("/").text == SITE_INDEX
assert client.get("/features").status_code == 200
assert client.get("/docs").status_code == 200
assert client.get("/app/").text == WORKSPACE_INDEX
assert client.get("/app/auth/sign-in").text == WORKSPACE_INDEX
assert client.get("/app/assets/app.js").text == "workspace-asset"
assert client.get("/_astro/site.js").text == "site-asset"
assert client.get("/api/v1/healthz").headers["content-type"].startswith("application/json")
assert client.get("/api/not-found").headers["content-type"].startswith("application/json")
```

Also test missing `index.html`, plain/encoded traversal, API docs at `/api/docs`, and OpenAPI at `/api/openapi.json`.

**Step 2: Run tests and confirm RED**

```bash
uv run pytest services/api/tests/architecture/test_same_origin_delivery.py -q
```

Expected: missing `install_same_origin_routes`.

**Step 3: Implement safe route installation**

Add:

```python
def install_same_origin_routes(
    app: FastAPI,
    *,
    site_dist: Path,
    workspace_dist: Path,
) -> None:
    """Install static routes after API routers, failing on invalid distributions."""
```

Use resolved-root containment checks and `FileResponse`; mount workspace assets only below `/app/assets` and Astro assets below `/_astro`. Configure FastAPI with `docs_url="/api/docs"`, `openapi_url="/api/openapi.json"`, and `redoc_url="/api/redoc"`. Make static serving explicitly enabled/disabled in profile settings; configured missing paths are startup errors.

Set Vite `base: "/app/"` and TanStack Router `basepath: "/app"`. Change public workspace links to `/app/auth/sign-in`. Update direct browser navigation paths without changing logical `Link to` route IDs.

**Step 4: Run focused builds and tests**

```bash
uv run pytest services/api/tests/architecture/test_same_origin_delivery.py tests/contracts/test_mounted_operation_ids.py -q
pnpm --filter clearcut-site test
pnpm --filter clearcut-site build
pnpm --filter clearcut-web build
```

Expected: PASS and both distributions build.

**Step 5: Commit**

```bash
git add services/api/src/clearcut/static_delivery.py services/api/src/clearcut/main.py services/api/tests/architecture/test_same_origin_delivery.py apps/web/vite.config.ts apps/web/src/router.tsx apps/site/src/layouts/PublicLayout.astro apps/site/src/pages/index.astro apps/site/tests/public_pages.test.ts apps/web/tests/e2e scripts/deployment_smoke.py
git commit -m "feat(runtime): serve public site workspace and api together"
```

### Task 3: Build one production image

**Files:**

- Modify: `Dockerfile`
- Modify: `docker-compose.yml`
- Modify: `cloudbuild.yaml`
- Modify: `tests/foundation/test_deployment_boundaries.py`
- Create: `tests/foundation/test_single_image_runtime.py`

**Step 1: Write failing container-source tests**

Require one root build to include `apps/site` and `apps/web`, copy both distributions, set stable paths, retain a non-root runtime, keep migrations out of startup, and reject separate `clearcut-site`, `clearcut-web`, and `clearcut-api` image contracts.

**Step 2: Run and confirm RED**

```bash
uv run pytest tests/foundation/test_deployment_boundaries.py tests/foundation/test_single_image_runtime.py -q
```

Expected: failures show the site distribution and singular image contract are absent.

**Step 3: Implement the image**

Use one frontend build stage and one Python runtime stage. Copy outputs to `/app/site-dist` and `/app/web-dist`; set `CLEARCUT_SITE_DIST_PATH` and `CLEARCUT_WORKSPACE_DIST_PATH`. Keep the explicit migration command available through the same image. Make Compose's `migrate`, `seed`, and `app` roles reuse the same image and keep only `app` persistent.

Convert Cloud Build to build `clearcut` as a release artifact or remove it from the deployment contract; delete all comments asserting three required images. Do not add deployment commands.

**Step 4: Build and smoke locally**

```bash
docker build --tag clearcut:test .
docker run --rm clearcut:test python -m alembic --help
docker compose config
```

Expected: image builds, migration CLI is present, and Compose resolves one application image.

**Step 5: Commit**

```bash
git add Dockerfile docker-compose.yml cloudbuild.yaml tests/foundation/test_deployment_boundaries.py tests/foundation/test_single_image_runtime.py
git commit -m "build(container): publish one clearcut application image"
```

### Task 4: Add provider-neutral object storage

**Files:**

- Modify: `services/api/src/clearcut/scripts/ports/object_storage.py`
- Create: `services/api/src/clearcut/scripts/adapters/gcs_storage.py`
- Create: `services/api/src/clearcut/scripts/adapters/s3_storage.py`
- Create: `services/api/tests/scripts/test_object_storage_contract.py`
- Modify: `services/api/src/clearcut/bootstrap/container.py`
- Modify: `services/api/pyproject.toml`
- Modify: `uv.lock`

**Step 1: Write a shared failing adapter contract**

Run the same tests against filesystem, in-memory, fake-GCS, and fake-S3 clients. Cover safe keys, byte fidelity, content type, missing object, idempotent delete, and typed provider errors. Assert construction performs no network request and no adapter falls back to filesystem.

**Step 2: Run and confirm RED**

```bash
uv run pytest services/api/tests/scripts/test_object_storage_contract.py -q
```

Expected: GCS/S3 adapter imports fail.

**Step 3: Add exact SDK dependencies and implementations**

```bash
uv add --exact google-cloud-storage google-cloud-tasks google-cloud-secret-manager boto3
```

Inject SDK-shaped clients into adapters. Translate provider exceptions into typed storage errors at the boundary. Receive bucket, endpoint, region, and credential references from validated settings; do not read environment variables inside adapters.

**Step 4: Run tests and supply-chain scan**

```bash
uv run pytest services/api/tests/scripts/test_object_storage_contract.py services/api/tests/scripts/test_import_pipeline_http.py -q
uv run ruff check services/api/src/clearcut/scripts services/api/tests/scripts
```

Run the available Semgrep supply-chain scan for the changed lockfile before completion.

**Step 5: Commit**

```bash
git add services/api/pyproject.toml uv.lock services/api/src/clearcut/scripts/ports/object_storage.py services/api/src/clearcut/scripts/adapters/gcs_storage.py services/api/src/clearcut/scripts/adapters/s3_storage.py services/api/src/clearcut/bootstrap/container.py services/api/tests/scripts/test_object_storage_contract.py
git commit -m "feat(storage): add gcs and s3 compatible adapters"
```

### Task 5: Add secret backends and redaction

**Files:**

- Create: `services/api/src/clearcut/bootstrap/secrets.py`
- Create: `services/api/tests/bootstrap/test_secret_backends.py`
- Modify: `services/api/src/clearcut/bootstrap/container.py`

**Step 1: Write failing tests**

Test environment/host resolution and injected Secret Manager clients. Assert missing references are typed failures and secret values never appear in `repr`, exceptions, JSON status, plans, or logs. Test local secret files require mode `0600`.

**Step 2: Confirm RED**

```bash
uv run pytest services/api/tests/bootstrap/test_secret_backends.py -q
```

**Step 3: Implement typed boundaries**

Add `SecretReference`, `SecretResolverPort`, and setup-only `SecretWriterPort`. Implement environment and injected Secret Manager adapters. Return values only to the composition root and expose redacted reference metadata elsewhere.

**Step 4: Run tests**

```bash
uv run pytest services/api/tests/bootstrap/test_secret_backends.py services/api/tests/bootstrap/test_redacted_summary.py -q
```

**Step 5: Commit**

```bash
git add services/api/src/clearcut/bootstrap/secrets.py services/api/src/clearcut/bootstrap/container.py services/api/tests/bootstrap/test_secret_backends.py
git commit -m "feat(secrets): add redacted profile secret backends"
```

### Task 6: Preserve server sessions while adding optional Firebase authentication

**Files:**

- Modify: `services/api/src/clearcut/identity/ports/identity_provider.py`
- Create: `services/api/src/clearcut/identity/application/authenticate.py`
- Create: `services/api/src/clearcut/identity/adapters/firebase_identity.py`
- Create: `services/api/tests/identity/test_identity_adapter_selection.py`
- Modify: `services/api/src/clearcut/identity/delivery/http.py`
- Modify: `services/api/src/clearcut/bootstrap/container.py`
- Modify: `packages/contracts/openapi.yaml`
- Modify: generated clients under `packages/contracts/generated/`

**Step 1: Write failing authentication-boundary tests**

Prove built-in is default; Firebase requires explicit selection and project/audience; issuer, audience, expiry, and subject are checked; email alone never identifies an external principal; setup creates no Firebase client call; and both successful adapters produce the same opaque revocable server session.

**Step 2: Confirm RED**

```bash
uv run pytest services/api/tests/identity/test_identity_adapter_selection.py services/api/tests/identity/test_sessions.py -q
```

**Step 3: Implement minimal adapter boundary**

Keep the current password hasher as `PasswordHasherPort`. Add `AuthenticationAdapterPort.authenticate(...) -> AuthenticationResult`. Verify Firebase ID tokens with injected `google-auth` verification, then map `(provider, subject)` to a ClearCut user before creating the normal hashed server session. Update the canonical OpenAPI contract first if request shapes change, then regenerate clients.

**Step 4: Verify identity and contract suites**

```bash
uv run pytest services/api/tests/identity -q
bun scripts/check-contract-drift.mjs
```

**Step 5: Commit**

```bash
git add services/api/src/clearcut/identity services/api/tests/identity/test_identity_adapter_selection.py services/api/src/clearcut/bootstrap/container.py packages/contracts/openapi.yaml packages/contracts/generated
git commit -m "feat(identity): add optional firebase session authentication"
```

### Task 7: Enforce paid-provider enablement and budgets

**Files:**

- Create: `services/api/src/clearcut/bootstrap/provider_policy.py`
- Create: `services/api/tests/bootstrap/test_paid_provider_controls.py`
- Modify: `services/api/src/clearcut/bootstrap/settings.py`
- Modify: `services/api/src/clearcut/detection/runtime_provider.py`
- Modify: `services/api/src/clearcut/research/runtime_provider.py`
- Modify: `services/api/src/clearcut/evaluation/runtime_provider.py`
- Modify: `services/api/tests/conformance/test_provider_selection.py`

**Step 1: Write failing zero-call tests**

Test disabled defaults, missing cost acknowledgement, missing credential reference, nonpositive request/result/token/concurrency limits, exhausted run budget, and semaphore enforcement. Recording fake clients must observe zero calls for every rejected case.

**Step 2: Confirm RED**

```bash
uv run pytest services/api/tests/bootstrap/test_paid_provider_controls.py services/api/tests/conformance/test_provider_selection.py -q
```

**Step 3: Implement run-scoped policy**

Add `PaidProviderSettings(enabled=False, cost_acknowledged=False, limits=...)`, `ProviderRunBudget`, and a bounded concurrency gate. Construct provider clients only after policy validation. Keep missing/unavailable providers as typed capability failures and preserve zero invented evidence.

**Step 4: Run provider conformance tests**

```bash
uv run pytest services/api/tests/bootstrap/test_paid_provider_controls.py services/api/tests/conformance/test_provider_selection.py services/api/tests/research services/api/tests/detection services/api/tests/evaluation -q
```

**Step 5: Commit**

```bash
git add services/api/src/clearcut/bootstrap/provider_policy.py services/api/src/clearcut/bootstrap/settings.py services/api/src/clearcut/detection/runtime_provider.py services/api/src/clearcut/research/runtime_provider.py services/api/src/clearcut/evaluation/runtime_provider.py services/api/tests/bootstrap/test_paid_provider_controls.py services/api/tests/conformance/test_provider_selection.py
git commit -m "feat(providers): require explicit bounded paid execution"
```

### Task 8: Add adaptive dispatch and the PostgreSQL worker

**Files:**

- Create: `services/api/src/clearcut/operations/ports/job_dispatcher.py`
- Create: `services/api/src/clearcut/operations/application/postgres_worker.py`
- Create: `services/api/src/clearcut/operations/adapters/postgres_dispatcher.py`
- Create: `services/api/src/clearcut/operations/runtime.py`
- Create: `services/api/tests/operations/test_dispatch_selection.py`
- Create: `services/api/tests/operations/test_postgres_worker.py`
- Modify: `services/api/src/clearcut/operations/ports/job_repository.py`
- Modify: `services/api/src/clearcut/operations/adapters/sql_job_repository.py`
- Modify: `services/api/src/clearcut/operations/application/run_job.py`
- Modify: `services/api/src/clearcut/operations/application/local_dispatcher.py`
- Modify: `services/api/src/clearcut/main.py`

**Step 1: Write failing dispatch-selection and worker tests**

Assert exact adapter mode/durability for each profile, no fallback, local one-worker validation, hosted PostgreSQL requirement, one claim per available row, `available_at` ordering, terminal/future-row skipping, lease audit, graceful stop, and visible interruption recovery.

**Step 2: Confirm RED**

```bash
uv run pytest services/api/tests/operations/test_dispatch_selection.py services/api/tests/operations/test_postgres_worker.py -q
```

**Step 3: Implement typed dispatch and worker runtime**

Add immutable `DispatchJob`, `DispatchResult`, `DispatchError`, and `JobDispatcherPort`. Split `RunJobService` into identifier claim plus common `run_claimed`. Add repository `claim_next_available` using PostgreSQL `FOR UPDATE SKIP LOCKED`, ordered by `available_at, id`, with current tenant/attempt/lease audit semantics. Implement `PostgresJobWorker.run_once()` and `serve(stop_event)` and select it only for Portable.

**Step 4: Run lease regressions**

```bash
uv run pytest services/api/tests/operations/test_dispatch_selection.py services/api/tests/operations/test_postgres_worker.py services/api/tests/operations/test_local_job_lifecycle.py services/api/tests/operations/test_job_http.py -q
```

Run the concurrent claim test only against disposable PostgreSQL; mark it explicitly when PostgreSQL is unavailable rather than claiming SQLite proves `SKIP LOCKED` behavior.

**Step 5: Commit**

```bash
git add services/api/src/clearcut/operations services/api/src/clearcut/main.py services/api/tests/operations/test_dispatch_selection.py services/api/tests/operations/test_postgres_worker.py
git commit -m "feat(jobs): add portable postgres worker dispatch"
```

### Task 9: Add durable Cloud Tasks handoff and protected execution

**Files:**

- Create: `services/api/src/clearcut/operations/adapters/cloud_tasks_dispatcher.py`
- Create: `services/api/src/clearcut/operations/application/reconcile_jobs.py`
- Create: `services/api/src/clearcut/operations/delivery/tasks_http.py`
- Create: `services/api/tests/operations/test_cloud_task_delivery.py`
- Create: `services/api/tests/operations/test_reconciliation.py`
- Create: `services/api/alembic/versions/0033_job_dispatch_outbox.py`
- Modify: `services/api/src/clearcut/operations/adapters/sql_job_repository.py`
- Modify: `services/api/src/clearcut/operations/runtime.py`
- Modify: `services/api/src/clearcut/main.py`
- Modify: `services/api/tests/architecture/test_migrated_runtime_schema.py`
- Modify: `packages/contracts/openapi.yaml`

**Step 1: Write failing handoff/auth/reconciliation tests**

Assert minimal task body, deterministic task name, exact target/audience/caller identity, duplicate delivery idempotency, completed-job no-op, issuer/audience/caller rejection before repository access, wrong-scope rejection, atomic job/audit/outbox rollback, pending state after task creation failure, bounded replay, and concurrent reconciler deduplication.

**Step 2: Confirm RED**

```bash
uv run pytest services/api/tests/operations/test_cloud_task_delivery.py services/api/tests/operations/test_reconciliation.py -q
```

**Step 3: Implement transactional outbox and Cloud Tasks adapter**

Add a tenant-owned dispatch outbox with unique deterministic dispatch identity. Persist enqueue/audit/outbox in one transaction. The dispatcher creates a Cloud Task from injected client configuration and marks the outbox delivered only after success. The protected route verifies Google issuer, configured audience, and dedicated service-account identity, then invokes `RunJobService.run` with identifiers only. Never trust authoritative payload state from the task body.

**Step 4: Run operation/schema/contract suites**

```bash
uv run pytest services/api/tests/operations services/api/tests/architecture/test_migrated_runtime_schema.py -q
bun scripts/check-contract-drift.mjs
```

**Step 5: Commit**

```bash
git add services/api/src/clearcut/operations services/api/alembic/versions/0033_job_dispatch_outbox.py services/api/src/clearcut/main.py services/api/tests/operations/test_cloud_task_delivery.py services/api/tests/operations/test_reconciliation.py services/api/tests/architecture/test_migrated_runtime_schema.py packages/contracts/openapi.yaml packages/contracts/generated
git commit -m "feat(jobs): add durable cloud tasks execution"
```

### Task 10: Implement guarded guided setup

**Files:**

- Create: `services/api/src/clearcut/setup/__init__.py`
- Create: `services/api/src/clearcut/setup/__main__.py`
- Create: `services/api/src/clearcut/setup/models.py`
- Create: `services/api/src/clearcut/setup/service.py`
- Create: `tests/foundation/test_guided_setup.py`
- Modify: `clearcut`
- Modify: `scripts/start_local.sh`
- Modify: `scripts/deploy_gcp.sh`

**Step 1: Write failing phase and approval tests**

Test `configure`, `validate`, `plan`, `approve`, `deploy`, `verify`, and `status --json`. Assert canonical SHA-256 plan digest, exact approval binding, stale/changed plan rejection, distinct Cloud SQL/provider acknowledgements, noninteractive missing-input failure, drift reporting, `0600` local secrets, and zero cloud/provider mutations during configure/validate.

**Step 2: Confirm RED**

```bash
uv run pytest tests/foundation/test_guided_setup.py -q
```

**Step 3: Implement stdlib CLI and typed setup service**

Use `argparse` plus the shared Pydantic settings. Saved plans contain schema version, profile/adapters, intended actions, cost-sensitive flags, secret references, revision/image digest, and canonical plan digest—never secret values. Keep `clearcut` as a thin delegator. Preserve GCP deployment fail-closed behavior until an exact approved saved plan exists.

**Step 4: Run setup and shell checks**

```bash
uv run pytest tests/foundation/test_guided_setup.py -q
./clearcut status --json
./clearcut validate --profile local --non-interactive
```

Expected: provider-free output, no cloud mutation, no secret values.

**Step 5: Commit**

```bash
git add services/api/src/clearcut/setup tests/foundation/test_guided_setup.py clearcut scripts/start_local.sh scripts/deploy_gcp.sh
git commit -m "feat(setup): add guarded deployment workflow"
```

### Task 11: Replace three repositories with one Artifact Registry contract

**Files:**

- Modify: `infra/gcp/modules/artifact-registry/{main,variables,outputs}.tf`
- Modify: `infra/gcp/environments/production/{main,variables,outputs}.tf`
- Modify: `infra/gcp/environments/production/tests/foundation.tftest.hcl`
- Modify: `tests/foundation/test_deployment_boundaries.py`
- Modify: `infra/gcp/README.md`

**Step 1: Change tests to require singular outputs**

Require one repository ID/name `clearcut`, reject `site`, `web`, and `api` keys, retain `prevent_destroy`, KEEP-only cleanup, dry-run cleanup, explicit project/location, and zero-resource defaults.

**Step 2: Confirm RED**

```bash
uv run pytest tests/foundation/test_deployment_boundaries.py -q
TF_DATA_DIR="$(mktemp -d)" terraform -chdir=infra/gcp/environments/production test -no-color
```

**Step 3: Implement singular module/root contract**

Replace role maps with singular `repository_id`, `repository_description`, `artifact_repository_id`, and `artifact_repository_name`. Keep `manage_artifact_registry=false`. Add no import/state movement.

**Step 4: Validate Terraform without backend/provider calls**

```bash
terraform fmt -recursive infra/gcp
TF_DATA_DIR="$(mktemp -d)" terraform -chdir=infra/gcp/environments/production init -backend=false -input=false -no-color
TF_DATA_DIR="$TF_DATA_DIR" terraform -chdir=infra/gcp/environments/production validate -no-color
TF_DATA_DIR="$TF_DATA_DIR" terraform -chdir=infra/gcp/environments/production test -no-color
```

Expected: validate/tests pass with mock providers and no cloud mutation.

**Step 5: Commit**

```bash
git add infra/gcp/modules/artifact-registry infra/gcp/environments/production infra/gcp/README.md tests/foundation/test_deployment_boundaries.py
git commit -m "refactor(infra): use one clearcut image repository"
```

### Task 12: Add fail-closed GCP Starter capability modules

**Files:**

- Create: `infra/gcp/modules/gcs-object-storage/`
- Create: `infra/gcp/modules/cloud-tasks-dispatch/`
- Create: `infra/gcp/modules/runtime-secrets/`
- Create: `infra/gcp/modules/cloud-run-application/`
- Create: `infra/gcp/modules/cloud-sql-postgresql/`
- Create: `infra/gcp/modules/firebase-auth/`
- Modify: `infra/gcp/environments/production/{main,variables,outputs}.tf`
- Modify: `infra/gcp/environments/production/tests/foundation.tftest.hcl`
- Modify: `tests/foundation/test_deployment_boundaries.py`

**Step 1: Add one failing native-test block per capability**

Each module/root flag defaults disabled and emits no resources. Enabled tests require complete typed inputs and exact resources. Cloud SQL additionally requires `acknowledge_cloud_sql_costs=true`; Firebase is explicit opt-in. Secret values are prohibited from variables/outputs. Add only APIs needed by enabled capabilities to the existing exact allowlist.

**Step 2: Confirm RED**

```bash
TF_DATA_DIR="$(mktemp -d)" terraform -chdir=infra/gcp/environments/production test -no-color
uv run pytest tests/foundation/test_deployment_boundaries.py -q
```

**Step 3: Implement modules incrementally**

Order: runtime secret metadata, GCS bucket, Cloud Tasks queue/OIDC caller, one Cloud Run service, optional Cloud SQL, optional Firebase. Every managed durable resource uses deletion protection or `prevent_destroy` where supported. The Cloud Run module consumes one digest-pinned `clearcut` image and defaults min instances to zero. Existing PostgreSQL remains valid; Cloud SQL is never automatically selected.

**Step 4: Validate all Terraform roots**

```bash
terraform fmt -check -recursive infra/gcp
TF_DATA_DIR="$(mktemp -d)" terraform -chdir=infra/gcp/environments/production init -backend=false -input=false -no-color
TF_DATA_DIR="$TF_DATA_DIR" terraform -chdir=infra/gcp/environments/production validate -no-color
TF_DATA_DIR="$TF_DATA_DIR" terraform -chdir=infra/gcp/environments/production test -no-color
TF_DATA_DIR="$(mktemp -d)" terraform -chdir=infra/gcp/bootstrap/state init -backend=false -input=false -no-color
TF_DATA_DIR="$TF_DATA_DIR" terraform -chdir=infra/gcp/bootstrap/state validate -no-color
TF_DATA_DIR="$TF_DATA_DIR" terraform -chdir=infra/gcp/bootstrap/state test -no-color
```

**Step 5: Commit**

```bash
git add infra/gcp/modules infra/gcp/environments/production tests/foundation/test_deployment_boundaries.py
git commit -m "feat(infra): add gated gcp starter capabilities"
```

### Task 13: Convert build, migration, deployment, and Terraform workflows

**Files:**

- Modify: `.github/workflows/build.yml`
- Modify: `.github/workflows/migrate.yml`
- Modify: `.github/workflows/deploy.yml`
- Modify: `.github/workflows/ci.yml`
- Create: `.github/workflows/terraform-plan.yml`
- Create: `.github/workflows/terraform-apply.yml`
- Modify: `tests/foundation/test_deployment_boundaries.py`

**Step 1: Write failing workflow-source contracts**

Require one `image_digest`, exact `/clearcut@sha256:<64 hex>`, one migration attestation bound to digest/environment, one `gcloud run deploy clearcut --no-traffic`, non-mutating candidate smoke for `/`, `/app/`, `/api/v1/healthz`, unauthenticated task-route rejection, one promotion, WIF/keyless auth, and no legacy digest inputs. Require apply to consume an exact saved-plan artifact/checksum behind a protected environment and never re-plan.

**Step 2: Confirm RED**

```bash
uv run pytest tests/foundation/test_deployment_boundaries.py -q
```

**Step 3: Implement workflows**

Build the root image once on authorized release events, publish one immutable digest with SBOM/provenance metadata, run migrations from that digest, attest the successful migration, deploy one no-traffic candidate, verify it, and promote once. Keep ordinary PR CI provider-free. Separate Terraform plan and apply; do not add apply to CI or deployment workflows.

**Step 4: Re-run source contracts**

```bash
uv run pytest tests/foundation/test_deployment_boundaries.py -q
```

**Step 5: Commit**

```bash
git add .github/workflows tests/foundation/test_deployment_boundaries.py
git commit -m "ci(release): deploy one digest through guarded promotion"
```

### Task 14: Migrate the submission contract without fabricating evidence

**Files:**

- Modify: `tests/submission/test_submission_gate.py`
- Modify: `tests/submission/test_public_claims.py`
- Modify: `scripts/verify-submission.mjs`
- Modify: `docs/submission/manifest.yaml`

**Step 1: Write failing singular-release tests**

Add positive and negative fixtures requiring:

```yaml
submission:
  release:
    image_digest: registry.example/clearcut@sha256:<64-hex>
    deployment_profile: gcp-starter
    migration_run_id: <attestation-id>
    cloud_run_revision: <revision>
    service_url: https://example.run.app
```

Reject legacy `image_digests.site/web/api`, `hosted_services.site/web/api`, tags, wrong image names, missing migration evidence, and fabricated GO values. Keep the repository's real manifest truthfully NO-GO until evidence exists.

**Step 2: Confirm RED**

```bash
uv run pytest tests/submission/test_submission_gate.py tests/submission/test_public_claims.py -q
```

**Step 3: Implement verifier and manifest schema**

Require one exact immutable `clearcut` reference, one HTTPS URL, one revision, migration evidence, selected production adapters, and spending-control proof when paid providers are enabled. Do not insert real-looking placeholders.

**Step 4: Run submission verification**

```bash
bun scripts/verify-submission.mjs
uv run pytest tests/submission -q
```

**Step 5: Commit**

```bash
git add tests/submission scripts/verify-submission.mjs docs/submission/manifest.yaml
git commit -m "refactor(submission): verify one immutable release"
```

### Task 15: Align architecture, ADRs, and canonical agent guidance

**Files:**

- Create: `docs/adr/0004-portable-single-service-deployment.md`
- Modify: `docs/adr/0003-terraform-gcp-infrastructure.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/EXTENSIONS.md`
- Modify: `README.md`
- Modify: `infra/gcp/README.md`
- Modify: `.agents/guide-header.md`
- Modify: `.agents/steering/{tech,structure,product-map,agents}.md`
- Modify: `.agents/personas/devops-engineer.md`
- Modify: `.agents/memory/project-memory.md`
- Modify: `.agents/includes/shared/delegation-pattern.md`
- Regenerate: `AGENTS.md` and render-manifest-owned outputs

**Step 1: Add stale-topology tests/search assertions**

Extend public-claim and deployment-boundary tests to reject normative three-service/three-image claims while allowing historical explanation in ADR 0004 and the superseded section of ADR 0003.

**Step 2: Confirm RED**

```bash
uv run pytest tests/foundation/test_deployment_boundaries.py tests/submission/test_public_claims.py -q
```

**Step 3: Update canonical guidance**

Document the one-service topology, profile matrix, adaptive dispatch, provider-neutral storage, server-session auth, spending gates, single-digest rollout, and fail-closed setup. Mark only the topology portion of ADR 0003 superseded; preserve its Terraform/state/auth decisions. Update canonical `.agents` sources, never generated `AGENTS.md` directly.

**Step 4: Regenerate and validate**

```bash
AGENTS_STRICT=1 bun .agents/scripts/build.mjs
bun .agents/scripts/lint.mjs
bun .agents/scripts/verify.mjs
bun .agents/scripts/signoff.mjs
pnpm exec prettier --check docs README.md .agents
```

**Step 5: Commit**

```bash
git add docs README.md infra/gcp/README.md .agents AGENTS.md
git commit -m "docs(architecture): adopt portable single-service deployment"
```

### Task 16: Run complete provider-free verification and review

**Files:**

- Modify only files required to fix verified regressions.

**Step 1: Run static, contract, and application gates**

```bash
uv run ruff check .
uv run pyright
bun scripts/check-contract-drift.mjs
pnpm verify
```

Expected: all pass. Warnings must be understood and unchanged or reduced.

**Step 2: Run frontend builds and browser matrix**

```bash
pnpm --filter clearcut-site build
pnpm --filter clearcut-web build
pnpm --filter clearcut-web test:e2e
```

Expected: public and workspace routes pass across configured engines/viewports.

**Step 3: Run Terraform provider-free gates**

```bash
terraform fmt -check -recursive infra/gcp
TF_DATA_DIR="$(mktemp -d)" terraform -chdir=infra/gcp/environments/production init -backend=false -input=false -no-color
TF_DATA_DIR="$TF_DATA_DIR" terraform -chdir=infra/gcp/environments/production validate -no-color
TF_DATA_DIR="$TF_DATA_DIR" terraform -chdir=infra/gcp/environments/production test -no-color
```

Expected: validation and mock-provider tests pass; no plan/apply/state mutation occurs.

**Step 4: Run container/profile smoke**

```bash
docker build --tag clearcut:test .
docker compose up -d --build
uv run python scripts/deployment_smoke.py --url http://127.0.0.1:8000
docker compose down
```

Expected: `/`, `/app/`, `/api/v1/healthz`, `/api/openapi.json`, built-in session flow, storage persistence, and local dispatch pass. No paid provider call occurs.

**Step 5: Request independent code review and commit fixes**

Use the code-review workflow on the complete branch diff. Fix all confirmed critical/high issues, rerun affected gates, and commit exact files:

```bash
git add <exact-fixed-files>
git commit -m "fix(deployment): resolve single-service review findings"
```

Do not create an empty commit when no fixes are needed.

## Completion Criteria

- One `clearcut` image contains both browser surfaces and FastAPI.
- One public Cloud Run service is the GCP runtime default.
- The migration job uses the same immutable digest.
- Local, Portable, and GCP profile validation is explicit and fail-closed.
- GCP defaults to GCS, Cloud Tasks, Secret Manager, and optional acknowledged Cloud SQL.
- R2/S3-compatible storage and existing PostgreSQL remain supported.
- Built-in opaque server sessions remain default; Firebase is optional.
- Paid providers default disabled and require bounded acknowledged enablement.
- Terraform manages zero resources by default and no cloud mutation occurred during implementation.
- Build/deploy/submission contracts require one digest and one service URL.
- Canonical docs and generated agent guidance no longer enforce three services.
- Provider-free tests, builds, browser checks, Terraform mock tests, and container smoke pass.

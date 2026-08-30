# Google Cloud Infrastructure (ClearCut)

Terraform/OpenTofu definitions for production, staging, and development deployments on Google Cloud Platform.

## Services Architecture
* **Cloud Run Services**:
  * `clearcut-site`: Public Astro documentation and static portal.
  * `clearcut-web`: TanStack Start evidence workspace.
  * `clearcut-api`: FastAPI backend with modular monolith domain architecture.
* **Storage & Persistence**:
  * Cloud SQL PostgreSQL (AlloyDB-compatible, automated backups, PITR enabled).
  * Cloud Storage bucket with CMEK and strict retention policies.
* **Background Tasks & Scheduling**:
  * Cloud Tasks (private task queue for async jobs and re-scans).
  * Cloud Scheduler (periodic evidence watch rechecks).
* **Security & Observability**:
  * Secret Manager for API keys and JWT secrets.
  * OpenTelemetry tracing & Cloud Logging.

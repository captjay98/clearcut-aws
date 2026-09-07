resource "google_artifact_registry_repository" "repository" {
  count = var.enabled ? 1 : 0

  project       = var.project_id
  location      = var.location
  repository_id = var.repository.repository_id
  description   = var.repository.description
  format        = "DOCKER"
  mode          = "STANDARD_REPOSITORY"
  labels        = var.repository.labels

  cleanup_policy_dry_run = true

  cleanup_policies {
    id     = "keep-most-recent"
    action = "KEEP"

    most_recent_versions {
      keep_count = var.repository.keep_count
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}

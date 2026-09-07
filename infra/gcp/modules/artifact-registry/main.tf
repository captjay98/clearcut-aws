resource "google_artifact_registry_repository" "repository" {
  for_each = var.enabled ? var.repositories : {}

  project       = var.project_id
  location      = var.location
  repository_id = each.value.repository_id
  description   = each.value.description
  format        = "DOCKER"
  mode          = "STANDARD_REPOSITORY"
  labels        = each.value.labels

  cleanup_policy_dry_run = true

  cleanup_policies {
    id     = "keep-most-recent"
    action = "KEEP"

    most_recent_versions {
      keep_count = each.value.keep_count
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}

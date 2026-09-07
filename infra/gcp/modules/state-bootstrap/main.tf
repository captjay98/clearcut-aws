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

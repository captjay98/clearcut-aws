module "state_bucket" {
  source = "../../modules/state-bootstrap"

  enabled                       = var.manage_state_bucket
  project_id                    = var.project_id
  bucket_name                   = var.bucket_name
  location                      = var.location
  labels                        = var.labels
  retention_period_seconds      = var.retention_period_seconds
  soft_delete_retention_seconds = var.soft_delete_retention_seconds
  force_destroy                 = var.force_destroy
}

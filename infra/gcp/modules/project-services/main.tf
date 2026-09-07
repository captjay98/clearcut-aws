resource "google_project_service" "service" {
  for_each = var.enabled ? var.requested_services : toset([])

  project = var.project_id
  service = each.value

  disable_on_destroy         = false
  disable_dependent_services = false
}

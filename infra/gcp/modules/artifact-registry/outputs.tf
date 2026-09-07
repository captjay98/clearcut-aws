output "repository_ids" {
  description = "Repository resource IDs keyed by deployment image role."
  value       = { for key, repository in google_artifact_registry_repository.repository : key => repository.id }
}

output "repository_names" {
  description = "Repository names keyed by deployment image role."
  value       = { for key, repository in google_artifact_registry_repository.repository : key => repository.name }
}

output "location" {
  description = "Configured repository location, or null while disabled."
  value       = var.enabled ? var.location : null
}

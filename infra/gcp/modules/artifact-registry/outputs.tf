output "repository_id" {
  description = "Single repository resource ID, or null while disabled."
  value       = one(google_artifact_registry_repository.repository[*].id)
}

output "repository_name" {
  description = "Single repository name, or null while disabled."
  value       = one(google_artifact_registry_repository.repository[*].name)
}

output "location" {
  description = "Configured repository location, or null while disabled."
  value       = var.enabled ? var.location : null
}

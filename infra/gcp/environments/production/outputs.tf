output "enabled_services" {
  description = "Sorted names of project services managed as enabled."
  value       = module.project_services.enabled_services
}

output "artifact_repository_ids" {
  description = "Artifact Registry repository resource IDs keyed by site, web, and api."
  value       = module.artifact_registry.repository_ids
}

output "artifact_repository_names" {
  description = "Artifact Registry repository names keyed by site, web, and api."
  value       = module.artifact_registry.repository_names
}

output "network_id" {
  description = "Production VPC resource ID, or null while disabled."
  value       = module.network_foundation.network_id
}

output "network_name" {
  description = "Production VPC name, or null while disabled."
  value       = module.network_foundation.network_name
}

output "subnet_id" {
  description = "Production subnet resource ID, or null while disabled."
  value       = module.network_foundation.subnet_id
}

output "subnet_name" {
  description = "Production subnet name, or null while disabled."
  value       = module.network_foundation.subnet_name
}

output "private_service_range_id" {
  description = "Private service range resource ID, or null while disabled."
  value       = module.network_foundation.private_service_range_id
}

output "private_service_range_name" {
  description = "Private service range name, or null while disabled."
  value       = module.network_foundation.private_service_range_name
}

output "service_networking_connection_id" {
  description = "Service networking connection resource ID, or null while disabled."
  value       = module.network_foundation.service_networking_connection_id
}

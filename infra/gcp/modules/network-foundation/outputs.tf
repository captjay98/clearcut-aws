output "network_id" {
  description = "Custom-mode VPC resource ID, or null while disabled."
  value       = try(google_compute_network.network[0].id, null)
}

output "network_name" {
  description = "Custom-mode VPC name, or null while disabled."
  value       = try(google_compute_network.network[0].name, null)
}

output "subnet_id" {
  description = "Regional subnet resource ID, or null while disabled."
  value       = try(google_compute_subnetwork.subnet[0].id, null)
}

output "subnet_name" {
  description = "Regional subnet name, or null while disabled."
  value       = try(google_compute_subnetwork.subnet[0].name, null)
}

output "private_service_range_id" {
  description = "Private service range resource ID, or null while disabled."
  value       = try(google_compute_global_address.private_service_range[0].id, null)
}

output "private_service_range_name" {
  description = "Private service range name, or null while disabled."
  value       = try(google_compute_global_address.private_service_range[0].name, null)
}

output "service_networking_connection_id" {
  description = "Service networking connection resource ID, or null while disabled."
  value       = try(google_service_networking_connection.private_service_connection[0].id, null)
}

output "region" {
  description = "Configured subnet region, or null while disabled."
  value       = var.enabled ? var.region : null
}

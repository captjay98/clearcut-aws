output "enabled_services" {
  description = "Sorted names of the project services managed as enabled."
  value       = sort([for service in google_project_service.service : service.service])
}

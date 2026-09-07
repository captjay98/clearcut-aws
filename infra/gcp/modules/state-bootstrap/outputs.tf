output "bucket_name" {
  description = "Name of the managed state bucket, or null when disabled."
  value       = try(google_storage_bucket.state[0].name, null)
}

output "bucket_self_link" {
  description = "Self-link of the managed state bucket, or null when disabled."
  value       = try(google_storage_bucket.state[0].self_link, null)
}

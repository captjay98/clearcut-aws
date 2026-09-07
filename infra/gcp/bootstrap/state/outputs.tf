output "bucket_name" {
  description = "Name of the managed state bucket, or null when management is disabled."
  value       = module.state_bucket.bucket_name
}

output "bucket_self_link" {
  description = "Self-link of the managed state bucket, or null when management is disabled."
  value       = module.state_bucket.bucket_self_link
}

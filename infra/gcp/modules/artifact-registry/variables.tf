variable "enabled" {
  type        = bool
  description = "Whether management of the three deployment image repositories is explicitly authorized."
  default     = false
}

variable "project_id" {
  type        = string
  description = "Explicit authorized GCP project ID."

  validation {
    condition     = length(trimspace(var.project_id)) > 0
    error_message = "project_id must name an explicitly authorized GCP project."
  }
}

variable "environment" {
  type        = string
  description = "Environment qualifier embedded in every repository ID."
  default     = null
  nullable    = true

  validation {
    condition = !var.enabled || try(
      length(trimspace(var.environment)) > 0 &&
      can(regex("^[a-z][a-z0-9-]*[a-z0-9]$", var.environment)),
      false
    )
    error_message = "environment must be an explicit valid lowercase qualifier when enabled."
  }
}

variable "location" {
  type        = string
  description = "Explicit Artifact Registry repository location."
  default     = null
  nullable    = true

  validation {
    condition     = !var.enabled || try(length(trimspace(var.location)) > 0, false)
    error_message = "location must be explicit when Artifact Registry management is enabled."
  }
}

variable "repositories" {
  type = map(object({
    description   = string
    keep_count    = number
    labels        = map(string)
    repository_id = string
  }))
  description = "Complete site, web, and api Docker repository configuration."
  default     = {}

  validation {
    condition     = !var.enabled || toset(keys(var.repositories)) == toset(["site", "web", "api"])
    error_message = "repositories must contain exactly the site, web, and api keys when enabled."
  }

  validation {
    condition = !var.enabled || try(alltrue([
      for key, repository in var.repositories :
      repository.repository_id == "clearcut-${var.environment}-${key}" &&
      can(regex("^[a-z][a-z0-9-]{2,61}[a-z0-9]$", repository.repository_id)) &&
      length(trimspace(repository.description)) > 0 &&
      repository.keep_count >= 1 &&
      repository.keep_count == floor(repository.keep_count) &&
      alltrue([
        for required_label in ["application", "environment", "managed_by"] :
        contains(keys(repository.labels), required_label) && length(trimspace(repository.labels[required_label])) > 0
      ]) &&
      repository.labels.application == "clearcut" &&
      repository.labels.environment == var.environment &&
      repository.labels.managed_by == "terraform"
    ]), false)
    error_message = "Each repository must have its exact environment-qualified ID, a nonempty description, a positive integer keep_count, and canonical application=clearcut, environment=<environment>, and managed_by=terraform labels."
  }
}

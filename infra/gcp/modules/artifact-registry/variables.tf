variable "enabled" {
  type        = bool
  description = "Whether management of the single clearcut deployment image repository is explicitly authorized."
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
  description = "Environment qualifier recorded in repository labels."
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

variable "repository" {
  type = object({
    description   = string
    keep_count    = number
    labels        = map(string)
    repository_id = string
  })
  description = "Single clearcut Docker repository configuration when management is enabled."
  default     = null
  nullable    = true

  validation {
    condition     = !var.enabled || var.repository != null
    error_message = "repository must be explicitly configured when enabled."
  }

  validation {
    condition = var.repository == null || try(
      var.repository.repository_id == "clearcut" &&
      length(trimspace(var.repository.description)) > 0 &&
      var.repository.keep_count >= 1 &&
      var.repository.keep_count == floor(var.repository.keep_count) &&
      var.repository.labels.application == "clearcut" &&
      var.repository.labels.managed_by == "terraform" &&
      (!var.enabled || var.repository.labels.environment == var.environment),
      false
    )
    error_message = "repository must use ID clearcut, a nonempty description, a positive integer keep_count, and canonical application=clearcut, managed_by=terraform, and environment=<environment> labels when enabled."
  }
}

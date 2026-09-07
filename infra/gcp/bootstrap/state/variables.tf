variable "project_id" {
  type        = string
  description = "Explicit authorized GCP project ID for state bootstrap."

  validation {
    condition     = length(trimspace(var.project_id)) > 0
    error_message = "project_id must name an explicitly authorized GCP project."
  }
}

variable "manage_state_bucket" {
  type        = bool
  description = "Whether state bucket management is explicitly authorized."
  default     = false
}

variable "bucket_name" {
  type        = string
  description = "Globally unique name of the dedicated Terraform state bucket."
  default     = null
  nullable    = true

  validation {
    condition     = !var.manage_state_bucket || try(length(trimspace(var.bucket_name)) > 0, false)
    error_message = "bucket_name must be explicitly set to a non-empty value when manage_state_bucket is true."
  }
}

variable "location" {
  type        = string
  description = "GCS location for the dedicated Terraform state bucket."
  default     = "US"

  validation {
    condition     = !var.manage_state_bucket || length(trimspace(var.location)) > 0
    error_message = "location must be a non-empty GCS location when manage_state_bucket is true."
  }
}

variable "labels" {
  type        = map(string)
  description = "State bucket labels, including application, environment, and managed_by."
  default     = {}

  validation {
    condition = !var.manage_state_bucket || alltrue([
      for required_label in ["application", "environment", "managed_by"] :
      try(length(trimspace(var.labels[required_label])) > 0, false)
    ])
    error_message = "labels must explicitly include non-empty application, environment, and managed_by values when manage_state_bucket is true."
  }
}

variable "retention_period_seconds" {
  type        = number
  description = "Explicit object retention period in whole seconds, from 1 second through 100 years."
  default     = null
  nullable    = true

  validation {
    condition = !var.manage_state_bucket || try(
      var.retention_period_seconds >= 1 &&
      var.retention_period_seconds <= 3155760000 &&
      floor(var.retention_period_seconds) == var.retention_period_seconds,
      false,
    )
    error_message = "retention_period_seconds must be explicitly set to a whole number from 1 through 3155760000 when manage_state_bucket is true."
  }
}

variable "soft_delete_retention_seconds" {
  type        = number
  description = "Explicit soft-delete retention duration in whole seconds, from 7 through 90 days."
  default     = null
  nullable    = true

  validation {
    condition = !var.manage_state_bucket || try(
      var.soft_delete_retention_seconds >= 604800 &&
      var.soft_delete_retention_seconds <= 7776000 &&
      floor(var.soft_delete_retention_seconds) == var.soft_delete_retention_seconds,
      false,
    )
    error_message = "soft_delete_retention_seconds must be explicitly set to a whole number from 604800 through 7776000 when manage_state_bucket is true."
  }
}

variable "force_destroy" {
  type        = bool
  description = "Destructive bucket teardown control; true is always rejected."
  default     = false

  validation {
    condition     = !var.force_destroy
    error_message = "force_destroy must remain false for the Terraform state bucket."
  }
}

variable "enabled" {
  type        = bool
  description = "Whether project-service activation is explicitly authorized."
  default     = false
}

variable "project_id" {
  type        = string
  description = "Explicit authorized GCP project ID whose services may be activated."

  validation {
    condition     = length(trimspace(var.project_id)) > 0
    error_message = "project_id must name an explicitly authorized GCP project."
  }
}

variable "allowed_services" {
  type        = set(string)
  description = "Caller-owned allowlist of Google Cloud service names that may be activated."
}

variable "requested_services" {
  type        = set(string)
  description = "Approved Google Cloud service names requested for activation."
  default     = []

  validation {
    condition     = length(setsubtract(var.requested_services, var.allowed_services)) == 0
    error_message = "requested_services must be a subset of allowed_services."
  }

  validation {
    condition     = !var.enabled || length(var.requested_services) > 0
    error_message = "requested_services must contain at least one approved service when enabled is true."
  }
}

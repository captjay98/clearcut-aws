variable "project_id" {
  type        = string
  description = "Explicit authorized GCP project ID; production project selection must be explicit."

  validation {
    condition     = length(trimspace(var.project_id)) > 0
    error_message = "project_id must name an explicitly authorized GCP project."
  }
}

variable "region" {
  type        = string
  description = "Approved GCP region for this production phase."
  default     = "us-central1"

  validation {
    condition     = var.region == "us-central1"
    error_message = "region must be us-central1 for this production phase."
  }
}

variable "acknowledge_service_identity_side_effects" {
  type        = bool
  description = "Acknowledges that enabling approved Google APIs may create Google-managed service agents/default identities and role bindings outside explicit Terraform IAM resources and requires IAM/org-policy review; this is not apply authorization."
  default     = false
}

variable "manage_project_services" {
  type        = bool
  description = "Whether activation of the requested project services is explicitly authorized after acknowledging provider-managed identity and IAM side effects."
  default     = false

  validation {
    condition     = !var.manage_project_services || var.acknowledge_service_identity_side_effects
    error_message = "manage_project_services=true requires acknowledge_service_identity_side_effects=true because enabling approved Google APIs may create Google-managed service agents/default identities and role bindings outside explicit Terraform IAM resources and requires IAM/org-policy review; this acknowledgement is not apply authorization."
  }
}

variable "requested_services" {
  type        = set(string)
  description = "Approved Google Cloud service names requested for activation."
  default     = []

  validation {
    condition     = !var.manage_project_services || length(var.requested_services) > 0
    error_message = "requested_services must contain at least one approved service when manage_project_services is true."
  }
}

variable "manage_artifact_registry" {
  type        = bool
  description = "Whether management of the single production deployment image repository is explicitly authorized."
  default     = false
}

variable "artifact_registry_environment" {
  type        = string
  description = "Environment qualifier recorded in the managed repository labels."
  default     = null
  nullable    = true

  validation {
    condition     = var.artifact_registry_environment == null || var.artifact_registry_environment == "production"
    error_message = "artifact_registry_environment must be production when specified."
  }
}

variable "artifact_repository" {
  type = object({
    description   = string
    keep_count    = number
    labels        = map(string)
    repository_id = string
  })
  description = "Single clearcut repository configuration when management is enabled."
  default     = null
  nullable    = true

  validation {
    condition = var.artifact_repository == null || try(
      var.artifact_repository.repository_id == "clearcut" &&
      length(trimspace(var.artifact_repository.description)) > 0 &&
      var.artifact_repository.keep_count >= 1 &&
      var.artifact_repository.keep_count == floor(var.artifact_repository.keep_count) &&
      var.artifact_repository.labels.application == "clearcut" &&
      var.artifact_repository.labels.environment == "production" &&
      var.artifact_repository.labels.managed_by == "terraform",
      false
    )
    error_message = "artifact_repository must use ID clearcut, a nonempty description, a positive integer keep_count, and canonical application=clearcut, environment=production, and managed_by=terraform labels."
  }
}

variable "manage_network_foundation" {
  type        = bool
  description = "Whether creation of the production network foundation is explicitly authorized."
  default     = false
}

variable "api_routing_mode" {
  type        = string
  description = "Documentary future API routing mode; this foundation creates no API routing resources."
  default     = "deferred"

  validation {
    condition = contains([
      "authenticated-web-proxy",
      "deferred",
      "external-load-balancer",
    ], var.api_routing_mode)
    error_message = "api_routing_mode must be deferred, external-load-balancer, or authenticated-web-proxy."
  }
}

variable "network_name" {
  type        = string
  description = "Explicit custom-mode VPC name when network management is enabled."
  default     = null
  nullable    = true

  validation {
    condition     = var.network_name == null || var.network_name == "clearcut-production-network"
    error_message = "network_name must be clearcut-production-network when specified."
  }
}

variable "subnet_name" {
  type        = string
  description = "Explicit regional subnet name when network management is enabled."
  default     = null
  nullable    = true

  validation {
    condition     = var.subnet_name == null || var.subnet_name == "clearcut-production-${var.region}"
    error_message = "subnet_name must be clearcut-production-<region> for the approved production region when specified."
  }
}

variable "subnet_cidr" {
  type        = string
  description = "Explicit primary subnet IPv4 CIDR when network management is enabled."
  default     = null
  nullable    = true
}

variable "private_service_range_name" {
  type        = string
  description = "Explicit private service range name when network management is enabled."
  default     = null
  nullable    = true

  validation {
    condition     = var.private_service_range_name == null || var.private_service_range_name == "clearcut-production-private-services"
    error_message = "private_service_range_name must be clearcut-production-private-services when specified."
  }
}

variable "private_service_cidr" {
  type        = string
  description = "Explicit non-overlapping private service IPv4 CIDR when network management is enabled."
  default     = null
  nullable    = true
}


variable "resource_dispositions" {
  type = map(object({
    disposition   = string
    resource_type = string
    resource_id   = string
    rationale     = optional(string)
  }))
  description = "Documentary-only reviewed dispositions for exact existing resource IDs; this input never drives resources or import blocks."
  default     = {}

  validation {
    condition = alltrue([
      for disposition in values(var.resource_dispositions) :
      contains([
        "import-and-retain",
        "import-and-migrate",
        "replace",
        "leave-unmanaged-temporarily",
        "retire",
      ], disposition.disposition)
    ])
    error_message = "Each resource disposition must use one of the five approved documentary values."
  }

  validation {
    condition = alltrue([
      for disposition in values(var.resource_dispositions) :
      try(
        contains([
          "artifact-registry-repository",
          "cloud-run-service",
          "cloud-sql-instance",
          "secret-manager-secret",
          "storage-bucket",
        ], disposition.resource_type) &&
        disposition.resource_id == trimspace(disposition.resource_id) &&
        !can(regex("[?*]", disposition.resource_id)) &&
        length(trimspace(disposition.rationale)) > 0 &&
        (
          disposition.resource_type == "cloud-run-service" ? (
            can(regex("^projects/[^/?*]+/locations/[^/?*]+/services/[^/?*]+$", disposition.resource_id)) &&
            split("/", disposition.resource_id)[1] == var.project_id
            ) : disposition.resource_type == "cloud-sql-instance" ? (
            can(regex("^projects/[^/?*]+/instances/[^/?*]+$", disposition.resource_id)) &&
            split("/", disposition.resource_id)[1] == var.project_id
            ) : disposition.resource_type == "artifact-registry-repository" ? (
            can(regex("^projects/[^/?*]+/locations/[^/?*]+/repositories/[^/?*]+$", disposition.resource_id)) &&
            split("/", disposition.resource_id)[1] == var.project_id
            ) : disposition.resource_type == "secret-manager-secret" ? (
            can(regex("^projects/[^/?*]+/secrets/[^/?*]+$", disposition.resource_id)) &&
            split("/", disposition.resource_id)[1] == var.project_id
          ) : disposition.resource_type == "storage-bucket" ?
          can(regex("^projects/_/buckets/[^/?*]+$", disposition.resource_id)) :
          false
        ),
        false
      )
    ])
    error_message = "Each disposition requires a supported resource_type, its exact canonical non-wildcard resource_id in the authorized project where encoded, and a nonempty rationale."
  }
}

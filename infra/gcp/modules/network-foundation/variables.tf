variable "enabled" {
  type        = bool
  description = "Whether creation of the production network foundation is explicitly authorized."
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

variable "api_routing_mode" {
  type        = string
  description = "Documentary future API routing mode; no routing resources are created by this module."
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
  description = "Explicit custom-mode VPC name."
  default     = null
  nullable    = true

  validation {
    condition = !var.enabled || try(
      var.network_name == "clearcut-production-network" &&
      can(regex("^[a-z](?:[-a-z0-9]{0,61}[a-z0-9])?$", var.network_name)),
      false
    )
    error_message = "network_name must be clearcut-production-network when enabled."
  }
}

variable "region" {
  type        = string
  description = "Explicit region for the subnet."
  default     = null
  nullable    = true

  validation {
    condition     = !var.enabled || try(length(trimspace(var.region)) > 0, false)
    error_message = "region must be explicit when network foundation management is enabled."
  }
}

variable "subnet_name" {
  type        = string
  description = "Explicit regional subnet name."
  default     = null
  nullable    = true

  validation {
    condition     = !var.enabled || var.subnet_name == "clearcut-production-${coalesce(var.region, "invalid")}"
    error_message = "subnet_name must be clearcut-production-<region> for the configured region when enabled."
  }
}

variable "subnet_cidr" {
  type        = string
  description = "Explicit primary IPv4 CIDR for the regional subnet."
  default     = null
  nullable    = true

  validation {
    condition = !var.enabled || try(
      can(cidrhost(var.subnet_cidr, 0)) &&
      cidrhost(var.subnet_cidr, 0) == split("/", var.subnet_cidr)[0],
      false
    )
    error_message = "subnet_cidr must be an explicit valid canonical IPv4 CIDR when enabled."
  }
}

variable "private_service_range_name" {
  type        = string
  description = "Explicit name for the private service access allocation."
  default     = null
  nullable    = true

  validation {
    condition = !var.enabled || try(
      var.private_service_range_name == "clearcut-production-private-services" &&
      can(regex("^[a-z](?:[-a-z0-9]{0,61}[a-z0-9])?$", var.private_service_range_name)),
      false
    )
    error_message = "private_service_range_name must be clearcut-production-private-services when enabled."
  }
}

variable "private_service_cidr" {
  type        = string
  description = "Explicit non-overlapping IPv4 CIDR allocated for private service access."
  default     = null
  nullable    = true

  validation {
    condition = !var.enabled || try(
      can(cidrhost(var.private_service_cidr, 0)) &&
      cidrhost(var.private_service_cidr, 0) == split("/", var.private_service_cidr)[0],
      false
    )
    error_message = "private_service_cidr must be an explicit valid canonical IPv4 CIDR when enabled."
  }

  validation {
    condition = !var.enabled || try(
      sum([
        for index, octet in split(".", cidrhost(var.private_service_cidr, -1)) :
        tonumber(octet) * pow(256, 3 - index)
        ]) < sum([
        for index, octet in split(".", cidrhost(var.subnet_cidr, 0)) :
        tonumber(octet) * pow(256, 3 - index)
      ]) ||
      sum([
        for index, octet in split(".", cidrhost(var.subnet_cidr, -1)) :
        tonumber(octet) * pow(256, 3 - index)
        ]) < sum([
        for index, octet in split(".", cidrhost(var.private_service_cidr, 0)) :
        tonumber(octet) * pow(256, 3 - index)
      ]),
      false
    )
    error_message = "private_service_cidr and subnet_cidr must not overlap."
  }
}

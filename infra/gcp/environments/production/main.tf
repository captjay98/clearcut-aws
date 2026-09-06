# Production environment Terraform entry point.
# This file currently configures only provider requirements and explicit inputs;
# it does not provision ClearCut resources.
terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

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
  description = "GCP region selected for the reviewed deployment."
  default     = "us-central1"
}

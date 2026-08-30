# Production Environment Terraform Entry Point
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
  description = "GCP Project ID"
  default     = "clearcut-prod"
}

variable "region" {
  type        = string
  description = "GCP Region"
  default     = "us-central1"
}

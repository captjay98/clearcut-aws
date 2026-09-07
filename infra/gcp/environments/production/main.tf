locals {
  allowed_project_services = toset([
    "artifactregistry.googleapis.com",
    "compute.googleapis.com",
    "iamcredentials.googleapis.com",
    "run.googleapis.com",
    "servicenetworking.googleapis.com",
    "sts.googleapis.com",
  ])
}

provider "google" {
  project = var.project_id
  region  = var.region
}

module "project_services" {
  source = "../../modules/project-services"

  allowed_services   = local.allowed_project_services
  enabled            = var.manage_project_services
  project_id         = var.project_id
  requested_services = var.requested_services
}

module "artifact_registry" {
  source = "../../modules/artifact-registry"

  depends_on = [module.project_services]

  enabled     = var.manage_artifact_registry
  environment = var.artifact_registry_environment
  location    = var.region
  project_id  = var.project_id
  repository  = var.artifact_repository
}

module "network_foundation" {
  source = "../../modules/network-foundation"

  depends_on = [module.project_services]

  api_routing_mode           = var.api_routing_mode
  enabled                    = var.manage_network_foundation
  network_name               = var.network_name
  private_service_cidr       = var.private_service_cidr
  private_service_range_name = var.private_service_range_name
  project_id                 = var.project_id
  region                     = var.region
  subnet_cidr                = var.subnet_cidr
  subnet_name                = var.subnet_name
}

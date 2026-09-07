mock_provider "google" {}

run "production_is_disabled_by_default" {
  command = plan

  variables {
    project_id = "clearcut-test"
  }

  assert {
    condition     = length(module.project_services.enabled_services) == 0
    error_message = "Production must enable no project services by default."
  }

  assert {
    condition = (
      module.artifact_registry.repository_ids == {} &&
      module.artifact_registry.repository_names == {} &&
      module.network_foundation.network_id == null &&
      module.network_foundation.network_name == null &&
      module.network_foundation.subnet_id == null &&
      module.network_foundation.subnet_name == null &&
      module.network_foundation.private_service_range_id == null &&
      module.network_foundation.private_service_range_name == null &&
      module.network_foundation.service_networking_connection_id == null
    )
    error_message = "Production defaults must create no repositories or network resources and return only empty or null outputs."
  }
}

run "production_forwards_root_region_to_regional_modules" {
  command = plan

  variables {
    artifact_registry_environment = "production"
    artifact_repositories = {
      site = {
        description   = "ClearCut production site deployment images"
        keep_count    = 20
        labels        = { application = "clearcut", environment = "production", managed_by = "terraform" }
        repository_id = "clearcut-production-site"
      }
      web = {
        description   = "ClearCut production web deployment images"
        keep_count    = 20
        labels        = { application = "clearcut", environment = "production", managed_by = "terraform" }
        repository_id = "clearcut-production-web"
      }
      api = {
        description   = "ClearCut production api deployment images"
        keep_count    = 30
        labels        = { application = "clearcut", environment = "production", managed_by = "terraform" }
        repository_id = "clearcut-production-api"
      }
    }
    manage_artifact_registry   = true
    manage_network_foundation  = true
    network_name               = "clearcut-production-network"
    private_service_cidr       = "10.40.16.0/20"
    private_service_range_name = "clearcut-production-private-services"
    project_id                 = "clearcut-test"
    region                     = "us-central1"
    subnet_cidr                = "10.40.0.0/20"
    subnet_name                = "clearcut-production-us-central1"
  }

  assert {
    condition = (
      module.artifact_registry.location == var.region &&
      module.network_foundation.region == var.region
    )
    error_message = "Production must pass its single approved root region to Artifact Registry and network foundation."
  }
}

run "production_rejects_nonapproved_region" {
  command = plan

  variables {
    project_id = "clearcut-test"
    region     = "us-east1"
  }

  expect_failures = [var.region]
}

run "disabled_module_manages_no_services" {
  command = plan

  module {
    source = "../../modules/project-services"
  }

  variables {
    allowed_services = [
      "artifactregistry.googleapis.com",
      "compute.googleapis.com",
      "iamcredentials.googleapis.com",
      "run.googleapis.com",
      "servicenetworking.googleapis.com",
      "sts.googleapis.com",
    ]
    project_id = "clearcut-test"
  }

  assert {
    condition     = length(google_project_service.service) == 0
    error_message = "Disabled project-service management must manage no services."
  }

  assert {
    condition     = length(output.enabled_services) == 0
    error_message = "Disabled project-service management must output no enabled services."
  }
}

run "requested_service_outside_caller_allowlist_is_rejected" {
  command = plan

  module {
    source = "../../modules/project-services"
  }

  variables {
    allowed_services   = ["run.googleapis.com"]
    enabled            = true
    project_id         = "clearcut-test"
    requested_services = ["artifactregistry.googleapis.com"]
  }

  expect_failures = [var.requested_services]
}

run "enabled_without_services_is_rejected" {
  command = plan

  module {
    source = "../../modules/project-services"
  }

  variables {
    allowed_services = [
      "artifactregistry.googleapis.com",
      "compute.googleapis.com",
      "iamcredentials.googleapis.com",
      "run.googleapis.com",
      "servicenetworking.googleapis.com",
      "sts.googleapis.com",
    ]
    enabled    = true
    project_id = "clearcut-test"
  }

  expect_failures = [var.requested_services]
}

run "production_rejects_project_service_management_without_side_effect_acknowledgement" {
  command = plan

  variables {
    manage_project_services = true
    project_id              = "clearcut-test"
    requested_services      = ["run.googleapis.com"]
  }

  expect_failures = [var.manage_project_services]
}

run "production_forwards_exact_allowed_services" {
  command = plan

  variables {
    acknowledge_service_identity_side_effects = true
    manage_project_services                   = true
    project_id                                = "clearcut-test"
    requested_services = [
      "artifactregistry.googleapis.com",
      "compute.googleapis.com",
      "iamcredentials.googleapis.com",
      "run.googleapis.com",
      "servicenetworking.googleapis.com",
      "sts.googleapis.com",
    ]
  }

  assert {
    condition = local.allowed_project_services == toset([
      "artifactregistry.googleapis.com",
      "compute.googleapis.com",
      "iamcredentials.googleapis.com",
      "run.googleapis.com",
      "servicenetworking.googleapis.com",
      "sts.googleapis.com",
    ])
    error_message = "Production must allow exactly the six approved project services."
  }

  assert {
    condition = module.project_services.enabled_services == sort([
      "artifactregistry.googleapis.com",
      "compute.googleapis.com",
      "iamcredentials.googleapis.com",
      "run.googleapis.com",
      "servicenetworking.googleapis.com",
      "sts.googleapis.com",
    ])
    error_message = "Production must pass its exact six-service allowlist to the project-services module."
  }
}

run "enabled_module_manages_exact_requested_subset" {
  command = plan

  module {
    source = "../../modules/project-services"
  }

  variables {
    allowed_services = [
      "artifactregistry.googleapis.com",
      "compute.googleapis.com",
      "run.googleapis.com",
    ]
    enabled    = true
    project_id = "clearcut-test"
    requested_services = [
      "run.googleapis.com",
      "artifactregistry.googleapis.com",
    ]
  }

  assert {
    condition = toset(keys(google_project_service.service)) == toset([
      "artifactregistry.googleapis.com",
      "run.googleapis.com",
    ])
    error_message = "Enabled project-service management must manage exactly the requested subset."
  }

  assert {
    condition = alltrue([
      for service in values(google_project_service.service) :
      !service.disable_on_destroy && !service.disable_dependent_services
    ])
    error_message = "Managed services must remain enabled when Terraform resources are removed."
  }

  assert {
    condition = output.enabled_services == sort([
      "artifactregistry.googleapis.com",
      "run.googleapis.com",
    ])
    error_message = "The enabled-services output must contain only sorted requested service names."
  }
}


run "disabled_artifact_registry_manages_no_repositories" {
  command = plan

  module {
    source = "../../modules/artifact-registry"
  }

  variables {
    project_id = "clearcut-test"
  }

  assert {
    condition     = length(google_artifact_registry_repository.repository) == 0
    error_message = "Disabled Artifact Registry management must manage no repositories."
  }

  assert {
    condition     = output.repository_ids == {} && output.repository_names == {}
    error_message = "Disabled Artifact Registry management must output empty repository maps."
  }
}

run "enabled_artifact_registry_manages_exact_protected_repositories" {
  command = plan

  module {
    source = "../../modules/artifact-registry"
  }

  variables {
    enabled     = true
    environment = "production"
    location    = "us-central1"
    project_id  = "clearcut-test"
    repositories = {
      site = {
        description   = "ClearCut production site deployment images"
        keep_count    = 20
        labels        = { application = "clearcut", environment = "production", managed_by = "terraform" }
        repository_id = "clearcut-production-site"
      }
      web = {
        description   = "ClearCut production web deployment images"
        keep_count    = 20
        labels        = { application = "clearcut", environment = "production", managed_by = "terraform" }
        repository_id = "clearcut-production-web"
      }
      api = {
        description   = "ClearCut production api deployment images"
        keep_count    = 30
        labels        = { application = "clearcut", environment = "production", managed_by = "terraform" }
        repository_id = "clearcut-production-api"
      }
    }
  }

  assert {
    condition     = toset(keys(google_artifact_registry_repository.repository)) == toset(["site", "web", "api"])
    error_message = "Artifact Registry must manage exactly site, web, and api repositories."
  }

  assert {
    condition = alltrue([
      for key, repository in google_artifact_registry_repository.repository :
      repository.format == "DOCKER" &&
      repository.mode == "STANDARD_REPOSITORY" &&
      repository.location == "us-central1" &&
      repository.repository_id == "clearcut-production-${key}" &&
      repository.description == "ClearCut production ${key} deployment images" &&
      repository.cleanup_policy_dry_run &&
      repository.labels.environment == "production" &&
      length(repository.cleanup_policies) == 1 &&
      one(repository.cleanup_policies).action == "KEEP" &&
      one(repository.cleanup_policies).id == "keep-most-recent" &&
      one(one(repository.cleanup_policies).most_recent_versions).keep_count > 0
    ])
    error_message = "Artifact repositories must be environment-qualified protected STANDARD Docker repositories with one explicit KEEP policy."
  }

  assert {
    condition = (
      toset(keys(output.repository_ids)) == toset(["site", "web", "api"]) &&
      toset(keys(output.repository_names)) == toset(["site", "web", "api"])
    )
    error_message = "Artifact Registry outputs must expose only repository IDs and names keyed by site, web, and api."
  }

  assert {
    condition = alltrue(flatten([
      for repository in values(google_artifact_registry_repository.repository) : [
        for policy in repository.cleanup_policies : policy.action != "DELETE"
      ]
    ]))
    error_message = "Artifact repositories must not define DELETE cleanup policies."
  }
}

run "artifact_registry_rejects_incomplete_enabled_configuration" {
  command = plan

  module {
    source = "../../modules/artifact-registry"
  }

  variables {
    enabled    = true
    project_id = "clearcut-test"
  }

  expect_failures = [var.environment, var.location]
}

run "artifact_registry_rejects_missing_repository_configuration" {
  command = plan

  module {
    source = "../../modules/artifact-registry"
  }

  variables {
    enabled     = true
    environment = "production"
    location    = "us-central1"
    project_id  = "clearcut-test"
  }

  expect_failures = [var.repositories]
}

run "artifact_registry_rejects_blank_repository_descriptions" {
  command = plan

  module {
    source = "../../modules/artifact-registry"
  }

  variables {
    enabled     = true
    environment = "production"
    location    = "us-central1"
    project_id  = "clearcut-test"
    repositories = {
      site = {
        description   = "ClearCut production site deployment images"
        keep_count    = 20
        labels        = { application = "clearcut", environment = "production", managed_by = "terraform" }
        repository_id = "clearcut-production-site"
      }
      web = {
        description   = "   "
        keep_count    = 20
        labels        = { application = "clearcut", environment = "production", managed_by = "terraform" }
        repository_id = "clearcut-production-web"
      }
      api = {
        description   = "ClearCut production api deployment images"
        keep_count    = 20
        labels        = { application = "clearcut", environment = "production", managed_by = "terraform" }
        repository_id = "clearcut-production-api"
      }
    }
  }

  expect_failures = [var.repositories]
}

run "artifact_registry_rejects_unsafe_repository_keys" {
  command = plan

  module {
    source = "../../modules/artifact-registry"
  }

  variables {
    enabled     = true
    environment = "production"
    location    = "us-central1"
    project_id  = "clearcut-test"
    repositories = {
      worker = {
        description   = "ClearCut production worker deployment images"
        keep_count    = 20
        labels        = { application = "clearcut", environment = "production", managed_by = "terraform" }
        repository_id = "clearcut-production-worker"
      }
    }
  }

  expect_failures = [var.repositories]
}

run "artifact_registry_rejects_unqualified_repository_ids" {
  command = plan

  module {
    source = "../../modules/artifact-registry"
  }

  variables {
    enabled     = true
    environment = "production"
    location    = "us-central1"
    project_id  = "clearcut-test"
    repositories = {
      site = {
        description   = "ClearCut production site deployment images"
        keep_count    = 20
        labels        = { application = "clearcut", environment = "production", managed_by = "terraform" }
        repository_id = "site"
      }
      web = {
        description   = "ClearCut production web deployment images"
        keep_count    = 20
        labels        = { application = "clearcut", environment = "production", managed_by = "terraform" }
        repository_id = "web"
      }
      api = {
        description   = "ClearCut production api deployment images"
        keep_count    = 20
        labels        = { application = "clearcut", environment = "production", managed_by = "terraform" }
        repository_id = "api"
      }
    }
  }

  expect_failures = [var.repositories]
}


run "disabled_network_foundation_manages_no_resources" {
  command = plan

  module {
    source = "../../modules/network-foundation"
  }

  variables {
    project_id = "clearcut-test"
  }

  assert {
    condition = (
      length(google_compute_network.network) == 0 &&
      length(google_compute_subnetwork.subnet) == 0 &&
      length(google_compute_global_address.private_service_range) == 0 &&
      length(google_service_networking_connection.private_service_connection) == 0
    )
    error_message = "Disabled network foundation management must create zero resources."
  }

  assert {
    condition = (
      output.network_id == null && output.network_name == null &&
      output.subnet_id == null && output.subnet_name == null &&
      output.private_service_range_id == null && output.private_service_range_name == null &&
      output.service_networking_connection_id == null
    )
    error_message = "Disabled network foundation outputs must be null."
  }
}

run "enabled_network_foundation_has_private_regional_settings" {
  command = plan

  module {
    source = "../../modules/network-foundation"
  }

  variables {
    enabled                    = true
    network_name               = "clearcut-production-network"
    private_service_cidr       = "10.40.16.0/20"
    private_service_range_name = "clearcut-production-private-services"
    project_id                 = "clearcut-test"
    region                     = "us-central1"
    subnet_cidr                = "10.40.0.0/20"
    subnet_name                = "clearcut-production-us-central1"
  }

  assert {
    condition = (
      google_compute_network.network[0].auto_create_subnetworks == false &&
      google_compute_network.network[0].routing_mode == "REGIONAL"
    )
    error_message = "The VPC must be custom-mode and regional without mutating default routes."
  }

  assert {
    condition = (
      google_compute_subnetwork.subnet[0].region == "us-central1" &&
      google_compute_subnetwork.subnet[0].ip_cidr_range == "10.40.0.0/20" &&
      google_compute_subnetwork.subnet[0].private_ip_google_access == true &&
      google_compute_subnetwork.subnet[0].log_config[0].aggregation_interval == "INTERVAL_10_MIN" &&
      google_compute_subnetwork.subnet[0].log_config[0].metadata == "INCLUDE_ALL_METADATA" &&
      google_compute_subnetwork.subnet[0].log_config[0].flow_sampling == 0.5
    )
    error_message = "The regional subnet must enable private Google access and explicit flow logs."
  }

  assert {
    condition = (
      google_compute_global_address.private_service_range[0].address_type == "INTERNAL" &&
      google_compute_global_address.private_service_range[0].purpose == "VPC_PEERING" &&
      google_compute_global_address.private_service_range[0].address == "10.40.16.0" &&
      google_compute_global_address.private_service_range[0].prefix_length == 20
    )
    error_message = "The private-service allocation must use the explicit global VPC_PEERING CIDR."
  }

  assert {
    condition = (
      google_service_networking_connection.private_service_connection[0].service == "servicenetworking.googleapis.com" &&
      google_service_networking_connection.private_service_connection[0].deletion_policy == "ABANDON" &&
      toset(google_service_networking_connection.private_service_connection[0].reserved_peering_ranges) == toset(["clearcut-production-private-services"])
    )
    error_message = "The service networking connection must use the explicit range and ABANDON deletion policy."
  }
}

run "network_foundation_rejects_incomplete_enabled_configuration" {
  command = plan

  module {
    source = "../../modules/network-foundation"
  }

  variables {
    enabled     = true
    project_id  = "clearcut-test"
    subnet_name = ""
  }

  expect_failures = [
    var.network_name,
    var.private_service_range_name,
    var.region,
    var.subnet_cidr,
  ]
}

run "network_foundation_rejects_missing_private_service_cidr" {
  command = plan

  module {
    source = "../../modules/network-foundation"
  }

  variables {
    enabled                    = true
    network_name               = "clearcut-production-network"
    private_service_range_name = "clearcut-production-private-services"
    project_id                 = "clearcut-test"
    region                     = "us-central1"
    subnet_cidr                = "10.40.0.0/20"
    subnet_name                = "clearcut-production-us-central1"
  }

  expect_failures = [var.private_service_cidr]
}

run "network_foundation_rejects_invalid_cidrs" {
  command = plan

  module {
    source = "../../modules/network-foundation"
  }

  variables {
    enabled                    = true
    network_name               = "clearcut-production-network"
    private_service_cidr       = "invalid"
    private_service_range_name = "clearcut-production-private-services"
    project_id                 = "clearcut-test"
    region                     = "us-central1"
    subnet_cidr                = "also-invalid"
    subnet_name                = "clearcut-production-us-central1"
  }

  expect_failures = [var.subnet_cidr]
}

run "network_foundation_rejects_invalid_private_service_cidr" {
  command = plan

  module {
    source = "../../modules/network-foundation"
  }

  variables {
    enabled                    = true
    network_name               = "clearcut-production-network"
    private_service_cidr       = "invalid"
    private_service_range_name = "clearcut-production-private-services"
    project_id                 = "clearcut-test"
    region                     = "us-central1"
    subnet_cidr                = "10.40.0.0/20"
    subnet_name                = "clearcut-production-us-central1"
  }

  expect_failures = [var.private_service_cidr]
}

run "network_foundation_rejects_overlapping_cidrs" {
  command = plan

  module {
    source = "../../modules/network-foundation"
  }

  variables {
    enabled                    = true
    network_name               = "clearcut-production-network"
    private_service_cidr       = "10.40.8.0/21"
    private_service_range_name = "clearcut-production-private-services"
    project_id                 = "clearcut-test"
    region                     = "us-central1"
    subnet_cidr                = "10.40.0.0/20"
    subnet_name                = "clearcut-production-us-central1"
  }

  expect_failures = [var.private_service_cidr]
}

run "network_api_routing_mode_defaults_to_deferred" {
  command = plan

  module {
    source = "../../modules/network-foundation"
  }

  variables {
    project_id = "clearcut-test"
  }

  assert {
    condition     = var.api_routing_mode == "deferred"
    error_message = "Future API routing must remain deferred by default."
  }
}

run "network_foundation_accepts_external_load_balancer_routing_mode" {
  command = plan

  module {
    source = "../../modules/network-foundation"
  }

  variables {
    api_routing_mode = "external-load-balancer"
    project_id       = "clearcut-test"
  }

  assert {
    condition     = var.api_routing_mode == "external-load-balancer"
    error_message = "External load balancer must remain an accepted documentary routing mode."
  }
}

run "network_foundation_accepts_authenticated_web_proxy_routing_mode" {
  command = plan

  module {
    source = "../../modules/network-foundation"
  }

  variables {
    api_routing_mode = "authenticated-web-proxy"
    project_id       = "clearcut-test"
  }

  assert {
    condition     = var.api_routing_mode == "authenticated-web-proxy"
    error_message = "Authenticated web proxy must remain an accepted documentary routing mode."
  }
}

run "network_foundation_rejects_private_api_routing_mode" {
  command = plan

  module {
    source = "../../modules/network-foundation"
  }

  variables {
    api_routing_mode = "private"
    project_id       = "clearcut-test"
  }

  expect_failures = [var.api_routing_mode]
}

run "network_foundation_rejects_public_api_routing_mode" {
  command = plan

  module {
    source = "../../modules/network-foundation"
  }

  variables {
    api_routing_mode = "public"
    project_id       = "clearcut-test"
  }

  expect_failures = [var.api_routing_mode]
}


run "artifact_registry_rejects_noncanonical_labels" {
  command = plan

  module {
    source = "../../modules/artifact-registry"
  }

  variables {
    enabled     = true
    environment = "production"
    location    = "us-central1"
    project_id  = "clearcut-test"
    repositories = {
      site = {
        description   = "ClearCut production site deployment images"
        keep_count    = 20
        labels        = { application = "other", environment = "production", managed_by = "terraform" }
        repository_id = "clearcut-production-site"
      }
      web = {
        description   = "ClearCut production web deployment images"
        keep_count    = 20
        labels        = { application = "clearcut", environment = "production", managed_by = "manual" }
        repository_id = "clearcut-production-web"
      }
      api = {
        description   = "ClearCut production api deployment images"
        keep_count    = 20
        labels        = { application = "clearcut", environment = "production", managed_by = "terraform" }
        repository_id = "clearcut-production-api"
      }
    }
  }

  expect_failures = [var.repositories]
}

run "production_rejects_nonproduction_repository_environment" {
  command = plan

  variables {
    artifact_registry_environment = "staging"
    project_id                    = "clearcut-test"
  }

  expect_failures = [var.artifact_registry_environment]
}

run "production_rejects_noncanonical_repository_labels" {
  command = plan

  variables {
    artifact_repositories = {
      site = {
        description   = "ClearCut production site deployment images"
        keep_count    = 20
        labels        = { application = "other", environment = "production", managed_by = "terraform" }
        repository_id = "clearcut-production-site"
      }
      web = {
        description   = "ClearCut production web deployment images"
        keep_count    = 20
        labels        = { application = "clearcut", environment = "production", managed_by = "terraform" }
        repository_id = "clearcut-production-web"
      }
      api = {
        description   = "ClearCut production api deployment images"
        keep_count    = 20
        labels        = { application = "clearcut", environment = "production", managed_by = "terraform" }
        repository_id = "clearcut-production-api"
      }
    }
    project_id = "clearcut-test"
  }

  expect_failures = [var.artifact_repositories]
}

run "network_foundation_rejects_syntactically_valid_noncanonical_names" {
  command = plan

  module {
    source = "../../modules/network-foundation"
  }

  variables {
    enabled                    = true
    network_name               = "valid-network"
    private_service_cidr       = "10.40.16.0/20"
    private_service_range_name = "valid-private-range"
    project_id                 = "clearcut-test"
    region                     = "us-central1"
    subnet_cidr                = "10.40.0.0/20"
    subnet_name                = "valid-subnet"
  }

  expect_failures = [var.network_name, var.private_service_range_name, var.subnet_name]
}

run "resource_dispositions_accept_exact_canonical_identities" {
  command = plan

  variables {
    project_id = "clearcut-test"
    resource_dispositions = {
      run = {
        disposition   = "import-and-retain"
        rationale     = "Retain the reviewed service."
        resource_id   = "projects/clearcut-test/locations/us-central1/services/api"
        resource_type = "cloud-run-service"
      }
      sql = {
        disposition   = "import-and-migrate"
        rationale     = "Migrate after adoption review."
        resource_id   = "projects/clearcut-test/instances/primary"
        resource_type = "cloud-sql-instance"
      }
      repository = {
        disposition   = "replace"
        rationale     = "Replacement is separately governed."
        resource_id   = "projects/clearcut-test/locations/us-central1/repositories/api"
        resource_type = "artifact-registry-repository"
      }
      secret = {
        disposition   = "leave-unmanaged-temporarily"
        rationale     = "Awaiting ownership review."
        resource_id   = "projects/clearcut-test/secrets/runtime"
        resource_type = "secret-manager-secret"
      }
      bucket = {
        disposition   = "retire"
        rationale     = "Retirement requires a governed action."
        resource_id   = "projects/_/buckets/clearcut-archive"
        resource_type = "storage-bucket"
      }
    }
  }

  assert {
    condition     = length(var.resource_dispositions) == 5
    error_message = "All five supported exact resource identities must be accepted."
  }
}

run "resource_dispositions_reject_malformed_identity" {
  command = plan

  variables {
    project_id = "clearcut-test"
    resource_dispositions = {
      malformed = {
        disposition   = "retire"
        rationale     = "Malformed identities must be rejected."
        resource_id   = "projects/clearcut-test/services/api"
        resource_type = "cloud-run-service"
      }
    }
  }

  expect_failures = [var.resource_dispositions]
}

run "resource_dispositions_reject_unsupported_type" {
  command = plan

  variables {
    project_id = "clearcut-test"
    resource_dispositions = {
      unsupported = {
        disposition   = "retire"
        rationale     = "Unknown types must be rejected."
        resource_id   = "projects/clearcut-test/global/networks/manual"
        resource_type = "compute-network"
      }
    }
  }

  expect_failures = [var.resource_dispositions]
}

run "resource_dispositions_reject_cross_project_identity" {
  command = plan

  variables {
    project_id = "clearcut-test"
    resource_dispositions = {
      foreign = {
        disposition   = "leave-unmanaged-temporarily"
        rationale     = "Cross-project identities must be rejected."
        resource_id   = "projects/other-project/secrets/runtime"
        resource_type = "secret-manager-secret"
      }
    }
  }

  expect_failures = [var.resource_dispositions]
}


run "valid_dispositions_are_documentary_and_do_not_change_resource_counts" {
  command = plan

  variables {
    project_id = "clearcut-test"
    resource_dispositions = {
      "legacy-api-repository" = {
        disposition   = "import-and-migrate"
        rationale     = "Preserve reviewed image history while migrating naming."
        resource_id   = "projects/clearcut-test/locations/us-central1/repositories/legacy-api"
        resource_type = "artifact-registry-repository"
      }
      "manual-network" = {
        disposition   = "leave-unmanaged-temporarily"
        rationale     = "Ownership review is incomplete."
        resource_id   = "projects/clearcut-test/locations/us-central1/services/manual-api"
        resource_type = "cloud-run-service"
      }
    }
  }

  assert {
    condition = (
      length(module.project_services.enabled_services) == 0 &&
      module.artifact_registry.repository_ids == {} &&
      module.artifact_registry.repository_names == {} &&
      module.network_foundation.network_id == null &&
      module.network_foundation.subnet_id == null &&
      module.network_foundation.private_service_range_id == null &&
      module.network_foundation.service_networking_connection_id == null
    )
    error_message = "Documentary dispositions must not change managed resource counts."
  }
}

run "resource_dispositions_accept_every_approved_value" {
  command = plan

  variables {
    project_id = "clearcut-test"
    resource_dispositions = {
      import-retain = {
        disposition   = "import-and-retain"
        rationale     = "Retain as reviewed."
        resource_id   = "projects/clearcut-test/locations/us-central1/repositories/site"
        resource_type = "artifact-registry-repository"
      }
      import-migrate = {
        disposition   = "import-and-migrate"
        rationale     = "Migrate after adoption review."
        resource_id   = "projects/clearcut-test/locations/us-central1/repositories/web"
        resource_type = "artifact-registry-repository"
      }
      replace = {
        disposition   = "replace"
        rationale     = "Replacement approved outside this documentary input."
        resource_id   = "projects/clearcut-test/locations/us-central1/repositories/api"
        resource_type = "artifact-registry-repository"
      }
      unmanaged = {
        disposition   = "leave-unmanaged-temporarily"
        rationale     = "Awaiting ownership review."
        resource_id   = "projects/clearcut-test/secrets/manual"
        resource_type = "secret-manager-secret"
      }
      retire = {
        disposition   = "retire"
        rationale     = "Retirement requires a separately governed action."
        resource_id   = "projects/_/buckets/clearcut-old-range"
        resource_type = "storage-bucket"
      }
    }
  }

  assert {
    condition     = length(var.resource_dispositions) == 5
    error_message = "All five approved documentary disposition values must be accepted."
  }
}

run "resource_dispositions_reject_unknown_value" {
  command = plan

  variables {
    project_id = "clearcut-test"
    resource_dispositions = {
      unsafe = {
        disposition   = "adopt-now"
        rationale     = "This must be rejected."
        resource_id   = "projects/clearcut-test/secrets/manual"
        resource_type = "secret-manager-secret"
      }
    }
  }

  expect_failures = [var.resource_dispositions]
}

run "resource_dispositions_reject_nonexact_or_empty_fields" {
  command = plan

  variables {
    project_id = "clearcut-test"
    resource_dispositions = {
      unsafe = {
        disposition   = "retire"
        rationale     = ""
        resource_id   = "projects/*/global/networks/*"
        resource_type = ""
      }
    }
  }

  expect_failures = [var.resource_dispositions]
}

run "resource_dispositions_reject_missing_required_field" {
  command = plan

  variables {
    project_id = "clearcut-test"
    resource_dispositions = {
      incomplete = {
        disposition   = "retire"
        resource_id   = "projects/clearcut-test/secrets/manual"
        resource_type = "secret-manager-secret"
      }
    }
  }

  expect_failures = [var.resource_dispositions]
}

mock_provider "google" {}

run "create_managed_network_foundation" {
  command   = apply
  state_key = "network-foundation-lifecycle"

  variables {
    manage_network_foundation  = true
    network_name               = "clearcut-production-network"
    region                     = "us-central1"
    private_service_cidr       = "10.40.16.0/20"
    private_service_range_name = "clearcut-production-private-services"
    project_id                 = "clearcut-test"
    subnet_cidr                = "10.40.0.0/20"
    subnet_name                = "clearcut-production-us-central1"
  }
}

run "disable_management" {
  command   = plan
  state_key = "network-foundation-lifecycle"

  variables {
    project_id = "clearcut-test"
  }
}

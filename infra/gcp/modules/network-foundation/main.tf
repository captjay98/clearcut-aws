resource "google_compute_network" "network" {
  count = var.enabled ? 1 : 0

  project                 = var.project_id
  name                    = var.network_name
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_compute_subnetwork" "subnet" {
  count = var.enabled ? 1 : 0

  project                  = var.project_id
  name                     = var.subnet_name
  region                   = var.region
  network                  = google_compute_network.network[0].id
  ip_cidr_range            = var.subnet_cidr
  private_ip_google_access = true

  log_config {
    aggregation_interval = "INTERVAL_10_MIN"
    flow_sampling        = 0.5
    metadata             = "INCLUDE_ALL_METADATA"
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_compute_global_address" "private_service_range" {
  count = var.enabled ? 1 : 0

  project       = var.project_id
  name          = var.private_service_range_name
  address_type  = "INTERNAL"
  purpose       = "VPC_PEERING"
  network       = google_compute_network.network[0].id
  address       = cidrhost(var.private_service_cidr, 0)
  prefix_length = tonumber(split("/", var.private_service_cidr)[1])

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_service_networking_connection" "private_service_connection" {
  count = var.enabled ? 1 : 0

  network                 = google_compute_network.network[0].id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_service_range[0].name]
  deletion_policy         = "ABANDON"

  lifecycle {
    prevent_destroy = true
  }
}

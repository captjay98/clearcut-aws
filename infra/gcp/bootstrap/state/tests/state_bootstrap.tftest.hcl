mock_provider "google" {}

run "disabled_by_default" {
  command = plan

  variables {
    project_id = "clearcut-test"
  }

  assert {
    condition     = module.state_bucket.bucket_name == null && module.state_bucket.bucket_self_link == null
    error_message = "Disabled state bootstrap child outputs must be null."
  }

  assert {
    condition     = output.bucket_name == null && output.bucket_self_link == null
    error_message = "Disabled state bootstrap outputs must be null."
  }
}

run "disabled_module_manages_no_bucket" {
  command = plan

  module {
    source = "../../modules/state-bootstrap"
  }

  variables {
    project_id = "clearcut-test"
  }

  assert {
    condition     = length(google_storage_bucket.state) == 0
    error_message = "A fresh disabled state bootstrap must manage zero buckets."
  }

  assert {
    condition     = output.bucket_name == null && output.bucket_self_link == null
    error_message = "Fresh disabled state bootstrap module outputs must be null."
  }
}

run "unsafe_force_destroy_is_rejected" {
  command = plan

  variables {
    project_id    = "clearcut-test"
    force_destroy = true
  }

  expect_failures = [var.force_destroy]
}

run "incomplete_enabled_configuration_is_rejected" {
  command = plan

  variables {
    project_id          = "clearcut-test"
    manage_state_bucket = true
  }

  expect_failures = [
    var.bucket_name,
    var.labels,
    var.retention_period_seconds,
    var.soft_delete_retention_seconds,
  ]
}

run "enabled_bucket_is_protected" {
  command = plan

  module {
    source = "../../modules/state-bootstrap"
  }

  variables {
    enabled                       = true
    project_id                    = "clearcut-test"
    bucket_name                   = "clearcut-test-terraform-state"
    location                      = "US"
    retention_period_seconds      = 2592000
    soft_delete_retention_seconds = 604800
    labels = {
      application = "clearcut"
      environment = "test"
      managed_by  = "terraform"
    }
  }

  assert {
    condition     = length(google_storage_bucket.state) == 1
    error_message = "Enabled state bootstrap must manage exactly one bucket."
  }

  assert {
    condition     = google_storage_bucket.state[0].storage_class == "STANDARD"
    error_message = "The state bucket must use STANDARD storage."
  }

  assert {
    condition     = google_storage_bucket.state[0].uniform_bucket_level_access
    error_message = "The state bucket must enforce uniform bucket-level access."
  }

  assert {
    condition     = google_storage_bucket.state[0].public_access_prevention == "enforced"
    error_message = "The state bucket must enforce public access prevention."
  }

  assert {
    condition     = google_storage_bucket.state[0].versioning[0].enabled
    error_message = "The state bucket must enable object versioning."
  }

  assert {
    condition     = google_storage_bucket.state[0].retention_policy[0].retention_period == 2592000 && !google_storage_bucket.state[0].retention_policy[0].is_locked
    error_message = "The state bucket must configure the explicit unlocked retention policy."
  }

  assert {
    condition     = google_storage_bucket.state[0].soft_delete_policy[0].retention_duration_seconds == 604800
    error_message = "The state bucket must configure the explicit soft-delete duration."
  }

  assert {
    condition = (
      google_storage_bucket.state[0].labels["application"] == "clearcut" &&
      google_storage_bucket.state[0].labels["environment"] == "test" &&
      google_storage_bucket.state[0].labels["managed_by"] == "terraform"
    )
    error_message = "The state bucket must retain all required labels."
  }

  assert {
    condition     = !google_storage_bucket.state[0].force_destroy
    error_message = "The state bucket must prohibit force destruction."
  }

  assert {
    condition     = strcontains(file("${path.module}/../../modules/state-bootstrap/main.tf"), "prevent_destroy = true")
    error_message = "The state bucket resource must set lifecycle prevent_destroy to true."
  }
}

mock_provider "google" {}

run "create_managed_bucket" {
  command   = apply
  state_key = "state-bucket-lifecycle"

  variables {
    project_id                    = "clearcut-test"
    manage_state_bucket           = true
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
}

run "disable_management" {
  command   = plan
  state_key = "state-bucket-lifecycle"

  variables {
    project_id = "clearcut-test"
  }
}

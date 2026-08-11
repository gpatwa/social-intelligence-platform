terraform {
  required_version = ">= 1.6.0"

  # CI configures this from an environment-specific backend.hcl file. Keeping
  # the backend values out of source lets dev and prod use distinct remote
  # state workspaces without leaking infrastructure metadata.
  backend "remote" {}

  required_providers {
    snowflake = {
      source  = "snowflakedb/snowflake"
      version = "2.18.0"
    }
  }
}

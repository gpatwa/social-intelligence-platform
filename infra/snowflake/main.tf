provider "snowflake" {
  organization_name = var.organization_name
  account_name      = var.account_name
  user              = var.deployer_user
  role              = var.deployer_role
  # Authentication is intentionally supplied by CI environment variables. The
  # development bridge uses JWT key-pair auth; production should use WIF/OIDC.
}

resource "snowflake_account_role" "publisher" {
  name    = "SOCIAL_INTELLIGENCE_PUBLISHER"
  comment = "Databricks Gold-mart publisher; no RAW analyst access"
}

resource "snowflake_account_role" "ba" {
  name    = "SOCIAL_INTELLIGENCE_BA"
  comment = "Read-only BA and BI role for curated social intelligence marts"
}

resource "snowflake_database" "social_intelligence" {
  name    = var.database_name
  comment = "Governed Snowflake serving database for Social Intelligence"
}

resource "snowflake_schema" "raw" {
  database = snowflake_database.social_intelligence.name
  name     = "RAW"
  comment  = "Transient publisher staging tables; no BA grants"
}

resource "snowflake_schema" "analytics" {
  database = snowflake_database.social_intelligence.name
  name     = "ANALYTICS"
  comment  = "Curated Gold marts and stable BA-facing views"
}

resource "snowflake_resource_monitor" "load" {
  name                      = "SOCIAL_INTELLIGENCE_LOAD_RM"
  credit_quota              = var.monthly_credit_quota
  frequency                 = "MONTHLY"
  start_timestamp           = "IMMEDIATELY"
  notify_triggers           = [75, 90]
  suspend_immediate_trigger = 100
}

resource "snowflake_resource_monitor" "ba" {
  name                      = "SOCIAL_INTELLIGENCE_BA_RM"
  credit_quota              = var.monthly_credit_quota
  frequency                 = "MONTHLY"
  start_timestamp           = "IMMEDIATELY"
  notify_triggers           = [75, 90]
  suspend_immediate_trigger = 100
}

resource "snowflake_warehouse" "load" {
  name                                = var.load_warehouse_name
  warehouse_size                      = "XSMALL"
  auto_suspend                        = 60
  auto_resume                         = "true"
  initially_suspended                 = true
  statement_timeout_in_seconds        = 1800
  statement_queued_timeout_in_seconds = 120
  resource_monitor                    = snowflake_resource_monitor.load.fully_qualified_name
  comment                             = "Dedicated Social Intelligence Databricks publishing warehouse"
}

resource "snowflake_warehouse" "ba" {
  name                                = var.ba_warehouse_name
  warehouse_size                      = "XSMALL"
  auto_suspend                        = 120
  auto_resume                         = "true"
  initially_suspended                 = true
  statement_timeout_in_seconds        = 900
  statement_queued_timeout_in_seconds = 120
  resource_monitor                    = snowflake_resource_monitor.ba.fully_qualified_name
  comment                             = "Dedicated Social Intelligence business analyst warehouse"
}

resource "snowflake_grant_account_role" "publisher_to_service_user" {
  role_name = snowflake_account_role.publisher.name
  user_name = var.publisher_user
}

resource "snowflake_grant_account_role" "ba_to_identity_group" {
  count            = var.ba_parent_role == "" ? 0 : 1
  role_name        = snowflake_account_role.ba.name
  parent_role_name = var.ba_parent_role
}

resource "snowflake_grant_privileges_to_account_role" "publisher_load_warehouse" {
  account_role_name = snowflake_account_role.publisher.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "WAREHOUSE"
    object_name = snowflake_warehouse.load.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ba_warehouse" {
  account_role_name = snowflake_account_role.ba.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "WAREHOUSE"
    object_name = snowflake_warehouse.ba.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "publisher_database" {
  account_role_name = snowflake_account_role.publisher.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.social_intelligence.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ba_database" {
  account_role_name = snowflake_account_role.ba.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.social_intelligence.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "publisher_raw_schema" {
  account_role_name = snowflake_account_role.publisher.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE STAGE", "CREATE FILE FORMAT"]
  on_schema {
    schema_name = snowflake_schema.raw.fully_qualified_name
  }
}

resource "snowflake_grant_privileges_to_account_role" "publisher_analytics_schema" {
  account_role_name = snowflake_account_role.publisher.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE VIEW"]
  on_schema {
    schema_name = snowflake_schema.analytics.fully_qualified_name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ba_analytics_schema" {
  account_role_name = snowflake_account_role.ba.name
  privileges        = ["USAGE"]
  on_schema {
    schema_name = snowflake_schema.analytics.fully_qualified_name
  }
}

resource "snowflake_grant_privileges_to_account_role" "ba_existing_tables" {
  account_role_name = snowflake_account_role.ba.name
  privileges        = ["SELECT"]
  on_schema_object {
    all {
      object_type_plural = "TABLES"
      in_schema          = snowflake_schema.analytics.fully_qualified_name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ba_future_tables" {
  account_role_name = snowflake_account_role.ba.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_schema          = snowflake_schema.analytics.fully_qualified_name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ba_existing_views" {
  account_role_name = snowflake_account_role.ba.name
  privileges        = ["SELECT"]
  on_schema_object {
    all {
      object_type_plural = "VIEWS"
      in_schema          = snowflake_schema.analytics.fully_qualified_name
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "ba_future_views" {
  account_role_name = snowflake_account_role.ba.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "VIEWS"
      in_schema          = snowflake_schema.analytics.fully_qualified_name
    }
  }
}

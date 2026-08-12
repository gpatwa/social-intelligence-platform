output "database_name" {
  value = snowflake_database.social_intelligence.name
}

output "load_warehouse_name" {
  value = snowflake_warehouse.load.name
}

output "ba_warehouse_name" {
  value = snowflake_warehouse.ba.name
}

output "publisher_role" {
  value = snowflake_account_role.publisher.name
}

output "ba_role" {
  value = snowflake_account_role.ba.name
}

variable "organization_name" {
  description = "Snowflake organization name, for example zcpwqmj."
  type        = string
}

variable "account_name" {
  description = "Snowflake account name, for example hd11049."
  type        = string
}

variable "deployer_user" {
  description = "Non-human Snowflake deploy identity supplied through CI configuration."
  type        = string
}

variable "deployer_role" {
  description = "Role used by Terraform. It requires object provisioning and grant-management privileges."
  type        = string
  default     = "ACCOUNTADMIN"
}

variable "publisher_user" {
  description = "Existing non-human identity used by Databricks to publish Gold marts."
  type        = string
  default     = "SVC_SOCIAL_INTELLIGENCE"
}

variable "ba_parent_role" {
  description = "Optional existing SSO/SCIM account role to receive BA access; leave blank until identity groups are available."
  type        = string
  default     = ""
}

variable "database_name" {
  description = "Governed Snowflake database for the social intelligence data product."
  type        = string
  default     = "SOCIAL_INTELLIGENCE"
}

variable "load_warehouse_name" {
  description = "Dedicated warehouse for Databricks publishing."
  type        = string
  default     = "SOCIAL_INTELLIGENCE_LOAD_WH"
}

variable "ba_warehouse_name" {
  description = "Dedicated read-only warehouse for analyst SQL."
  type        = string
  default     = "SOCIAL_INTELLIGENCE_BA_WH"
}

variable "monthly_credit_quota" {
  description = "Per-warehouse monthly credit quota used for resource-monitor guardrails."
  type        = number
  default     = 25
  validation {
    condition     = var.monthly_credit_quota > 0
    error_message = "monthly_credit_quota must be positive."
  }
}

# Snowflake control plane

This directory is the desired state for the Snowflake serving plane. It creates
separate publishing and BA warehouses, resource-monitor guardrails, the
`SOCIAL_INTELLIGENCE` database, `RAW` and `ANALYTICS` schemas, and role-based
access. It intentionally does not create people: human access remains owned by
the corporate IdP/SCIM system through `ba_parent_role`.

## Authentication model

The Terraform provider reads sensitive connection settings from its execution
environment. Never put private keys in `.tfvars` or commit them. The GitHub
deployment workflow uses an environment-scoped deploy identity for the current
Free Edition bridge. In production, configure Snowflake workload identity
federation for the CI runner and eliminate the static key.

Required CI environment values:

- `SNOWFLAKE_ORGANIZATION_NAME`
- `SNOWFLAKE_ACCOUNT_NAME`
- `SNOWFLAKE_USER`
- `SNOWFLAKE_PRIVATE_KEY` (temporary bridge only)
- `SNOWFLAKE_ROLE` (normally an infrastructure-admin role)
- `DATABRICKS_HOST`
- `TF_TOKEN_app_terraform_io`
- `TF_BACKEND_CONFIG`, containing the environment-specific Terraform Cloud
  backend configuration, for example:

  ```hcl
  organization = "your-terraform-cloud-organization"
  workspaces { name = "social-intelligence-snowflake-dev" }
  ```

## Adopt the existing dev bootstrap

The current Snowflake objects were created before this module existed. Import
them once rather than recreating or dropping live objects. Run these from this
directory after copying `dev.tfvars.example` to a local `.tfvars` file. Use a
separate local `backend.hcl` that points to a non-production remote workspace:

```bash
terraform init -backend-config=backend.hcl
terraform import -var-file=dev.tfvars \
  snowflake_account_role.publisher '"SOCIAL_INTELLIGENCE_PUBLISHER"'
terraform import -var-file=dev.tfvars \
  snowflake_account_role.ba '"SOCIAL_INTELLIGENCE_BA"'
terraform import -var-file=dev.tfvars \
  snowflake_database.social_intelligence '"SOCIAL_INTELLIGENCE"'
terraform import -var-file=dev.tfvars \
  snowflake_schema.raw '"SOCIAL_INTELLIGENCE"."RAW"'
terraform import -var-file=dev.tfvars \
  snowflake_schema.analytics '"SOCIAL_INTELLIGENCE"."ANALYTICS"'
```

The original shared `SOCIAL_INTELLIGENCE_WH` warehouse is not adopted. After
this module applies, use the newly created load and BA warehouses and retire
the shared warehouse only after the published marts reconcile.

The `Data platform deploy` workflow has an `adopt_existing_bootstrap` option
that performs the same idempotent imports directly into the selected remote
state workspace. Use it exactly once for the existing dev account.

## Delivery sequence

1. Pull request: `terraform fmt`, provider initialization, and static
   validation run without cloud credentials.
2. Approved workflow dispatch: environment-scoped credentials run `plan`.
3. The same approved workflow applies the Snowflake plan, deploys the
   Databricks bundle, and enables Snowflake publishing only when the
   `ENABLE_SNOWFLAKE_PUBLISH` variable is `true`.
4. The Databricks DAG publishes only after Gold validation succeeds.

`RAW` is publisher-only staging. Business analysts receive `SELECT` only on
`ANALYTICS`, including future tables and views.

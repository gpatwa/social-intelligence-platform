# Snowflake serving for BA and SQL users

Databricks remains the governed system of record. Snowflake is the curated
serving surface for business analysts and BI tools that need familiar SQL.

```text
Approved social APIs -> Databricks signals + decisions -> Snowflake ANALYTICS -> BA / BI
```

The publisher copies Gold marts only. It never copies raw API payloads,
provider credentials, or the Bronze event envelope into Snowflake.

## Automated developer bootstrap

The Free Edition developer path is automated. The bootstrap creates the
dedicated Snowflake roles, warehouses, database, schemas, service user,
least-privilege grants, and Databricks secret; it can also perform one guarded
publish. The private key never enters the repository or GitHub.

```bash
python3 scripts/bootstrap_snowflake_dev.py --run-initial-publish
```

Snowflake authentication remains an identity boundary: the administrator must
complete its provider-owned SSO/MFA flow. For accounts without ExternalBrowser
SSO, run the same idempotent statements from an authenticated Snowsight
administrator session rather than copying credentials into the application.

This is the temporary Free Edition path. The staff-level deployment model is
defined in [`infra/snowflake`](../../infra/snowflake): Terraform owns objects,
roles, grants, dedicated warehouses, and resource monitors; CI performs a
reviewed plan/apply; and production moves the deployment identity to workload
identity federation instead of a static key.

## BA access and continuous serving

The development target enables the publisher only after the successful guarded
validation. Each hourly run validates Gold before it writes Snowflake. Business
analysts use the `SOCIAL_INTELLIGENCE_BA` role with the dedicated
`SOCIAL_INTELLIGENCE_BA_WH` warehouse and read-only access to `ANALYTICS`.

Start with [`snowflake_ba_starter_queries.sql`](../sql/snowflake_ba_starter_queries.sql).
It includes executive pulse, emerging trends, challenge intelligence, brand
health, topic performance, connector operations, opportunity prioritization,
recommendation review, experiment performance, and pilot scorecard queries
against 13 curated marts.

## Publish behavior

`GOLD_TOPIC_HOURLY`, `GOLD_BRAND_DAILY`, and the durable recommendation,
experiment, and learning records use key-based `MERGE` writes.
Current-state marts (trends, challenges, KPIs, connector operations, and
trending topics, opportunities, experiment performance, and the pilot
scorecard) are built in a temporary staging table and atomically replaced in
Snowflake. That prevents removed or expired state from appearing as active to
analysts.

This Free Edition-compatible implementation collects curated Gold marts to the
driver before writing them. Move to the Spark Snowflake connector plus a staged
bulk load before Gold outputs outgrow a controlled serving-mart size.

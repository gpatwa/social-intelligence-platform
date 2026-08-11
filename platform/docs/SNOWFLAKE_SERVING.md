# Snowflake serving for BA and SQL users

Databricks remains the governed system of record. Snowflake is the curated
serving surface for business analysts and BI tools that need familiar SQL.

```text
Approved social APIs -> Databricks Bronze/Silver/Gold -> Snowflake ANALYTICS -> BA / BI
```

The publisher copies Gold marts only. It never copies raw API payloads,
provider credentials, or the Bronze event envelope into Snowflake.

## Development key-pair bridge

Run the following on a trusted workstation. Do not commit either key or paste
the private key into chat.

```bash
openssl genrsa -out social_intelligence_snowflake_key.pem 2048
openssl rsa -in social_intelligence_snowflake_key.pem -pubout \
  -out social_intelligence_snowflake_key.pub
grep -v -- '-----' social_intelligence_snowflake_key.pub | tr -d '\n' \
  > social_intelligence_snowflake_key.public-base64
base64 < social_intelligence_snowflake_key.pem | tr -d '\n' \
  > social_intelligence_snowflake_key.base64
```

In Snowflake, use `ACCOUNTADMIN` to attach the public key:

```sql
ALTER USER SVC_SOCIAL_INTELLIGENCE SET RSA_PUBLIC_KEY =
  '<contents of social_intelligence_snowflake_key.public-base64>';

DESC USER SVC_SOCIAL_INTELLIGENCE;
```

Store the one-line contents of `social_intelligence_snowflake_key.base64` as
the Databricks secret `social-intelligence/snowflake-private-key-base64`.
The secret must be a base64-encoded PEM; it is decoded only in the publishing
job. Do not store it as a GitHub secret because the publisher runs in
Databricks.

This is the temporary Free Edition path. The staff-level deployment model is
defined in [`infra/snowflake`](../../infra/snowflake): Terraform owns objects,
roles, grants, dedicated warehouses, and resource monitors; CI performs a
reviewed plan/apply; and production moves the deployment identity to workload
identity federation instead of a static key.

## Deploy and manually validate

Set the account identifier (normally `org-account`, not the Snowsight URL) in
the deployment target, then deploy:

```bash
databricks bundle deploy -t dev \
  --var snowflake_account='<org-account>'

databricks bundle run social_intelligence_external_ingestion -t dev \
  --var snowflake_account='<org-account>' \
  --var snowflake_publish_enabled=true
```

The publish task is skipped by default and only runs after the validated Gold
tasks when `snowflake_publish_enabled=true`. Complete one manual run and
validate these queries before enabling it in the deployment environment:

```sql
USE ROLE SOCIAL_INTELLIGENCE_BA;
USE WAREHOUSE SOCIAL_INTELLIGENCE_WH;

SELECT * FROM SOCIAL_INTELLIGENCE.ANALYTICS.GOLD_EXECUTIVE_KPIS;
SELECT * FROM SOCIAL_INTELLIGENCE.ANALYTICS.GOLD_TREND_SNAPSHOT
ORDER BY TREND_SCORE DESC NULLS LAST;
SELECT * FROM SOCIAL_INTELLIGENCE.ANALYTICS.GOLD_CONNECTOR_OPERATIONS;
```

## Publish behavior

`GOLD_TOPIC_HOURLY` and `GOLD_BRAND_DAILY` use key-based `MERGE` writes.
Current-state marts (trends, challenges, KPIs, connector operations, and
trending topics) are built in a temporary staging table and atomically replaced
in Snowflake. That prevents removed or expired trends from appearing as active
to analysts.

This Free Edition-compatible implementation collects curated Gold marts to the
driver before writing them. Move to the Spark Snowflake connector plus a staged
bulk load before Gold outputs outgrow a controlled serving-mart size.

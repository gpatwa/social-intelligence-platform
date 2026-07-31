# Databricks notebook source
"""Initialize logical control-plane metadata and shared data-plane storage."""

import re


dbutils.widgets.text("catalog", "dev")
dbutils.widgets.text("schema", "social_intelligence_dev")
dbutils.widgets.text("tenant_id", "demo")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
tenant_id = dbutils.widgets.get("tenant_id")

for identifier in (catalog, schema):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", identifier):
        raise ValueError(f"Unsafe Unity Catalog identifier: {identifier!r}")
if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,62}", tenant_id):
    raise ValueError(f"Unsafe tenant identifier: {tenant_id!r}")

ns = f"`{catalog}`.`{schema}`"
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {ns}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {ns}.`raw_social`")

# These tables are the logical control plane. They describe desired collection
# behavior; connector workers consume them but social payloads never flow here.
spark.sql(
    f"""
    CREATE TABLE IF NOT EXISTS {ns}.`control_source_registry` (
      tenant_id STRING NOT NULL,
      source_id STRING NOT NULL,
      platform STRING NOT NULL,
      connector_type STRING NOT NULL,
      collection_mode STRING NOT NULL,
      enabled BOOLEAN NOT NULL,
      event_schema_version STRING NOT NULL,
      poll_interval_seconds INT,
      secret_scope STRING,
      secret_key STRING,
      owner STRING NOT NULL,
      updated_at TIMESTAMP NOT NULL
    )
    USING DELTA
    COMMENT 'Desired-state registry for social connectors; contains secret references, never credentials'
    """
)

spark.sql(
    f"""
    MERGE INTO {ns}.`control_source_registry` AS target
    USING (
      SELECT * FROM VALUES
        ('{tenant_id}', 'demo-youtube', 'youtube', 'demo_generator', 'batch', true, '1.0', 300, NULL, NULL, 'data-platform', CURRENT_TIMESTAMP()),
        ('{tenant_id}', 'demo-reddit', 'reddit', 'demo_generator', 'batch', true, '1.0', 300, NULL, NULL, 'data-platform', CURRENT_TIMESTAMP()),
        ('{tenant_id}', 'demo-tiktok', 'tiktok', 'demo_generator', 'batch', true, '1.0', 300, NULL, NULL, 'data-platform', CURRENT_TIMESTAMP())
      AS source(tenant_id, source_id, platform, connector_type, collection_mode, enabled,
                event_schema_version, poll_interval_seconds, secret_scope, secret_key, owner, updated_at)
    ) AS incoming
    ON target.tenant_id = incoming.tenant_id AND target.source_id = incoming.source_id
    WHEN MATCHED THEN UPDATE SET
      platform = incoming.platform,
      connector_type = incoming.connector_type,
      collection_mode = incoming.collection_mode,
      enabled = incoming.enabled,
      event_schema_version = incoming.event_schema_version,
      poll_interval_seconds = incoming.poll_interval_seconds,
      owner = incoming.owner,
      updated_at = incoming.updated_at
    WHEN NOT MATCHED THEN INSERT *
    """
)

spark.sql(
    f"""
    CREATE TABLE IF NOT EXISTS {ns}.`control_collection_rules` (
      tenant_id STRING NOT NULL,
      rule_id STRING NOT NULL,
      source_id STRING NOT NULL,
      rule_type STRING NOT NULL,
      expression STRING NOT NULL,
      enabled BOOLEAN NOT NULL,
      updated_at TIMESTAMP NOT NULL
    )
    USING DELTA
    COMMENT 'Versionable collection intent consumed by streaming and polling connectors'
    """
)

spark.sql(
    f"""
    MERGE INTO {ns}.`control_collection_rules` AS target
    USING (
      SELECT * FROM VALUES
        ('{tenant_id}', 'track-product', 'demo-youtube', 'keyword', 'Acme', true, CURRENT_TIMESTAMP()),
        ('{tenant_id}', 'track-challenges', 'demo-tiktok', 'hashtag', '*Challenge', true, CURRENT_TIMESTAMP())
      AS rule(tenant_id, rule_id, source_id, rule_type, expression, enabled, updated_at)
    ) AS incoming
    ON target.tenant_id = incoming.tenant_id AND target.rule_id = incoming.rule_id
    WHEN MATCHED THEN UPDATE SET
      source_id = incoming.source_id,
      rule_type = incoming.rule_type,
      expression = incoming.expression,
      enabled = incoming.enabled,
      updated_at = incoming.updated_at
    WHEN NOT MATCHED THEN INSERT *
    """
)

spark.sql(
    f"""
    CREATE TABLE IF NOT EXISTS {ns}.`control_event_contracts` (
      schema_version STRING NOT NULL,
      event_type STRING NOT NULL,
      compatibility_mode STRING NOT NULL,
      payload_policy STRING NOT NULL,
      active BOOLEAN NOT NULL,
      registered_at TIMESTAMP NOT NULL
    )
    USING DELTA
    COMMENT 'Accepted event-envelope contracts and compatibility policy'
    """
)

spark.sql(
    f"""
    MERGE INTO {ns}.`control_event_contracts` AS target
    USING (
      SELECT * FROM VALUES
        ('1.0', 'social.post.observed', 'BACKWARD', 'SOURCE_SHAPED_JSON', true, CURRENT_TIMESTAMP()),
        ('1.0', 'social.post.updated', 'BACKWARD', 'SOURCE_SHAPED_JSON', true, CURRENT_TIMESTAMP()),
        ('1.0', 'social.post.deleted', 'BACKWARD', 'SOURCE_SHAPED_JSON', true, CURRENT_TIMESTAMP()),
        ('1.0', 'social.engagement.observed', 'BACKWARD', 'SOURCE_SHAPED_JSON', true, CURRENT_TIMESTAMP())
      AS contract(schema_version, event_type, compatibility_mode, payload_policy, active, registered_at)
    ) AS incoming
    ON target.schema_version = incoming.schema_version AND target.event_type = incoming.event_type
    WHEN MATCHED THEN UPDATE SET
      compatibility_mode = incoming.compatibility_mode,
      payload_policy = incoming.payload_policy,
      active = incoming.active
    WHEN NOT MATCHED THEN INSERT *
    """
)

print(f"Initialized control plane in {catalog}.{schema} for tenant {tenant_id}")
print(f"Raw event landing root: /Volumes/{catalog}/{schema}/raw_social/events")

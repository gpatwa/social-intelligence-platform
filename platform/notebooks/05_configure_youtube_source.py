# Databricks notebook source
"""Register the desired state for a public YouTube Data API v3 source."""

from datetime import datetime, timezone
from hashlib import sha256
import re

from pyspark.sql import Row


dbutils.widgets.text("catalog", "dev")
dbutils.widgets.text("schema", "social_intelligence_dev")
dbutils.widgets.text("tenant_id", "demo")
dbutils.widgets.text("source_id", "youtube-api-v3")
dbutils.widgets.text("secret_scope", "social-intelligence")
dbutils.widgets.text("secret_key", "youtube-api-key")
dbutils.widgets.text("search_expression", "Acme|GlowUpChallenge")
dbutils.widgets.text("channel_ids", "")
dbutils.widgets.text("poll_interval_seconds", "3600")
dbutils.widgets.text("owner", "data-platform")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
tenant_id = dbutils.widgets.get("tenant_id")
source_id = dbutils.widgets.get("source_id")
secret_scope = dbutils.widgets.get("secret_scope")
secret_key = dbutils.widgets.get("secret_key")
search_expression = dbutils.widgets.get("search_expression").strip()
channel_ids = [
    value.strip()
    for value in dbutils.widgets.get("channel_ids").split(",")
    if value.strip()
]
poll_interval_seconds = int(dbutils.widgets.get("poll_interval_seconds"))
owner = dbutils.widgets.get("owner").strip()

for identifier in (catalog, schema):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", identifier):
        raise ValueError(f"Unsafe Unity Catalog identifier: {identifier!r}")
for name, value in (
    ("tenant_id", tenant_id),
    ("source_id", source_id),
    ("secret_scope", secret_scope),
    ("secret_key", secret_key),
):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value):
        raise ValueError(f"Unsafe {name}: {value!r}")
if not owner or len(owner) > 255 or any(ord(character) < 32 for character in owner):
    raise ValueError("owner must be a printable value no longer than 255 characters")
if not 900 <= poll_interval_seconds <= 86_400:
    raise ValueError("poll_interval_seconds must be between 900 and 86400")
if not search_expression and not channel_ids:
    raise ValueError("At least one search expression or channel ID is required")
for channel_id in channel_ids:
    if not re.fullmatch(r"[A-Za-z0-9_-]{3,64}", channel_id):
        raise ValueError(f"Unsafe YouTube channel ID: {channel_id!r}")

namespace = f"`{catalog}`.`{schema}`"
# Spark expects a naive UTC datetime when constructing a TIMESTAMP field.
now = datetime.now(timezone.utc).replace(tzinfo=None)
source_view = "incoming_youtube_source"
rules_view = "incoming_youtube_rules"

spark.createDataFrame(
    [
        Row(
            tenant_id=tenant_id,
            source_id=source_id,
            platform="youtube",
            connector_type="youtube_data_api_v3",
            collection_mode="polling",
            enabled=True,
            event_schema_version="1.0",
            poll_interval_seconds=poll_interval_seconds,
            secret_scope=secret_scope,
            secret_key=secret_key,
            owner=owner,
            updated_at=now,
        )
    ]
).createOrReplaceTempView(source_view)

spark.sql(
    f"""
    MERGE INTO {namespace}.`control_source_registry` AS target
    USING {source_view} AS incoming
      ON target.tenant_id = incoming.tenant_id
     AND target.source_id = incoming.source_id
    WHEN MATCHED THEN UPDATE SET
      platform = incoming.platform,
      connector_type = incoming.connector_type,
      collection_mode = incoming.collection_mode,
      enabled = incoming.enabled,
      event_schema_version = incoming.event_schema_version,
      poll_interval_seconds = incoming.poll_interval_seconds,
      secret_scope = incoming.secret_scope,
      secret_key = incoming.secret_key,
      owner = incoming.owner,
      updated_at = incoming.updated_at
    WHEN NOT MATCHED THEN INSERT *
    """
)

rules = []
if search_expression:
    rules.append(("keyword", search_expression))
rules.extend(("channel", channel_id) for channel_id in channel_ids)
rule_rows = [
    Row(
        tenant_id=tenant_id,
        rule_id=f"youtube-{rule_type}-{sha256(expression.encode()).hexdigest()[:12]}",
        source_id=source_id,
        rule_type=rule_type,
        expression=expression,
        enabled=True,
        updated_at=now,
    )
    for rule_type, expression in rules
]
spark.createDataFrame(rule_rows).createOrReplaceTempView(rules_view)

spark.sql(
    f"""
    MERGE INTO {namespace}.`control_collection_rules` AS target
    USING {rules_view} AS incoming
      ON target.tenant_id = incoming.tenant_id
     AND target.rule_id = incoming.rule_id
    WHEN MATCHED THEN UPDATE SET
      source_id = incoming.source_id,
      rule_type = incoming.rule_type,
      expression = incoming.expression,
      enabled = incoming.enabled,
      updated_at = incoming.updated_at
    WHEN NOT MATCHED THEN INSERT *
    WHEN NOT MATCHED BY SOURCE
      AND target.tenant_id = '{tenant_id}'
      AND target.source_id = '{source_id}'
    THEN UPDATE SET enabled = false, updated_at = CURRENT_TIMESTAMP()
    """
)

print(
    f"Registered YouTube source {tenant_id}/{source_id} with {len(rule_rows)} "
    "active collection rule(s)"
)
print(f"Credential reference: {secret_scope}/{secret_key}")

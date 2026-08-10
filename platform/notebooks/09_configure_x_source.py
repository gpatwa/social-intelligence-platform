# Databricks notebook source
"""Register the desired state for an X API v2 recent-search source."""

from datetime import datetime, timezone
from hashlib import sha256
import re

from pyspark.sql import Row


dbutils.widgets.text("catalog", "dev")
dbutils.widgets.text("schema", "social_intelligence_dev")
dbutils.widgets.text("tenant_id", "demo")
dbutils.widgets.text("source_id", "x-api-v2")
dbutils.widgets.text("secret_scope", "external-github-actions")
dbutils.widgets.text("secret_key", "x-bearer-token")
dbutils.widgets.text("search_expression", "")
dbutils.widgets.text("hashtags", "")
dbutils.widgets.text("account_handles", "")
dbutils.widgets.text("trends_woeid", "2487956")
dbutils.widgets.text("trends_location", "San Francisco")
dbutils.widgets.text("max_trends_per_run", "20")
dbutils.widgets.text("poll_interval_seconds", "3600")
dbutils.widgets.text("owner", "data-platform")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
tenant_id = dbutils.widgets.get("tenant_id")
source_id = dbutils.widgets.get("source_id")
secret_scope = dbutils.widgets.get("secret_scope")
secret_key = dbutils.widgets.get("secret_key")
search_expression = dbutils.widgets.get("search_expression").strip()
hashtags = [value.strip() for value in dbutils.widgets.get("hashtags").split(",") if value.strip()]
account_handles = [value.strip() for value in dbutils.widgets.get("account_handles").split(",") if value.strip()]
trends_woeid = dbutils.widgets.get("trends_woeid").strip()
trends_location = dbutils.widgets.get("trends_location").strip()
max_trends_per_run = int(dbutils.widgets.get("max_trends_per_run"))
poll_interval_seconds = int(dbutils.widgets.get("poll_interval_seconds"))
owner = dbutils.widgets.get("owner").strip()

for identifier in (catalog, schema):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", identifier):
        raise ValueError(f"Unsafe Unity Catalog identifier: {identifier!r}")
for name, value in (("tenant_id", tenant_id), ("source_id", source_id), ("secret_scope", secret_scope), ("secret_key", secret_key)):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value):
        raise ValueError(f"Unsafe {name}: {value!r}")
if trends_woeid:
    if not trends_woeid.isdigit() or int(trends_woeid) <= 0:
        raise ValueError("trends_woeid must be a positive integer")
    if not trends_location or len(trends_location) > 100 or any(ord(character) < 32 for character in trends_location):
        raise ValueError("trends_location must be printable and at most 100 characters")
elif trends_location:
    raise ValueError("trends_location requires trends_woeid")
if not 1 <= max_trends_per_run <= 20:
    raise ValueError("max_trends_per_run must be between 1 and 20")
if not search_expression and not hashtags and not account_handles and not trends_woeid:
    raise ValueError("At least one X search rule or trends_woeid is required")
if not 900 <= poll_interval_seconds <= 86_400:
    raise ValueError("poll_interval_seconds must be between 900 and 86400")
if not owner or len(owner) > 255 or any(ord(character) < 32 for character in owner):
    raise ValueError("owner must be a printable value no longer than 255 characters")
for hashtag in hashtags:
    if not re.fullmatch(r"#?[\w-]{1,100}", hashtag, re.UNICODE):
        raise ValueError(f"Unsafe X hashtag: {hashtag!r}")
for handle in account_handles:
    if not re.fullmatch(r"@?[A-Za-z0-9_]{1,15}", handle):
        raise ValueError(f"Unsafe X account handle: {handle!r}")

namespace = f"`{catalog}`.`{schema}`"
now = datetime.now(timezone.utc).replace(tzinfo=None)
spark.createDataFrame([Row(
    tenant_id=tenant_id, source_id=source_id, platform="x",
    connector_type="x_api_v2_recent_search", collection_mode="polling", enabled=True,
    event_schema_version="1.0", poll_interval_seconds=poll_interval_seconds,
    secret_scope=secret_scope, secret_key=secret_key, owner=owner, updated_at=now,
)]).createOrReplaceTempView("incoming_x_source")
spark.sql(f"""
    MERGE INTO {namespace}.`control_source_registry` AS target
    USING incoming_x_source AS incoming
      ON target.tenant_id = incoming.tenant_id AND target.source_id = incoming.source_id
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
""")

rules = []
if search_expression:
    rules.append(("keyword", search_expression))
rules.extend(("hashtag", hashtag) for hashtag in hashtags)
rules.extend(("account", handle) for handle in account_handles)
if trends_woeid:
    rules.append(("trend", f"woeid:{trends_woeid}"))
spark.createDataFrame([Row(
    tenant_id=tenant_id,
    rule_id=f"x-{rule_type}-{sha256(expression.encode()).hexdigest()[:12]}",
    source_id=source_id, rule_type=rule_type, expression=expression,
    enabled=True, updated_at=now,
) for rule_type, expression in rules]).createOrReplaceTempView("incoming_x_rules")
spark.sql(f"""
    MERGE INTO {namespace}.`control_collection_rules` AS target
    USING incoming_x_rules AS incoming
      ON target.tenant_id = incoming.tenant_id AND target.rule_id = incoming.rule_id
    WHEN MATCHED THEN UPDATE SET
      source_id = incoming.source_id,
      rule_type = incoming.rule_type,
      expression = incoming.expression,
      enabled = incoming.enabled,
      updated_at = incoming.updated_at
    WHEN NOT MATCHED THEN INSERT *
    WHEN NOT MATCHED BY SOURCE
      AND target.tenant_id = '{tenant_id}' AND target.source_id = '{source_id}'
    THEN UPDATE SET enabled = false, updated_at = CURRENT_TIMESTAMP()
""")
print(f"Registered X source {tenant_id}/{source_id} with {len(rules)} active collection rule(s)")
print(f"Credential reference: {secret_scope}/{secret_key}")

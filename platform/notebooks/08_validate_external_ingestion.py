# Databricks notebook source
"""Validate source-specific acceptance gates for external ingestion."""

import re


dbutils.widgets.text("catalog", "dev")
dbutils.widgets.text("schema", "social_intelligence_dev")
dbutils.widgets.text("tenant_id", "demo")
dbutils.widgets.text("source_id", "youtube-api-v3")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
tenant_id = dbutils.widgets.get("tenant_id")
source_id = dbutils.widgets.get("source_id")

for identifier in (catalog, schema):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", identifier):
        raise ValueError(f"Unsafe Unity Catalog identifier: {identifier!r}")
for name, value in (("tenant_id", tenant_id), ("source_id", source_id)):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value):
        raise ValueError(f"Unsafe {name}: {value!r}")

namespace = f"`{catalog}`.`{schema}`"
checks = spark.sql(
    f"""
    WITH checks AS (
      SELECT
        'source_is_registered' AS check_name,
        COUNT_IF(enabled) = 1 AS passed,
        CONCAT(COUNT_IF(enabled), ' enabled source registrations') AS detail
      FROM {namespace}.`control_source_registry`
      WHERE tenant_id = '{tenant_id}' AND source_id = '{source_id}'

      UNION ALL
      SELECT
        'latest_collection_succeeded',
        COUNT_IF(status = 'SUCCESS' AND run_age_minutes <= 180) = 1,
        CONCAT_WS(', ',
          CONCAT('status=', COALESCE(MAX(status), 'missing')),
          CONCAT('age_minutes=', COALESCE(MAX(run_age_minutes), -1))
        )
      FROM {namespace}.`gold_connector_operations`
      WHERE tenant_id = '{tenant_id}' AND source_id = '{source_id}'

      UNION ALL
      SELECT
        'quota_headroom_is_positive',
        COUNT_IF(search_calls_remaining > 0 AND core_units_remaining > 0) = 1,
        CONCAT_WS(', ',
          CONCAT('search_remaining=', COALESCE(MAX(search_calls_remaining), -1)),
          CONCAT('core_remaining=', COALESCE(MAX(core_units_remaining), -1))
        )
      FROM {namespace}.`gold_connector_operations`
      WHERE tenant_id = '{tenant_id}' AND source_id = '{source_id}'

      UNION ALL
      SELECT
        'source_has_delivered_events',
        COUNT(*) > 0,
        CONCAT(COUNT(*), ' delivered events')
      FROM {namespace}.`bronze_social_events`
      WHERE tenant_id = '{tenant_id}' AND source_id = '{source_id}'

      UNION ALL
      SELECT
        'source_dead_letter_is_empty',
        COUNT(*) = 0,
        CONCAT(COUNT(*), ' rejected events')
      FROM {namespace}.`bronze_dead_letter_events`
      WHERE tenant_id = '{tenant_id}' AND source_id = '{source_id}'
    )
    SELECT * FROM checks ORDER BY check_name
    """
)

display(checks)
failed = checks.filter("NOT passed").collect()
if failed:
    summary = "; ".join(f"{row.check_name}: {row.detail}" for row in failed)
    raise RuntimeError(f"External ingestion validation failed: {summary}")

print(f"External ingestion acceptance gates passed for {tenant_id}/{source_id}")

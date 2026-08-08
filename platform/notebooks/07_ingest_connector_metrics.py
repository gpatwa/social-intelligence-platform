# Databricks notebook source
"""Ingest external collector run records into operational data products."""

import re

from pyspark.sql import functions as F
from pyspark.sql import types as T


dbutils.widgets.text("catalog", "dev")
dbutils.widgets.text("schema", "social_intelligence_dev")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

for identifier in (catalog, schema):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", identifier):
        raise ValueError(f"Unsafe Unity Catalog identifier: {identifier!r}")

namespace = f"`{catalog}`.`{schema}`"
operations_path = f"/Volumes/{catalog}/{schema}/raw_social/operations"
checkpoint_path = (
    f"/Volumes/{catalog}/{schema}/raw_social/checkpoints/connector_operations"
)

metric_schema = T.StructType(
    [
        T.StructField("run_id", T.StringType()),
        T.StructField("tenant_id", T.StringType()),
        T.StructField("source_id", T.StringType()),
        T.StructField("platform", T.StringType()),
        T.StructField("runtime", T.StringType()),
        T.StructField("started_at", T.TimestampType()),
        T.StructField("completed_at", T.TimestampType()),
        T.StructField("status", T.StringType()),
        T.StructField("active_rules", T.LongType()),
        T.StructField("videos_discovered", T.LongType()),
        T.StructField("posts_discovered", T.LongType()),
        T.StructField("events_emitted", T.LongType()),
        T.StructField("search_calls_used", T.LongType()),
        T.StructField("search_calls_remaining", T.LongType()),
        T.StructField("core_units_used", T.LongType()),
        T.StructField("core_units_remaining", T.LongType()),
        T.StructField("requests_used", T.LongType()),
        T.StructField("requests_remaining", T.LongType()),
        T.StructField("event_path", T.StringType()),
        T.StructField("error_type", T.StringType()),
    ]
)

# Existing Free Edition workspaces may already have the YouTube-only shape.
# Evolve the governed operational table before Auto Loader writes X metrics so a
# connector rollout does not depend on destructive table recreation.
metrics_table = f"{catalog}.{schema}.bronze_connector_runs"
if not spark.catalog.tableExists(metrics_table):
    spark.createDataFrame([], metric_schema).write.format("delta").saveAsTable(metrics_table)
else:
    existing_columns = {
        field.name.lower() for field in spark.table(metrics_table).schema.fields
    }
    for column_name in ("posts_discovered", "requests_used", "requests_remaining"):
        if column_name not in existing_columns:
            spark.sql(
                f"ALTER TABLE {namespace}.`bronze_connector_runs` "
                f"ADD COLUMNS (`{column_name}` BIGINT)"
            )

metric_stream = (
    spark.readStream.format("cloudFiles")
    .option("cloudFiles.format", "json")
    .schema(metric_schema)
    .load(operations_path)
)
query = (
    metric_stream.withColumn("ingested_at", F.current_timestamp())
    .writeStream.option("checkpointLocation", checkpoint_path)
    .option("mergeSchema", "false")
    .trigger(availableNow=True)
    .toTable(metrics_table)
)
query.awaitTermination()

spark.sql(
    f"""
    CREATE OR REPLACE TABLE {namespace}.`gold_connector_operations`
    COMMENT 'Latest external collection status, quota headroom, and delivery counts'
    AS
    WITH ranked AS (
      SELECT
        *,
        ROW_NUMBER() OVER (
          PARTITION BY tenant_id, source_id
          ORDER BY completed_at DESC, run_id DESC
        ) AS run_rank,
        COUNT_IF(status = 'FAILED') OVER (
          PARTITION BY tenant_id, source_id
          ORDER BY completed_at
          ROWS BETWEEN 23 PRECEDING AND CURRENT ROW
        ) AS failed_runs_last_24
      FROM {namespace}.`bronze_connector_runs`
    )
    SELECT
      run_id,
      tenant_id,
      source_id,
      platform,
      runtime,
      started_at,
      completed_at,
      status,
      active_rules,
      videos_discovered,
      posts_discovered,
      COALESCE(posts_discovered, videos_discovered, 0) AS source_objects_discovered,
      events_emitted,
      search_calls_used,
      search_calls_remaining,
      core_units_used,
      core_units_remaining,
      requests_used,
      requests_remaining,
      event_path,
      error_type,
      failed_runs_last_24,
      TIMESTAMPDIFF(MINUTE, completed_at, CURRENT_TIMESTAMP()) AS run_age_minutes,
      CASE
        WHEN status = 'FAILED' THEN 'DEGRADED'
        WHEN TIMESTAMPDIFF(MINUTE, completed_at, CURRENT_TIMESTAMP()) > 180
          THEN 'STALE'
        WHEN search_calls_remaining <= 5 OR core_units_remaining <= 500
          OR requests_remaining <= 5
          THEN 'QUOTA_GUARD'
        ELSE 'HEALTHY'
      END AS operational_status,
      CURRENT_TIMESTAMP() AS evaluated_at
    FROM ranked
    WHERE run_rank = 1
    """
)

print(f"Refreshed connector operations in {catalog}.{schema}")

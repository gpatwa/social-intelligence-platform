# Databricks notebook source
"""Publish governed Databricks Gold marts to Snowflake for BA SQL access.

This job never publishes Bronze payloads or credentials. Facts are merged by
their stable business keys; current-state marts are atomically replaced from a
staged table so removed trends do not linger in analyst queries.
"""

import base64
import re
from datetime import datetime, timezone
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
import snowflake.connector
from snowflake.connector.pandas_tools import write_pandas


IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
ACCOUNT_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,255}")


def text_widget(name, default):
    dbutils.widgets.text(name, default)
    return dbutils.widgets.get(name).strip()


catalog = text_widget("catalog", "dev")
schema = text_widget("schema", "social_intelligence_dev")
snowflake_account = text_widget("snowflake_account", "")
snowflake_user = text_widget("snowflake_user", "SVC_SOCIAL_INTELLIGENCE")
snowflake_database = text_widget("snowflake_database", "SOCIAL_INTELLIGENCE")
snowflake_raw_schema = text_widget("snowflake_raw_schema", "RAW")
snowflake_analytics_schema = text_widget("snowflake_analytics_schema", "ANALYTICS")
snowflake_warehouse = text_widget("snowflake_warehouse", "SOCIAL_INTELLIGENCE_WH")
snowflake_role = text_widget("snowflake_role", "SOCIAL_INTELLIGENCE_PUBLISHER")
secret_scope = text_widget("secret_scope", "social-intelligence")
private_key_secret_key = text_widget(
    "private_key_secret_key", "snowflake-private-key-base64"
)

for identifier in (
    catalog,
    schema,
    snowflake_user,
    snowflake_database,
    snowflake_raw_schema,
    snowflake_analytics_schema,
    snowflake_warehouse,
    snowflake_role,
):
    if not IDENTIFIER_PATTERN.fullmatch(identifier):
        raise ValueError(f"Unsafe identifier: {identifier!r}")
if not ACCOUNT_PATTERN.fullmatch(snowflake_account):
    raise ValueError("snowflake_account must be a Snowflake account identifier")
if not secret_scope or not private_key_secret_key:
    raise ValueError("secret_scope and private_key_secret_key are required")


def quoted(identifier):
    return f'"{identifier}"'


def table_name(schema_name, table):
    return ".".join(
        quoted(value) for value in (snowflake_database, schema_name, table)
    )


def stage_table_name(table, publish_run_id):
    suffix = re.sub(r"[^A-Za-z0-9_]", "_", publish_run_id)[-24:]
    return f"_STAGE_{table}_{suffix}".upper()


private_key_pem = base64.b64decode(
    dbutils.secrets.get(scope=secret_scope, key=private_key_secret_key)
)
private_key = serialization.load_pem_private_key(private_key_pem, password=None)
private_key_der = private_key.private_bytes(
    encoding=serialization.Encoding.DER,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)

publish_run_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid4().hex[:12]}"

# Facts accumulate as new source observations arrive. Snapshot marts represent
# the current state and therefore use a staged atomic replacement.
datasets = (
    ("GOLD_TOPIC_HOURLY", "gold_topic_hourly", ("tenant_id", "hour_ts", "topic"), "merge"),
    ("GOLD_CONTENT_PERFORMANCE", "gold_content_performance", (), "replace"),
    ("GOLD_CREATOR_PERFORMANCE", "gold_creator_performance", (), "replace"),
    ("GOLD_BRAND_DAILY", "gold_brand_daily", ("tenant_id", "metric_date", "brand"), "merge"),
    ("GOLD_TREND_SNAPSHOT", "gold_trend_snapshot", (), "replace"),
    ("GOLD_CHALLENGE_SNAPSHOT", "gold_challenge_snapshot", (), "replace"),
    ("GOLD_EXECUTIVE_KPIS", "gold_executive_kpis", (), "replace"),
    ("GOLD_CONNECTOR_OPERATIONS", "gold_connector_operations", (), "replace"),
    ("GOLD_TRENDING_TOPICS", "gold_trending_topics", (), "replace"),
    ("GOLD_OPPORTUNITIES", "gold_opportunities", (), "replace"),
    ("DECISION_RECOMMENDATIONS", "decision_recommendations", ("recommendation_id",), "merge"),
    ("DECISION_EXPERIMENTS", "decision_experiments", ("experiment_id",), "merge"),
    ("DECISION_LEARNINGS", "decision_learnings", ("learning_id",), "merge"),
    ("GOLD_EXPERIMENT_PERFORMANCE", "gold_experiment_performance", (), "replace"),
    ("GOLD_PILOT_SCORECARD", "gold_pilot_scorecard", (), "replace"),
)


def publish_dataset(connection, target, source, keys, strategy):
    dataframe = spark.table(f"{catalog}.{schema}.{source}")
    row_count = dataframe.count()
    if row_count == 0:
        print(f"Skipped {source}: source table is empty; existing Snowflake mart is retained")
        return 0

    # Gold marts are deliberately small. Keeping the cross-system transfer on
    # the driver makes the implementation compatible with Free Edition while
    # source extraction and intelligence computation remain distributed.
    pandas_frame = dataframe.toPandas()
    stage = stage_table_name(target, publish_run_id)
    success, _, written, _ = write_pandas(
        connection,
        pandas_frame,
        stage,
        database=snowflake_database,
        schema=snowflake_raw_schema,
        auto_create_table=True,
        overwrite=True,
        quote_identifiers=False,
    )
    if not success or written != row_count:
        raise RuntimeError(f"Snowflake stage write failed for {source}: {written}/{row_count}")

    target_fqn = table_name(snowflake_analytics_schema, target)
    stage_fqn = table_name(snowflake_raw_schema, stage)
    with connection.cursor() as cursor:
        if strategy == "replace":
            cursor.execute(f"CREATE OR REPLACE TABLE {target_fqn} CLONE {stage_fqn}")
        else:
            cursor.execute(f"CREATE TABLE IF NOT EXISTS {target_fqn} CLONE {stage_fqn}")
            match_condition = " AND ".join(
                f"target.{quoted(key.upper())} = source.{quoted(key.upper())}"
                for key in keys
            )
            cursor.execute(
                f"""
                MERGE INTO {target_fqn} AS target
                USING {stage_fqn} AS source
                ON {match_condition}
                WHEN MATCHED THEN UPDATE ALL BY NAME
                WHEN NOT MATCHED THEN INSERT ALL BY NAME
                """
            )
        cursor.execute(f"DROP TABLE IF EXISTS {stage_fqn}")
    print(f"Published {source} to {target_fqn}: {row_count} rows ({strategy})")
    return row_count


connection = snowflake.connector.connect(
    account=snowflake_account,
    user=snowflake_user,
    private_key=private_key_der,
    warehouse=snowflake_warehouse,
    database=snowflake_database,
    schema=snowflake_analytics_schema,
    role=snowflake_role,
    application="social_intelligence_databricks",
)

# The account can keep the load warehouse suspended between scheduled runs.
# Select it explicitly after authenticating so Snowflake resumes it before
# write_pandas creates its temporary stage and performs schema inference.
with connection.cursor() as cursor:
    cursor.execute(f"USE WAREHOUSE {quoted(snowflake_warehouse)}")

published_rows = 0
try:
    for target, source, keys, strategy in datasets:
        published_rows += publish_dataset(connection, target, source, keys, strategy)
finally:
    connection.close()

dbutils.notebook.exit(
    f"Snowflake publish completed: run_id={publish_run_id}, rows={published_rows}"
)

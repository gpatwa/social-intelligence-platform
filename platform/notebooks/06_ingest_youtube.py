# Databricks notebook source
"""Collect a quota-bounded YouTube batch and land replayable JSON envelopes."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from social_intelligence.connectors.base import CollectionRule
from social_intelligence.connectors.checkpoint import (
    ConnectorCheckpoint,
    JsonCheckpointStore,
)
from social_intelligence.connectors.youtube import (
    YouTubeConnector,
    YouTubeConnectorConfig,
)


dbutils.widgets.text("catalog", "dev")
dbutils.widgets.text("schema", "social_intelligence_dev")
dbutils.widgets.text("tenant_id", "demo")
dbutils.widgets.text("source_id", "youtube-api-v3")
dbutils.widgets.text("secret_scope", "social-intelligence")
dbutils.widgets.text("secret_key", "youtube-api-key")
dbutils.widgets.text("region_code", "US")
dbutils.widgets.text("relevance_language", "en")
dbutils.widgets.text("lookback_hours", "6")
dbutils.widgets.text("max_search_pages_per_rule", "1")
dbutils.widgets.dropdown("collect_comments", "false", ["false", "true"])
dbutils.widgets.dropdown("collect_replies", "false", ["false", "true"])

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
tenant_id = dbutils.widgets.get("tenant_id")
source_id = dbutils.widgets.get("source_id")
secret_scope = dbutils.widgets.get("secret_scope")
secret_key = dbutils.widgets.get("secret_key")
region_code = dbutils.widgets.get("region_code")
relevance_language = dbutils.widgets.get("relevance_language")
lookback_hours = int(dbutils.widgets.get("lookback_hours"))
max_search_pages_per_rule = int(
    dbutils.widgets.get("max_search_pages_per_rule")
)
collect_comments = dbutils.widgets.get("collect_comments") == "true"
collect_replies = dbutils.widgets.get("collect_replies") == "true"

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
if not re.fullmatch(r"[A-Z]{2}", region_code):
    raise ValueError("region_code must be an ISO 3166-1 alpha-2 code")
if not re.fullmatch(r"[A-Za-z0-9-]{2,16}", relevance_language):
    raise ValueError("relevance_language is invalid")

namespace = f"`{catalog}`.`{schema}`"
rule_rows = spark.sql(
    f"""
    SELECT rule_id, rule_type, expression, enabled
    FROM {namespace}.`control_collection_rules`
    WHERE tenant_id = '{tenant_id}'
      AND source_id = '{source_id}'
      AND enabled
    ORDER BY rule_id
    """
).collect()
if not rule_rows:
    raise ValueError(f"No active collection rules for {tenant_id}/{source_id}")

rules = [
    CollectionRule(
        rule_id=row.rule_id,
        rule_type=row.rule_type,
        expression=row.expression,
        enabled=row.enabled,
    )
    for row in rule_rows
]
api_key = dbutils.secrets.get(scope=secret_scope, key=secret_key)

checkpoint_path = Path(
    f"/Volumes/{catalog}/{schema}/raw_social/checkpoints/"
    f"youtube/{tenant_id}/{source_id}.json"
)
landing_directory = Path(f"/Volumes/{catalog}/{schema}/raw_social/events")
checkpoint_store = JsonCheckpointStore(checkpoint_path)
checkpoint = checkpoint_store.load()


def persist_quota(quota):
    """Commit quota reservations without advancing collection cursors."""
    checkpoint_store.save(
        ConnectorCheckpoint(
            cursors=checkpoint.cursors,
            quota=dict(quota),
            metadata={
                **dict(checkpoint.metadata),
                "quota_reserved_at": datetime.now(timezone.utc).isoformat(),
            },
            updated_at=datetime.now(timezone.utc),
        )
    )


connector = YouTubeConnector(
    api_key=api_key,
    config=YouTubeConnectorConfig(
        tenant_id=tenant_id,
        source_id=source_id,
        region_code=region_code,
        relevance_language=relevance_language,
        lookback_hours=lookback_hours,
        max_search_pages_per_rule=max_search_pages_per_rule,
        collect_comments=collect_comments,
        collect_replies=collect_replies,
    ),
    quota_observer=persist_quota,
)
batch = connector.collect(rules, checkpoint)

# Land events first and commit the cursor second. A failure between these steps
# safely replays the overlap window; downstream idempotency removes duplicates.
if batch.events:
    landing_directory.mkdir(parents=True, exist_ok=True)
    batch_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid4().hex}"
    final_path = landing_directory / f"youtube-{batch_id}.json"
    temporary_path = landing_directory / f".{final_path.name}.tmp"
    try:
        with temporary_path.open("w") as output:
            for event in batch.events:
                output.write(json.dumps(event.to_record(), sort_keys=True) + "\n")
        os.replace(temporary_path, final_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
    print(f"Landed {len(batch.events)} YouTube events at {final_path}")
else:
    print("YouTube collection completed with no new events")

checkpoint_store.save(batch.checkpoint)
print(f"Checkpoint committed at {checkpoint_path}")
print(json.dumps(batch.statistics, sort_keys=True))

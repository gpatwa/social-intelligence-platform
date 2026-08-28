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
for directory in ("events", "checkpoints", "operations"):
    dbutils.fs.mkdirs(
        f"/Volumes/{catalog}/{schema}/raw_social/{directory}"
    )

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
        ('1.0', 'social.engagement.observed', 'BACKWARD', 'SOURCE_SHAPED_JSON', true, CURRENT_TIMESTAMP()),
        ('1.0', 'social.trend.observed', 'BACKWARD', 'SOURCE_SHAPED_JSON', true, CURRENT_TIMESTAMP())
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

# Product and decision records form the commercial control plane. Product maps
# can be maintained by an API or catalog sync; lifecycle tables are append-safe
# and are never replaced by the scheduled analytics rebuild.
spark.sql(
    f"""
    CREATE TABLE IF NOT EXISTS {ns}.`control_product_catalog` (
      tenant_id STRING NOT NULL,
      product_id STRING NOT NULL,
      product_name STRING NOT NULL,
      category STRING,
      gross_margin_rate DOUBLE,
      active BOOLEAN NOT NULL,
      updated_at TIMESTAMP NOT NULL
    )
    USING DELTA
    COMMENT 'Tenant product catalog used to translate social signals into commercial opportunities'
    """
)

spark.sql(
    f"""
    MERGE INTO {ns}.`control_product_catalog` AS target
    USING (
      SELECT * FROM VALUES
        ('{tenant_id}', 'acme-core', 'Acme Core', 'consumer-electronics', 0.60, true, CURRENT_TIMESTAMP())
      AS product(tenant_id, product_id, product_name, category, gross_margin_rate, active, updated_at)
    ) AS incoming
    ON target.tenant_id = incoming.tenant_id AND target.product_id = incoming.product_id
    WHEN MATCHED THEN UPDATE SET
      product_name = incoming.product_name,
      category = incoming.category,
      gross_margin_rate = incoming.gross_margin_rate,
      active = incoming.active,
      updated_at = incoming.updated_at
    WHEN NOT MATCHED THEN INSERT *
    """
)

spark.sql(
    f"""
    CREATE TABLE IF NOT EXISTS {ns}.`control_signal_product_map` (
      tenant_id STRING NOT NULL,
      signal_key STRING NOT NULL,
      product_id STRING NOT NULL,
      product_fit DOUBLE NOT NULL,
      commercial_fit DOUBLE NOT NULL,
      target_audience STRING,
      preferred_channel STRING,
      active BOOLEAN NOT NULL,
      updated_at TIMESTAMP NOT NULL
    )
    USING DELTA
    COMMENT 'Explicit governed mapping from discovered signals to products and activation context'
    """
)

spark.sql(
    f"""
    MERGE INTO {ns}.`control_signal_product_map` AS target
    USING (
      SELECT * FROM VALUES
        ('{tenant_id}', 'battery_issue', 'acme-core', 1.00, 0.70, 'current customers', 'owned-social', true, CURRENT_TIMESTAMP()),
        ('{tenant_id}', 'product_tips', 'acme-core', 0.90, 0.80, 'consideration-stage shoppers', 'paid-social', true, CURRENT_TIMESTAMP()),
        ('{tenant_id}', 'glow_up_challenge', 'acme-core', 0.70, 0.75, 'creator-led lifestyle audiences', 'paid-social', true, CURRENT_TIMESTAMP()),
        ('{tenant_id}', 'glowupchallenge', 'acme-core', 0.70, 0.75, 'creator-led lifestyle audiences', 'paid-social', true, CURRENT_TIMESTAMP())
      AS mapping(tenant_id, signal_key, product_id, product_fit, commercial_fit,
                 target_audience, preferred_channel, active, updated_at)
    ) AS incoming
    ON target.tenant_id = incoming.tenant_id AND target.signal_key = incoming.signal_key
       AND target.product_id = incoming.product_id
    WHEN MATCHED THEN UPDATE SET
      product_fit = incoming.product_fit,
      commercial_fit = incoming.commercial_fit,
      target_audience = incoming.target_audience,
      preferred_channel = incoming.preferred_channel,
      active = incoming.active,
      updated_at = incoming.updated_at
    WHEN NOT MATCHED THEN INSERT *
    """
)

spark.sql(
    f"""
    CREATE TABLE IF NOT EXISTS {ns}.`decision_recommendations` (
      recommendation_id STRING NOT NULL,
      tenant_id STRING NOT NULL,
      opportunity_id STRING NOT NULL,
      product_id STRING,
      action_type STRING NOT NULL,
      channel STRING NOT NULL,
      target_audience STRING,
      hypothesis STRING NOT NULL,
      creative_brief STRING NOT NULL,
      primary_metric STRING NOT NULL,
      confidence_score DOUBLE NOT NULL,
      status STRING NOT NULL,
      evidence_ref STRING NOT NULL,
      created_at TIMESTAMP NOT NULL,
      updated_at TIMESTAMP NOT NULL,
      decided_by STRING,
      decision_reason STRING
    )
    USING DELTA
    COMMENT 'Durable governed recommendation lifecycle; scheduled jobs never erase human decisions'
    """
)

spark.sql(
    f"""
    CREATE TABLE IF NOT EXISTS {ns}.`decision_experiments` (
      experiment_id STRING NOT NULL,
      tenant_id STRING NOT NULL,
      recommendation_id STRING NOT NULL,
      status STRING NOT NULL,
      primary_metric STRING NOT NULL,
      guardrail_metric STRING NOT NULL,
      target_lift_pct DOUBLE,
      control_definition STRING NOT NULL,
      treatment_definition STRING NOT NULL,
      planned_budget DOUBLE NOT NULL,
      actual_spend DOUBLE,
      control_conversions BIGINT,
      treatment_conversions BIGINT,
      control_revenue DOUBLE,
      treatment_revenue DOUBLE,
      start_at TIMESTAMP,
      end_at TIMESTAMP,
      created_at TIMESTAMP NOT NULL,
      updated_at TIMESTAMP NOT NULL
    )
    USING DELTA
    COMMENT 'Controlled commercial experiments created only from approved recommendations'
    """
)

spark.sql(
    f"""
    CREATE TABLE IF NOT EXISTS {ns}.`decision_learnings` (
      learning_id STRING NOT NULL,
      tenant_id STRING NOT NULL,
      experiment_id STRING NOT NULL,
      recommendation_id STRING NOT NULL,
      outcome STRING NOT NULL,
      measured_lift_pct DOUBLE,
      incremental_revenue DOUBLE,
      contribution_margin DOUBLE,
      confidence_level STRING NOT NULL,
      reusable_insight STRING NOT NULL,
      recorded_at TIMESTAMP NOT NULL,
      recorded_by STRING NOT NULL
    )
    USING DELTA
    COMMENT 'Measured experiment outcomes that calibrate future recommendations'
    """
)

# Human reviews and outcome observations are append-only control-plane facts.
# They accept only validated recommendation-review-v1 artifacts through the
# review ingestion boundary; no provider credential or source payload belongs
# here. The scheduled decision build never overwrites either table.
spark.sql(
    f"""
    CREATE TABLE IF NOT EXISTS {ns}.`decision_recommendation_reviews` (
      review_id STRING NOT NULL,
      tenant_id STRING NOT NULL,
      rerank_id STRING NOT NULL,
      context_id STRING NOT NULL,
      decision_id STRING NOT NULL,
      decision STRING NOT NULL,
      status STRING NOT NULL,
      reviewer_id STRING NOT NULL,
      decision_reason STRING NOT NULL,
      reviewer_note STRING,
      selected_candidate_id STRING,
      selected_candidate_rank INT,
      evidence_ids_json STRING NOT NULL,
      edited_brief STRING,
      handoff_state STRING NOT NULL,
      idempotency_key STRING NOT NULL,
      reviewed_at TIMESTAMP NOT NULL,
      received_at TIMESTAMP NOT NULL
    )
    USING DELTA
    COMMENT 'Append-only human decisions over cited offline reranks; manual handoff only'
    """
)

spark.sql(
    f"""
    CREATE TABLE IF NOT EXISTS {ns}.`decision_recommendation_outcomes` (
      outcome_id STRING NOT NULL,
      tenant_id STRING NOT NULL,
      review_id STRING NOT NULL,
      rerank_id STRING NOT NULL,
      context_id STRING NOT NULL,
      decision_id STRING NOT NULL,
      candidate_id STRING NOT NULL,
      metric_name STRING NOT NULL,
      observed_value DOUBLE NOT NULL,
      baseline_value DOUBLE,
      unit STRING NOT NULL,
      measurement_window_days INT NOT NULL,
      measurement_source STRING NOT NULL,
      observed_at TIMESTAMP NOT NULL,
      reported_by STRING NOT NULL,
      idempotency_key STRING NOT NULL,
      confidence STRING NOT NULL,
      attribution STRING NOT NULL,
      received_at TIMESTAMP NOT NULL
    )
    USING DELTA
    COMMENT 'Append-only observational outcome measurements for approved recommendation reviews'
    """
)

print(f"Initialized control plane in {catalog}.{schema} for tenant {tenant_id}")
print(f"Raw event landing root: /Volumes/{catalog}/{schema}/raw_social/events")

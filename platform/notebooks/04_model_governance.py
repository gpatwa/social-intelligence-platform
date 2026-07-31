# Databricks notebook source
"""Create a human-review queue and daily model-quality reporting scaffold."""

import re


dbutils.widgets.text("catalog", "dev")
dbutils.widgets.text("schema", "social_intelligence_dev")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

for identifier in (catalog, schema):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", identifier):
        raise ValueError(f"Unsafe Unity Catalog identifier: {identifier!r}")

ns = f"`{catalog}`.`{schema}`"

# This is intentionally empty until reviewers label content. It separates human
# truth from model predictions and makes future model/prompt evaluation repeatable.
spark.sql(
    f"""
    CREATE TABLE IF NOT EXISTS {ns}.`silver_human_labels` (
      tenant_id STRING,
      platform STRING,
      post_id STRING,
      reviewed_at TIMESTAMP,
      reviewer_id STRING,
      reviewed_topic STRING,
      reviewed_sentiment STRING,
      reviewed_risk_level STRING,
      review_notes STRING
    )
    USING DELTA
    COMMENT 'Human labels used to evaluate topic, sentiment, and risk enrichment'
    """
)

# Preserve any existing reviewer labels while evolving the table to tenant
# scope. The migration is additive and does not replace human-entered data.
label_columns = spark.table(f"{catalog}.{schema}.silver_human_labels").columns
if "tenant_id" not in label_columns:
    spark.sql(f"ALTER TABLE {ns}.`silver_human_labels` ADD COLUMNS (tenant_id STRING)")

spark.sql(
    f"""
    CREATE OR REPLACE TABLE {ns}.`gold_model_review_queue`
    COMMENT 'Prioritized samples for human review; high risk and uncertain cases first'
    AS
    WITH ranked AS (
      SELECT
        tenant_id,
        platform,
        post_id,
        created_at,
        content_text,
        topic AS predicted_topic,
        sentiment_label AS predicted_sentiment,
        risk_level AS predicted_risk_level,
        enrichment_model_version,
        CASE
          WHEN risk_level = 'high' THEN 1
          WHEN sentiment_label = 'negative' THEN 2
          ELSE 3
        END AS review_priority,
        ROW_NUMBER() OVER (
          PARTITION BY tenant_id,
            CASE WHEN risk_level = 'high' THEN 'high' WHEN sentiment_label = 'negative' THEN 'negative' ELSE 'baseline' END
          ORDER BY created_at DESC
        ) AS sample_rank
      FROM {ns}.`silver_social_posts`
    )
    SELECT * EXCEPT (sample_rank)
    FROM ranked
    WHERE sample_rank <= 50
    """
)

spark.sql(
    f"""
    CREATE OR REPLACE TABLE {ns}.`gold_model_quality_daily`
    COMMENT 'Evaluation metrics from human labels; populated as reviews are completed'
    AS
    SELECT
      p.tenant_id,
      CAST(COALESCE(l.reviewed_at, CURRENT_TIMESTAMP()) AS DATE) AS metric_date,
      p.enrichment_model_version,
      COUNT(l.post_id) AS reviewed_posts,
      AVG(CASE WHEN l.reviewed_topic = p.topic THEN 1.0 ELSE 0.0 END) AS topic_accuracy,
      AVG(CASE WHEN l.reviewed_sentiment = p.sentiment_label THEN 1.0 ELSE 0.0 END) AS sentiment_accuracy,
      AVG(CASE WHEN l.reviewed_risk_level = p.risk_level THEN 1.0 ELSE 0.0 END) AS risk_accuracy
    FROM {ns}.`silver_social_posts` p
    LEFT JOIN {ns}.`silver_human_labels` l
      ON p.tenant_id = l.tenant_id AND p.platform = l.platform AND p.post_id = l.post_id
    WHERE l.post_id IS NOT NULL
    GROUP BY p.tenant_id, CAST(COALESCE(l.reviewed_at, CURRENT_TIMESTAMP()) AS DATE), p.enrichment_model_version
    """
)

print(f"Review queue: {spark.table(f'{catalog}.{schema}.gold_model_review_queue').count():,} rows")
print("Quality metrics will populate after human labels are added to silver_human_labels.")

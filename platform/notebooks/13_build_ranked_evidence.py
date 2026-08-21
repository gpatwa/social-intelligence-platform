# Databricks notebook source
"""Materialize explainable, decision-specific evidence rankings for staging."""

import re


dbutils.widgets.text("catalog", "dev")
dbutils.widgets.text("schema", "social_intelligence_dev")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

for identifier in (catalog, schema):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", identifier):
        raise ValueError(f"Unsafe Unity Catalog identifier: {identifier!r}")

ns = f"`{catalog}`.`{schema}`"

# Momentum is normalized inside platform/topic/language/geography cohorts. Raw
# views are never compared directly across platforms. A topic is the v1
# decision context; a future mapping may replace it with an opportunity ID.
spark.sql(
    f"""
    CREATE OR REPLACE TABLE {ns}.`gold_ranked_evidence`
    COMMENT 'Decision-specific source evidence with direct links and explainable cohort-normalized ranking'
    AS
    WITH topic_platforms AS (
      SELECT tenant_id, topic, COUNT(DISTINCT platform) AS platform_count
      FROM {ns}.`silver_social_posts`
      GROUP BY tenant_id, topic
    ), cohort_features AS (
      SELECT
        posts.tenant_id,
        CONCAT('topic:', posts.topic) AS decision_id,
        posts.event_id AS evidence_id,
        posts.platform,
        posts.post_id AS source_object_id,
        COALESCE(
          posts.source_url,
          CASE
            WHEN posts.platform = 'youtube' THEN CONCAT('https://www.youtube.com/watch?v=', posts.post_id)
            WHEN posts.platform = 'x' THEN CONCAT('https://x.com/i/web/status/', posts.post_id)
          END
        ) AS source_url,
        COALESCE(NULLIF(posts.source_title, ''), LEFT(posts.content_text, 240)) AS title,
        COALESCE(NULLIF(posts.source_author, ''), posts.author_id) AS author,
        posts.created_at AS published_at,
        posts.collected_at AS observed_at,
        100.0 AS relevance,
        CASE
          WHEN COUNT(*) OVER cohort > 1
            THEN 100.0 * PERCENT_RANK() OVER (
              PARTITION BY posts.tenant_id, posts.platform, posts.topic, posts.language, COALESCE(posts.geography, 'global')
              ORDER BY posts.engagements, posts.views
            )
          ELSE 50.0
        END AS momentum,
        LEAST(100.0, 40.0 + 600.0 * posts.engagement_rate) AS source_quality,
        LEAST(100.0, 35.0 + 15.0 * (platforms.platform_count - 1)) AS corroboration,
        GREATEST(0.0, 100.0 - 5.0 * DATEDIFF(CURRENT_DATE(), DATE(posts.created_at))) AS freshness,
        CASE WHEN posts.risk_level = 'none' THEN 100.0 ELSE 35.0 END AS safety,
        CASE WHEN posts.risk_level = 'none' THEN 'machine_confirmed' ELSE 'unverified' END AS trust_tier
      FROM {ns}.`silver_social_posts` posts
      INNER JOIN topic_platforms platforms
        ON posts.tenant_id = platforms.tenant_id AND posts.topic = platforms.topic
      WINDOW cohort AS (
        PARTITION BY posts.tenant_id, posts.platform, posts.topic, posts.language, COALESCE(posts.geography, 'global')
      )
    ), scored AS (
      SELECT *, ROUND(LEAST(100.0, GREATEST(0.0,
          0.35 * relevance
        + 0.20 * momentum
        + 0.15 * source_quality
        + 0.15 * corroboration
        + 0.10 * freshness
        + 0.05 * safety
      )), 2) AS evidence_score
      FROM cohort_features
      WHERE source_url IS NOT NULL
    )
    SELECT
      *,
      ROW_NUMBER() OVER (
        PARTITION BY tenant_id, decision_id
        ORDER BY evidence_score DESC, relevance DESC, observed_at DESC, evidence_id
      ) AS evidence_rank,
      'evidence-rank-v1' AS score_version,
      FILTER(ARRAY(
        CASE WHEN relevance >= 70 THEN 'Strong match to the decision' END,
        CASE WHEN momentum >= 70 THEN 'High momentum within its platform cohort' END,
        CASE WHEN source_quality >= 70 THEN 'Strong source-quality signals' END,
        CASE WHEN corroboration >= 70 THEN 'Corroborated by independent evidence' END,
        CASE WHEN freshness >= 70 THEN 'Recently observed' END,
        CASE WHEN safety >= 70 THEN 'Low evidence-integrity risk' END
      ), reason -> reason IS NOT NULL) AS why_ranked,
      CURRENT_TIMESTAMP() AS ranked_at
    FROM scored
    """
)

display(
    spark.sql(
        f"""
        SELECT decision_id, platform, evidence_rank, evidence_score, title, source_url
        FROM {ns}.`gold_ranked_evidence`
        WHERE evidence_rank <= 5
        ORDER BY decision_id, evidence_rank
        """
    )
)

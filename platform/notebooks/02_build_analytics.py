# Databricks notebook source
"""Ingest and transform social data into governed analytics products."""

import re

from pyspark.sql import functions as F
from pyspark.sql import types as T


dbutils.widgets.text("catalog", "main")
dbutils.widgets.text("schema", "social_intelligence_dev")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

for identifier in (catalog, schema):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", identifier):
        raise ValueError(f"Unsafe Unity Catalog identifier: {identifier!r}")

ns = f"`{catalog}`.`{schema}`"
landing_path = f"/Volumes/{catalog}/{schema}/raw_social/events"
checkpoint_path = f"/Volumes/{catalog}/{schema}/raw_social/checkpoints/events"

event_schema = T.StructType(
    [
        T.StructField("event_id", T.StringType()),
        T.StructField("schema_version", T.StringType()),
        T.StructField("tenant_id", T.StringType()),
        T.StructField("source_id", T.StringType()),
        T.StructField("platform", T.StringType()),
        T.StructField("event_type", T.StringType()),
        T.StructField("source_object_id", T.StringType()),
        T.StructField("occurred_at", T.TimestampType()),
        T.StructField("collected_at", T.TimestampType()),
        T.StructField("idempotency_key", T.StringType()),
        T.StructField("correlation_id", T.StringType()),
        T.StructField("payload", T.StringType()),
        T.StructField("attributes", T.MapType(T.StringType(), T.StringType())),
    ]
)

# Available-now Auto Loader gives the MVP incremental file ingestion semantics while
# allowing the workflow task to finish. A production feed can run continuously.
bronze_stream = (
    spark.readStream.format("cloudFiles")
    .option("cloudFiles.format", "json")
    .schema(event_schema)
    .load(landing_path)
)
query = (
    bronze_stream.withColumn("ingested_at", F.current_timestamp())
    .writeStream.option("checkpointLocation", checkpoint_path)
    .option("mergeSchema", "false")
    .trigger(availableNow=True)
    .toTable(f"{catalog}.{schema}.bronze_social_events")
)
query.awaitTermination()

# Invalid or unauthorized events stay queryable for diagnosis without entering
# canonical product tables. A production receiver should also publish failures
# to a dead-letter queue before raw storage.
spark.sql(
    f"""
    CREATE OR REPLACE TABLE {ns}.`bronze_dead_letter_events`
    COMMENT 'Rejected raw events with deterministic validation reasons'
    AS
    SELECT
      events.*,
      CONCAT_WS(',',
        CASE WHEN events.event_id IS NULL THEN 'missing_event_id' END,
        CASE WHEN events.idempotency_key IS NULL THEN 'missing_idempotency_key' END,
        CASE WHEN events.tenant_id IS NULL THEN 'missing_tenant_id' END,
        CASE WHEN events.source_id IS NULL THEN 'missing_source_id' END,
        CASE WHEN events.payload IS NULL THEN 'missing_payload' END,
        CASE WHEN contracts.event_type IS NULL THEN 'unsupported_contract' END,
        CASE WHEN sources.source_id IS NULL THEN 'disabled_or_unregistered_source' END
      ) AS rejection_reasons
    FROM {ns}.`bronze_social_events` events
    LEFT JOIN {ns}.`control_event_contracts` contracts
      ON events.schema_version = contracts.schema_version
     AND events.event_type = contracts.event_type
     AND contracts.active
    LEFT JOIN {ns}.`control_source_registry` sources
      ON events.tenant_id = sources.tenant_id
     AND events.source_id = sources.source_id
     AND sources.enabled
    WHERE events.event_id IS NULL
       OR events.idempotency_key IS NULL
       OR events.tenant_id IS NULL
       OR events.source_id IS NULL
       OR events.payload IS NULL
       OR contracts.event_type IS NULL
       OR sources.source_id IS NULL
    """
)

post_payload_schema = """
  STRUCT<
    post_id: STRING,
    platform: STRING,
    source_url: STRING,
    source_title: STRING,
    source_author: STRING,
    author_id: STRING,
    author_followers: BIGINT,
    content_text: STRING,
    hashtags: ARRAY<STRING>,
    audio_id: STRING,
    created_at: TIMESTAMP,
    collected_at: TIMESTAMP,
    views: BIGINT,
    likes: BIGINT,
    comments: BIGINT,
    shares: BIGINT,
    saves: BIGINT,
    language: STRING,
    geography: STRING,
    brand: STRING,
    source_payload: STRING
  >
"""

trend_payload_schema = """
  STRUCT<
    platform: STRING,
    trend_name: STRING,
    tweet_count: BIGINT,
    woeid: BIGINT,
    location: STRING,
    observed_at: TIMESTAMP,
    source_payload: STRING
  >
"""

# Idempotency is enforced at the mapping boundary. Raw deliveries remain
# immutable, while downstream analytics see one logical event per key.
spark.sql(
    f"""
    CREATE OR REPLACE TABLE {ns}.`bronze_social_posts`
    COMMENT 'Valid post observations mapped from replayable raw event envelopes'
    AS
    WITH accepted AS (
      SELECT
        events.*,
        ROW_NUMBER() OVER (
          PARTITION BY events.tenant_id, events.idempotency_key
          ORDER BY events.collected_at DESC, events.ingested_at DESC, events.event_id DESC
        ) AS delivery_rank
      FROM {ns}.`bronze_social_events` events
      INNER JOIN {ns}.`control_event_contracts` contracts
        ON events.schema_version = contracts.schema_version
       AND events.event_type = contracts.event_type
       AND contracts.active
      INNER JOIN {ns}.`control_source_registry` sources
        ON events.tenant_id = sources.tenant_id
       AND events.source_id = sources.source_id
       AND sources.enabled
      WHERE events.event_type IN ('social.post.observed', 'social.post.updated')
        AND events.event_id IS NOT NULL
        AND events.idempotency_key IS NOT NULL
        AND events.payload IS NOT NULL
    ), parsed AS (
      SELECT *, FROM_JSON(payload, '{post_payload_schema}') AS post
      FROM accepted
      WHERE delivery_rank = 1
    )
    SELECT
      event_id,
      schema_version,
      tenant_id,
      source_id,
      event_type,
      source_object_id,
      idempotency_key,
      correlation_id,
      occurred_at,
      post.*,
      payload AS raw_event_payload,
      attributes AS event_attributes,
      ingested_at
    FROM parsed
    WHERE post.post_id IS NOT NULL
    """
)

spark.sql(
    f"""
    CREATE OR REPLACE TABLE {ns}.`bronze_social_trends`
    COMMENT 'Valid location-scoped trend observations mapped from raw event envelopes'
    AS
    WITH accepted AS (
      SELECT
        events.*,
        ROW_NUMBER() OVER (
          PARTITION BY events.tenant_id, events.idempotency_key
          ORDER BY events.collected_at DESC, events.ingested_at DESC, events.event_id DESC
        ) AS delivery_rank
      FROM {ns}.`bronze_social_events` events
      INNER JOIN {ns}.`control_event_contracts` contracts
        ON events.schema_version = contracts.schema_version
       AND events.event_type = contracts.event_type
       AND contracts.active
      INNER JOIN {ns}.`control_source_registry` sources
        ON events.tenant_id = sources.tenant_id
       AND events.source_id = sources.source_id
       AND sources.enabled
      WHERE events.event_type = 'social.trend.observed'
        AND events.event_id IS NOT NULL
        AND events.idempotency_key IS NOT NULL
        AND events.payload IS NOT NULL
    ), parsed AS (
      SELECT *, FROM_JSON(payload, '{trend_payload_schema}') AS trend
      FROM accepted
      WHERE delivery_rank = 1
    )
    SELECT
      event_id,
      schema_version,
      tenant_id,
      source_id,
      event_type,
      source_object_id,
      idempotency_key,
      correlation_id,
      occurred_at,
      collected_at,
      trend.*,
      CAST(attributes['trend_rank'] AS INT) AS trend_rank,
      payload AS raw_event_payload,
      attributes AS event_attributes,
      ingested_at
    FROM parsed
    WHERE trend.trend_name IS NOT NULL
      AND trend.woeid IS NOT NULL
    """
)

spark.sql(
    f"""
    CREATE OR REPLACE TABLE {ns}.`gold_trending_topics`
    COMMENT 'Latest observed X trends for each configured location'
    AS
    WITH snapshots AS (
      SELECT
        *,
        MAX(observed_at) OVER (
          PARTITION BY tenant_id, source_id, platform, woeid
        ) AS latest_observed_at
      FROM {ns}.`bronze_social_trends`
    )
    SELECT
      tenant_id,
      source_id,
      platform,
      woeid,
      location,
      trend_name,
      tweet_count,
      trend_rank,
      observed_at,
      collected_at,
      source_payload,
      CURRENT_TIMESTAMP() AS refreshed_at
    FROM snapshots
    WHERE observed_at = latest_observed_at
    """
)

spark.sql(
    f"""
    CREATE OR REPLACE TABLE {ns}.`silver_social_posts`
    COMMENT 'Canonical, deduplicated and enriched social post records'
    AS
    WITH deduplicated AS (
      SELECT *, ROW_NUMBER() OVER (
        PARTITION BY tenant_id, platform, post_id
        ORDER BY collected_at DESC, ingested_at DESC
      ) AS row_num
      FROM {ns}.`bronze_social_posts`
      WHERE post_id IS NOT NULL
        AND platform IS NOT NULL
        AND created_at IS NOT NULL
        AND views >= 0
    )
    SELECT
      event_id,
      tenant_id,
      source_id,
      correlation_id,
      post_id,
      platform,
      source_url,
      source_title,
      source_author,
      author_id,
      author_followers,
      content_text,
      hashtags,
      audio_id,
      created_at,
      collected_at,
      views,
      likes,
      comments,
      shares,
      saves,
      likes + comments + shares + saves AS engagements,
      CASE WHEN views > 0 THEN (likes + comments + shares + saves) / views ELSE 0 END AS engagement_rate,
      language,
      geography,
      brand,
      CASE
        WHEN lower(content_text) RLIKE 'overheating|poor charging|problem|issue' THEN 'battery_issue'
        WHEN lower(content_text) LIKE '%glow up%' THEN 'glow_up_challenge'
        WHEN lower(content_text) RLIKE 'tips|tutorial|setup' THEN 'product_tips'
        ELSE 'lifestyle'
      END AS topic,
      CASE
        WHEN lower(content_text) RLIKE 'overheating|poor charging|problem|issue|hate|broken' THEN 'negative'
        WHEN lower(content_text) RLIKE 'inspiration|useful|glow up|love|great' THEN 'positive'
        ELSE 'neutral'
      END AS sentiment_label,
      CASE
        WHEN lower(content_text) RLIKE 'overheating|poor charging' THEN 'high'
        ELSE 'none'
      END AS risk_level,
      'rules-v1' AS enrichment_model_version,
      source_payload,
      raw_event_payload,
      ingested_at
    FROM deduplicated
    WHERE row_num = 1
    """
)

spark.sql(
    f"""
    CREATE OR REPLACE TABLE {ns}.`gold_content_performance`
    COMMENT 'Explainable cross-platform post performance scores; efficiency is weighted above raw reach'
    AS
    SELECT
      tenant_id,
      platform,
      post_id,
      author_id,
      topic,
      sentiment_label,
      created_at,
      views,
      engagements,
      engagement_rate,
      ROUND(LEAST(100.0, GREATEST(0.0,
          50.0 * LEAST(1.0, GREATEST(0.0, engagement_rate / 0.10))
        + 35.0 * LEAST(1.0, LOG1P(engagements) / LOG1P(10000))
        + 15.0 * LEAST(1.0, LOG1P(views) / LOG1P(100000))
      )), 2) AS content_performance_score,
      CASE
        WHEN engagement_rate >= 0.10 THEN 'high'
        WHEN engagement_rate >= 0.03 THEN 'medium'
        ELSE 'baseline'
      END AS efficiency_band
    FROM {ns}.`silver_social_posts`
    """
)

spark.sql(
    f"""
    CREATE OR REPLACE TABLE {ns}.`gold_creator_performance`
    COMMENT 'Creator and account performance by platform; no audience-size ranking is implied'
    AS
    SELECT
      tenant_id,
      platform,
      author_id,
      COUNT(*) AS post_count,
      MAX(created_at) AS latest_post_at,
      SUM(views) AS views,
      SUM(engagements) AS engagements,
      AVG(engagement_rate) AS avg_engagement_rate,
      AVG(content_performance_score) AS avg_content_performance_score,
      AVG(CASE WHEN sentiment_label = 'positive' THEN 1.0 ELSE 0.0 END) AS positive_share,
      COUNT(DISTINCT topic) AS active_topic_count
    FROM {ns}.`gold_content_performance`
    GROUP BY tenant_id, platform, author_id
    """
)

spark.sql(
    f"""
    CREATE OR REPLACE TABLE {ns}.`gold_topic_hourly`
    COMMENT 'Hourly topic performance used for trend detection'
    AS
    SELECT
      tenant_id,
      date_trunc('hour', created_at) AS hour_ts,
      topic,
      COUNT(*) AS post_count,
      COUNT(DISTINCT author_id) AS creator_count,
      COUNT(DISTINCT platform) AS platform_count,
      COUNT(DISTINCT geography) AS geography_count,
      SUM(views) AS views,
      SUM(engagements) AS engagements,
      SUM(shares) AS shares,
      AVG(engagement_rate) AS avg_engagement_rate,
      AVG(CASE WHEN sentiment_label = 'positive' THEN 1.0 ELSE 0.0 END) AS positive_share,
      AVG(CASE WHEN sentiment_label = 'negative' THEN 1.0 ELSE 0.0 END) AS negative_share
    FROM {ns}.`silver_social_posts`
    GROUP BY tenant_id, date_trunc('hour', created_at), topic
    """
)

spark.sql(
    f"""
    CREATE OR REPLACE TABLE {ns}.`gold_trend_hourly`
    COMMENT 'Explainable hourly trend scores and their component signals'
    AS
    WITH history AS (
      SELECT
        *,
        AVG(post_count) OVER topic_history AS baseline_posts,
        STDDEV_SAMP(post_count) OVER topic_history AS baseline_post_stddev,
        AVG(engagements) OVER topic_history AS baseline_engagements,
        STDDEV_SAMP(engagements) OVER topic_history AS baseline_engagement_stddev,
        LAG(post_count) OVER (PARTITION BY tenant_id, topic ORDER BY hour_ts) AS previous_posts,
        MIN(hour_ts) OVER (PARTITION BY tenant_id, topic) AS first_seen_at
      FROM {ns}.`gold_topic_hourly`
      WINDOW topic_history AS (
        PARTITION BY tenant_id, topic ORDER BY hour_ts ROWS BETWEEN 24 PRECEDING AND 1 PRECEDING
      )
    ), components AS (
      SELECT
        *,
        COALESCE((post_count - baseline_posts) / NULLIF(baseline_post_stddev, 0), 0) AS velocity_z,
        COALESCE((engagements - baseline_engagements) / NULLIF(baseline_engagement_stddev, 0), 0) AS engagement_velocity_z,
        COALESCE((post_count - previous_posts) / NULLIF(previous_posts, 0), 0) AS acceleration_pct,
        GREATEST(0.0, 1.0 - (timestampdiff(HOUR, first_seen_at, hour_ts) / 72.0)) AS novelty
      FROM history
    )
    SELECT
      *,
      ROUND(LEAST(100.0, GREATEST(0.0,
          30.0 * LEAST(1.0, GREATEST(0.0, velocity_z / 4.0))
        + 20.0 * LEAST(1.0, GREATEST(0.0, engagement_velocity_z / 4.0))
        + 15.0 * LEAST(1.0, GREATEST(0.0, acceleration_pct / 2.0))
        + 10.0 * LEAST(1.0, LOG1P(creator_count) / LOG1P(100))
        + 10.0 * LEAST(1.0, platform_count / 3.0)
        + 10.0 * LEAST(1.0, novelty)
        + 5.0 * LEAST(1.0, positive_share)
      )), 2) AS trend_score,
      ROUND(LEAST(100.0, GREATEST(0.0,
          50.0 * LEAST(1.0, platform_count / 3.0)
        + 30.0 * LEAST(1.0, LOG1P(creator_count) / LOG1P(100))
        + 20.0 * LEAST(1.0, LOG1P(post_count) / LOG1P(500))
      )), 2) AS cross_platform_confidence
    FROM components
    """
)

spark.sql(
    f"""
    CREATE OR REPLACE TABLE {ns}.`gold_trend_snapshot`
    COMMENT 'Latest available trend state for each topic'
    AS
    SELECT * EXCEPT (recency_rank)
    FROM (
      SELECT *, ROW_NUMBER() OVER (PARTITION BY tenant_id, topic ORDER BY hour_ts DESC) AS recency_rank
      FROM {ns}.`gold_trend_hourly`
    )
    WHERE recency_rank = 1
    """
)

spark.sql(
    f"""
    CREATE OR REPLACE TABLE {ns}.`gold_challenge_hourly`
    COMMENT 'Challenge participation breadth, growth and spread'
    AS
    WITH expanded AS (
      SELECT
        tenant_id,
        date_trunc('hour', created_at) AS hour_ts,
        lower(hashtag) AS challenge_name,
        author_id,
        geography,
        platform
      FROM {ns}.`silver_social_posts`
      LATERAL VIEW explode(hashtags) exploded AS hashtag
      WHERE lower(hashtag) LIKE '%challenge%' OR audio_id IS NOT NULL
    ), hourly AS (
      SELECT
        tenant_id,
        hour_ts,
        challenge_name,
        COUNT(*) AS participation_count,
        COUNT(DISTINCT author_id) AS unique_creators,
        COUNT(DISTINCT geography) AS geography_count,
        COUNT(DISTINCT platform) AS platform_count
      FROM expanded
      GROUP BY tenant_id, hour_ts, challenge_name
    ), growth AS (
      SELECT
        *,
        LAG(participation_count) OVER (PARTITION BY tenant_id, challenge_name ORDER BY hour_ts) AS previous_participation,
        timestampdiff(HOUR, MIN(hour_ts) OVER (PARTITION BY tenant_id, challenge_name), hour_ts) + 1 AS persistence_hours
      FROM hourly
    ), scored AS (
      SELECT
        *,
        COALESCE((participation_count - previous_participation) / NULLIF(previous_participation, 0), 0) AS participant_growth_pct
      FROM growth
    )
    SELECT
      *,
      ROUND(LEAST(100.0, GREATEST(0.0,
          35.0 * LEAST(1.0, GREATEST(0.0, participant_growth_pct / 3.0))
        + 25.0 * LEAST(1.0, LOG1P(unique_creators) / LOG1P(100))
        + 15.0 * LEAST(1.0, geography_count / 5.0)
        + 15.0 * LEAST(1.0, platform_count / 3.0)
        + 10.0 * LEAST(1.0, persistence_hours / 24.0)
      )), 2) AS challenge_score
    FROM scored
    """
)

spark.sql(
    f"""
    CREATE OR REPLACE TABLE {ns}.`gold_challenge_snapshot`
    COMMENT 'Latest available state of every detected challenge'
    AS
    SELECT * EXCEPT (recency_rank)
    FROM (
      SELECT *, ROW_NUMBER() OVER (PARTITION BY tenant_id, challenge_name ORDER BY hour_ts DESC) AS recency_rank
      FROM {ns}.`gold_challenge_hourly`
    )
    WHERE recency_rank = 1
    """
)

spark.sql(
    f"""
    CREATE OR REPLACE TABLE {ns}.`gold_brand_daily`
    COMMENT 'Daily brand health and sentiment metrics'
    AS
    SELECT
      tenant_id,
      CAST(created_at AS DATE) AS metric_date,
      brand,
      COUNT(*) AS mentions,
      COUNT(DISTINCT author_id) AS unique_authors,
      SUM(views) AS views,
      SUM(engagements) AS engagements,
      AVG(engagement_rate) AS avg_engagement_rate,
      AVG(CASE WHEN sentiment_label = 'positive' THEN 1.0 ELSE 0.0 END) AS positive_share,
      AVG(CASE WHEN sentiment_label = 'negative' THEN 1.0 ELSE 0.0 END) AS negative_share,
      AVG(CASE WHEN sentiment_label = 'positive' THEN 1.0 WHEN sentiment_label = 'negative' THEN -1.0 ELSE 0.0 END) AS net_sentiment,
      SUM(CASE WHEN risk_level = 'high' THEN 1 ELSE 0 END) AS high_risk_mentions
    FROM {ns}.`silver_social_posts`
    WHERE brand IS NOT NULL
    GROUP BY tenant_id, CAST(created_at AS DATE), brand
    """
)

spark.sql(
    f"""
    CREATE OR REPLACE TABLE {ns}.`gold_executive_kpis`
    COMMENT 'Current executive-level social intelligence metrics'
    AS
    WITH cutoff AS (
      SELECT tenant_id, MAX(created_at) - INTERVAL 24 HOURS AS start_at
      FROM {ns}.`silver_social_posts`
      GROUP BY tenant_id
    )
    SELECT
      posts.tenant_id,
      MAX(created_at) AS data_through,
      COUNT(*) AS posts_24h,
      COUNT(DISTINCT author_id) AS creators_24h,
      SUM(views) AS views_24h,
      SUM(engagements) AS engagements_24h,
      AVG(engagement_rate) AS avg_engagement_rate_24h,
      AVG(CASE WHEN sentiment_label = 'positive' THEN 1.0 ELSE 0.0 END) AS positive_share_24h,
      AVG(CASE WHEN sentiment_label = 'negative' THEN 1.0 ELSE 0.0 END) AS negative_share_24h,
      SUM(CASE WHEN risk_level = 'high' THEN 1 ELSE 0 END) AS high_risk_mentions_24h,
      COUNT(DISTINCT topic) AS active_topics_24h
    FROM {ns}.`silver_social_posts` posts
    INNER JOIN cutoff ON posts.tenant_id = cutoff.tenant_id
    WHERE created_at >= cutoff.start_at
    GROUP BY posts.tenant_id
    """
)

spark.sql(
    f"""
    CREATE OR REPLACE TABLE {ns}.`gold_source_health`
    COMMENT 'Per-source delivery, rejection, duplication, latency and freshness SLO signals'
    AS
    WITH delivery AS (
      SELECT
        tenant_id,
        source_id,
        COUNT(*) AS delivered_events,
        COUNT(DISTINCT idempotency_key) AS unique_logical_events,
        COUNT(*) - COUNT(DISTINCT idempotency_key) AS duplicate_deliveries,
        MAX(collected_at) AS last_collected_at,
        MAX(ingested_at) AS last_ingested_at,
        PERCENTILE_APPROX(
          GREATEST(0, UNIX_TIMESTAMP(collected_at) - UNIX_TIMESTAMP(occurred_at)),
          0.95
        ) AS collection_latency_p95_seconds
      FROM {ns}.`bronze_social_events`
      GROUP BY tenant_id, source_id
    ), rejected AS (
      SELECT tenant_id, source_id, COUNT(*) AS rejected_events
      FROM {ns}.`bronze_dead_letter_events`
      GROUP BY tenant_id, source_id
    )
    SELECT
      sources.tenant_id,
      sources.source_id,
      sources.platform,
      sources.connector_type,
      sources.collection_mode,
      sources.enabled,
      sources.poll_interval_seconds,
      delivery.last_collected_at,
      delivery.last_ingested_at,
      COALESCE(delivery.delivered_events, 0) AS delivered_events,
      COALESCE(delivery.unique_logical_events, 0) AS unique_logical_events,
      COALESCE(delivery.duplicate_deliveries, 0) AS duplicate_deliveries,
      COALESCE(rejected.rejected_events, 0) AS rejected_events,
      delivery.collection_latency_p95_seconds,
      TIMESTAMPDIFF(MINUTE, delivery.last_collected_at, CURRENT_TIMESTAMP()) AS freshness_minutes,
      CASE
        WHEN NOT sources.enabled THEN 'DISABLED'
        WHEN delivery.last_collected_at IS NULL THEN 'NO_DATA'
        WHEN TIMESTAMPDIFF(SECOND, delivery.last_collected_at, CURRENT_TIMESTAMP())
             > GREATEST(900, COALESCE(sources.poll_interval_seconds, 300) * 3) THEN 'STALE'
        WHEN COALESCE(rejected.rejected_events, 0) > 0 THEN 'DEGRADED'
        ELSE 'HEALTHY'
      END AS health_status,
      CURRENT_TIMESTAMP() AS evaluated_at
    FROM {ns}.`control_source_registry` sources
    LEFT JOIN delivery
      ON sources.tenant_id = delivery.tenant_id AND sources.source_id = delivery.source_id
    LEFT JOIN rejected
      ON sources.tenant_id = rejected.tenant_id AND sources.source_id = rejected.source_id
    """
)

# This unified serving contract is the experience plane's stable read model.
# Dashboards and APIs can add new signal producers without coupling to their
# internal Gold table schemas.
spark.sql(
    f"""
    CREATE OR REPLACE TABLE {ns}.`gold_signal_feed`
    COMMENT 'Unified tenant-scoped serving contract for trends, challenges and brand risks'
    AS
    SELECT
      tenant_id,
      'trend' AS signal_type,
      topic AS signal_key,
      hour_ts AS signal_ts,
      trend_score AS score,
      CASE WHEN trend_score >= 70 THEN 'critical'
           WHEN trend_score >= 45 THEN 'high'
           ELSE 'info' END AS severity,
      CONCAT(
        'Topic ', topic, ' trend score ', CAST(trend_score AS STRING),
        ' with cross-platform confidence ', CAST(cross_platform_confidence AS STRING)
      ) AS summary,
      post_count AS evidence_count,
      'gold_trend_snapshot' AS source_table
    FROM {ns}.`gold_trend_snapshot`

    UNION ALL

    SELECT
      tenant_id,
      'challenge' AS signal_type,
      challenge_name AS signal_key,
      hour_ts AS signal_ts,
      challenge_score AS score,
      CASE WHEN challenge_score >= 70 THEN 'critical'
           WHEN challenge_score >= 45 THEN 'high'
           ELSE 'info' END AS severity,
      CONCAT('Challenge ', challenge_name, ' score ', CAST(challenge_score AS STRING)) AS summary,
      participation_count AS evidence_count,
      'gold_challenge_snapshot' AS source_table
    FROM {ns}.`gold_challenge_snapshot`

    UNION ALL

    SELECT
      tenant_id,
      'brand_risk' AS signal_type,
      brand AS signal_key,
      CAST(metric_date AS TIMESTAMP) AS signal_ts,
      ROUND(LEAST(100.0, negative_share * 60.0 + LEAST(40.0, high_risk_mentions * 2.0)), 2) AS score,
      CASE WHEN high_risk_mentions >= 10 OR negative_share >= 0.5 THEN 'critical'
           WHEN high_risk_mentions > 0 OR negative_share >= 0.25 THEN 'high'
           ELSE 'info' END AS severity,
      CONCAT(brand, ': ', CAST(high_risk_mentions AS STRING), ' high-risk mentions') AS summary,
      mentions AS evidence_count,
      'gold_brand_daily' AS source_table
    FROM {ns}.`gold_brand_daily` brand_daily
    WHERE metric_date = (
      SELECT MAX(latest.metric_date)
      FROM {ns}.`gold_brand_daily` latest
      WHERE latest.tenant_id = brand_daily.tenant_id
    )
    """
)

for table_name in (
    "bronze_social_events",
    "bronze_dead_letter_events",
    "bronze_social_posts",
    "bronze_social_trends",
    "silver_social_posts",
    "gold_content_performance",
    "gold_creator_performance",
    "gold_trending_topics",
    "gold_topic_hourly",
    "gold_trend_hourly",
    "gold_trend_snapshot",
    "gold_challenge_hourly",
    "gold_challenge_snapshot",
    "gold_brand_daily",
    "gold_executive_kpis",
    "gold_source_health",
    "gold_signal_feed",
):
    count = spark.table(f"{catalog}.{schema}.{table_name}").count()
    print(f"{catalog}.{schema}.{table_name}: {count:,} rows")

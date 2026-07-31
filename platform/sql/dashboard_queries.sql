-- Social Intelligence MVP: dashboard datasets and alert queries
-- Replace ${catalog}, ${schema}, and ${tenant_id} with deployed values.
-- Production dashboards must bind tenant_id from authenticated context rather
-- than accepting an unrestricted client-provided value.

-- =============================================================================
-- PAGE 1: EXECUTIVE PULSE
-- =============================================================================
SELECT
  data_through,
  posts_24h,
  creators_24h,
  views_24h,
  engagements_24h,
  avg_engagement_rate_24h,
  positive_share_24h,
  negative_share_24h,
  high_risk_mentions_24h,
  active_topics_24h
FROM ${catalog}.${schema}.gold_executive_kpis
WHERE tenant_id = '${tenant_id}';

-- Platform mix over the latest 24 hours.
WITH cutoff AS (
  SELECT MAX(created_at) - INTERVAL 24 HOURS AS start_at
  FROM ${catalog}.${schema}.silver_social_posts
  WHERE tenant_id = '${tenant_id}'
)
SELECT
  platform,
  COUNT(*) AS posts,
  COUNT(DISTINCT author_id) AS creators,
  SUM(views) AS views,
  SUM(engagements) AS engagements,
  AVG(engagement_rate) AS engagement_rate
FROM ${catalog}.${schema}.silver_social_posts
CROSS JOIN cutoff
WHERE tenant_id = '${tenant_id}' AND created_at >= cutoff.start_at
GROUP BY platform
ORDER BY views DESC;

-- =============================================================================
-- PAGE 2: EMERGING TRENDS
-- =============================================================================
SELECT
  hour_ts,
  topic,
  trend_score,
  post_count,
  creator_count,
  platform_count,
  geography_count,
  velocity_z,
  engagement_velocity_z,
  acceleration_pct,
  positive_share,
  negative_share
FROM ${catalog}.${schema}.gold_trend_snapshot
WHERE tenant_id = '${tenant_id}'
ORDER BY trend_score DESC;

-- Trend lifecycle time series.
SELECT
  hour_ts,
  topic,
  trend_score,
  post_count,
  engagements,
  velocity_z
FROM ${catalog}.${schema}.gold_trend_hourly
WHERE tenant_id = '${tenant_id}'
ORDER BY hour_ts, topic;

-- =============================================================================
-- PAGE 3: CHALLENGES
-- =============================================================================
SELECT
  challenge_name,
  hour_ts,
  challenge_score,
  participation_count,
  participant_growth_pct,
  unique_creators,
  geography_count,
  platform_count,
  persistence_hours
FROM ${catalog}.${schema}.gold_challenge_snapshot
WHERE tenant_id = '${tenant_id}'
ORDER BY challenge_score DESC;

SELECT
  hour_ts,
  challenge_name,
  participation_count,
  unique_creators,
  challenge_score
FROM ${catalog}.${schema}.gold_challenge_hourly
WHERE tenant_id = '${tenant_id}'
ORDER BY hour_ts, challenge_name;

-- =============================================================================
-- PAGE 4: BRAND HEALTH
-- =============================================================================
SELECT
  metric_date,
  brand,
  mentions,
  unique_authors,
  views,
  engagements,
  avg_engagement_rate,
  positive_share,
  negative_share,
  net_sentiment,
  high_risk_mentions
FROM ${catalog}.${schema}.gold_brand_daily
WHERE tenant_id = '${tenant_id}'
ORDER BY metric_date, brand;

-- Top brand issues and representative content.
SELECT
  topic,
  geography,
  platform,
  COUNT(*) AS mentions,
  COUNT(DISTINCT author_id) AS creators,
  SUM(views) AS views,
  MAX_BY(content_text, engagements) AS representative_post
FROM ${catalog}.${schema}.silver_social_posts
WHERE tenant_id = '${tenant_id}' AND brand IS NOT NULL AND sentiment_label = 'negative'
GROUP BY topic, geography, platform
ORDER BY mentions DESC;

-- =============================================================================
-- PAGE 5: DATA OPERATIONS
-- =============================================================================
SELECT
  MAX(created_at) AS newest_post,
  MAX(collected_at) AS newest_collection,
  COUNT(*) AS canonical_rows,
  COUNT(DISTINCT CONCAT(tenant_id, ':', platform, ':', post_id)) AS unique_posts,
  COUNT_IF(content_text IS NULL OR created_at IS NULL OR author_id IS NULL) AS invalid_rows,
  COUNT_IF(engagement_rate < 0 OR engagement_rate > 1) AS suspicious_engagement_rates
FROM ${catalog}.${schema}.silver_social_posts
WHERE tenant_id = '${tenant_id}';

-- Unified experience-plane signal feed.
SELECT signal_type, signal_key, signal_ts, score, severity, summary, evidence_count
FROM ${catalog}.${schema}.gold_signal_feed
WHERE tenant_id = '${tenant_id}'
ORDER BY signal_ts DESC, score DESC;

-- Source SLO and ingestion health.
SELECT source_id, platform, collection_mode, health_status, freshness_minutes,
       delivered_events, duplicate_deliveries, rejected_events,
       collection_latency_p95_seconds, evaluated_at
FROM ${catalog}.${schema}.gold_source_health
WHERE tenant_id = '${tenant_id}'
ORDER BY health_status DESC, source_id;

-- =============================================================================
-- ALERT: emerging trend. Returns rows only when the threshold is breached.
-- =============================================================================
SELECT topic, trend_score, velocity_z, acceleration_pct, hour_ts
FROM ${catalog}.${schema}.gold_trend_snapshot
WHERE tenant_id = '${tenant_id}' AND trend_score >= 70
ORDER BY trend_score DESC;

-- ALERT: brand-risk spike. Tune 0.25 and 10 after observing a real baseline.
SELECT metric_date, brand, negative_share, high_risk_mentions
FROM ${catalog}.${schema}.gold_brand_daily
WHERE tenant_id = '${tenant_id}'
  AND metric_date = (
    SELECT MAX(metric_date)
    FROM ${catalog}.${schema}.gold_brand_daily
    WHERE tenant_id = '${tenant_id}'
  )
  AND negative_share >= 0.25
  AND high_risk_mentions >= 10;

-- ALERT: stale feed. Returns one row when the latest post is over 30 minutes old.
SELECT MAX(created_at) AS newest_post,
       timestampdiff(MINUTE, MAX(created_at), CURRENT_TIMESTAMP()) AS minutes_old
FROM ${catalog}.${schema}.silver_social_posts
WHERE tenant_id = '${tenant_id}'
HAVING minutes_old > 30;

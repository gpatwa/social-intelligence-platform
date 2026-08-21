-- Social Intelligence: Snowflake BA starter queries
-- Databricks is the governed system of record. These curated Gold marts are
-- published to SOCIAL_INTELLIGENCE.ANALYTICS after validation succeeds.

USE ROLE SOCIAL_INTELLIGENCE_BA;
USE WAREHOUSE SOCIAL_INTELLIGENCE_BA_WH;
USE DATABASE SOCIAL_INTELLIGENCE;
USE SCHEMA ANALYTICS;

-- =============================================================================
-- 1. Executive pulse: latest 24-hour social signal
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
FROM gold_executive_kpis
ORDER BY data_through DESC;

-- =============================================================================
-- 2. Emerging trends: highest-scoring current topics
-- =============================================================================
SELECT
  hour_ts,
  topic,
  trend_score,
  post_count,
  creator_count,
  platform_count,
  geography_count,
  views,
  engagements,
  acceleration_pct,
  positive_share,
  negative_share
FROM gold_trend_snapshot
ORDER BY trend_score DESC, engagements DESC;

-- =============================================================================
-- 3. Challenge intelligence: participation, spread, and persistence
-- =============================================================================
SELECT
  hour_ts,
  challenge_name,
  challenge_score,
  participation_count,
  participant_growth_pct,
  unique_creators,
  geography_count,
  platform_count,
  persistence_hours
FROM gold_challenge_snapshot
ORDER BY challenge_score DESC, participation_count DESC;

-- =============================================================================
-- 4. Brand health: daily sentiment and risk summary
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
FROM gold_brand_daily
ORDER BY metric_date DESC, mentions DESC;

-- =============================================================================
-- 5. Topic performance: hourly evidence behind the trend score
-- =============================================================================
SELECT
  hour_ts,
  topic,
  post_count,
  creator_count,
  platform_count,
  views,
  engagements,
  avg_engagement_rate,
  positive_share,
  negative_share
FROM gold_topic_hourly
ORDER BY hour_ts DESC, engagements DESC;

-- =============================================================================
-- 6. Connector operations: data freshness and quota headroom
-- =============================================================================
SELECT
  completed_at,
  source_id,
  platform,
  status,
  operational_status,
  source_objects_discovered,
  events_emitted,
  search_calls_remaining,
  core_units_remaining,
  requests_remaining,
  failed_runs_last_24,
  run_age_minutes
FROM gold_connector_operations
ORDER BY completed_at DESC, source_id;

-- =============================================================================
-- 7. Commercial opportunities: what to act on, why, and for which product
-- =============================================================================
SELECT
  opportunity_id,
  opportunity_type,
  title,
  product_id,
  product_name,
  preferred_channel,
  target_audience,
  opportunity_score,
  confidence_score,
  status,
  evidence_count,
  evidence_ref,
  expires_at
FROM gold_opportunities
ORDER BY opportunity_score DESC, signal_ts DESC;

-- =============================================================================
-- 8. Ranked evidence: direct sources behind each decision context
-- =============================================================================
SELECT
  decision_id,
  evidence_rank,
  evidence_score,
  platform,
  title,
  author,
  source_url,
  trust_tier,
  why_ranked,
  published_at,
  observed_at
FROM gold_ranked_evidence
WHERE evidence_rank <= 5
ORDER BY decision_id, evidence_rank;

-- =============================================================================
-- 9. Recommendation review: proposed, approved, rejected, and activated work
-- =============================================================================
SELECT
  recommendation_id,
  opportunity_id,
  product_id,
  action_type,
  channel,
  hypothesis,
  creative_brief,
  primary_metric,
  confidence_score,
  status,
  decided_by,
  decision_reason,
  updated_at
FROM decision_recommendations
ORDER BY updated_at DESC;

-- =============================================================================
-- 10. Pilot scorecard: adoption, experiment velocity, wins, and contribution
-- =============================================================================
SELECT *
FROM gold_pilot_scorecard
ORDER BY evaluated_at DESC;

SELECT
  experiment_id,
  recommendation_id,
  product_id,
  channel,
  status,
  primary_metric,
  target_lift_pct,
  planned_budget,
  actual_spend,
  outcome,
  measured_lift_pct,
  incremental_revenue,
  contribution_margin,
  confidence_level,
  start_at,
  end_at
FROM gold_experiment_performance
ORDER BY updated_at DESC;

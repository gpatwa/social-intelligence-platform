# Databricks notebook source
"""Run data-quality and product acceptance checks for the generated MVP."""

import re


dbutils.widgets.text("catalog", "main")
dbutils.widgets.text("schema", "social_intelligence_dev")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

for identifier in (catalog, schema):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", identifier):
        raise ValueError(f"Unsafe Unity Catalog identifier: {identifier!r}")

ns = f"`{catalog}`.`{schema}`"
checks = spark.sql(
    f"""
    WITH checks AS (
      SELECT 'registered_sources_are_available' AS check_name,
             COUNT_IF(enabled) > 0 AS passed,
             CONCAT(COUNT_IF(enabled), ' enabled sources') AS detail
      FROM {ns}.`control_source_registry`

      UNION ALL
      SELECT 'raw_events_have_required_envelope',
             COUNT_IF(event_id IS NULL OR tenant_id IS NULL OR source_id IS NULL
                      OR schema_version IS NULL OR idempotency_key IS NULL OR payload IS NULL) = 0,
             CONCAT(COUNT_IF(event_id IS NULL OR tenant_id IS NULL OR source_id IS NULL
                             OR schema_version IS NULL OR idempotency_key IS NULL OR payload IS NULL),
                    ' invalid envelopes')
      FROM {ns}.`bronze_social_events`

      UNION ALL
      SELECT 'dead_letter_queue_is_empty',
             COUNT(*) = 0,
             CONCAT(COUNT(*), ' rejected events')
      FROM {ns}.`bronze_dead_letter_events`

      UNION ALL
      SELECT 'silver_has_rows',
             COUNT(*) > 0 AS passed,
             CONCAT(COUNT(*), ' canonical posts') AS detail
      FROM {ns}.`silver_social_posts`

      UNION ALL
      SELECT 'post_ids_are_unique',
             COUNT(*) = COUNT(DISTINCT CONCAT(tenant_id, ':', platform, ':', post_id)),
             CONCAT(COUNT(*) - COUNT(DISTINCT CONCAT(tenant_id, ':', platform, ':', post_id)), ' duplicate IDs')
      FROM {ns}.`silver_social_posts`

      UNION ALL
      SELECT 'required_fields_are_complete',
             COUNT_IF(post_id IS NULL OR author_id IS NULL OR created_at IS NULL OR topic IS NULL) = 0,
             CONCAT(COUNT_IF(post_id IS NULL OR author_id IS NULL OR created_at IS NULL OR topic IS NULL), ' invalid rows')
      FROM {ns}.`silver_social_posts`

      UNION ALL
      SELECT 'challenge_is_detected',
             COUNT_IF(challenge_name = 'glowupchallenge') > 0,
             CONCAT(COUNT_IF(challenge_name = 'glowupchallenge'), ' matching challenge rows')
      FROM {ns}.`gold_challenge_snapshot`

      UNION ALL
      SELECT 'brand_risk_is_detected',
             SUM(high_risk_mentions) > 0,
             CONCAT(SUM(high_risk_mentions), ' high-risk mentions')
      FROM {ns}.`gold_brand_daily`

      UNION ALL
      SELECT 'trend_scores_are_bounded',
             COUNT_IF(trend_score < 0 OR trend_score > 100 OR trend_score IS NULL) = 0,
             CONCAT(COUNT_IF(trend_score < 0 OR trend_score > 100 OR trend_score IS NULL), ' invalid scores')
      FROM {ns}.`gold_trend_hourly`

      UNION ALL
      SELECT 'model_review_queue_is_available',
             COUNT(*) > 0,
             CONCAT(COUNT(*), ' review candidates')
      FROM {ns}.`gold_model_review_queue`

      UNION ALL
      SELECT 'source_health_is_available',
             COUNT(*) > 0 AND COUNT_IF(health_status IN ('NO_DATA', 'STALE', 'DEGRADED')) = 0,
             CONCAT(COUNT(*), ' sources; ', COUNT_IF(health_status != 'HEALTHY'), ' non-healthy')
      FROM {ns}.`gold_source_health`

      UNION ALL
      SELECT 'experience_signal_feed_is_available',
             COUNT(*) > 0,
             CONCAT(COUNT(*), ' actionable signals')
      FROM {ns}.`gold_signal_feed`

      UNION ALL
      SELECT 'data_is_recent',
             timestampdiff(HOUR, MAX(created_at), CURRENT_TIMESTAMP()) <= 2,
             CONCAT(timestampdiff(MINUTE, MAX(created_at), CURRENT_TIMESTAMP()), ' minutes old')
      FROM {ns}.`silver_social_posts`
    )
    SELECT * FROM checks ORDER BY check_name
    """
)

display(checks)
failed = checks.filter("NOT passed").collect()
if failed:
    summary = "; ".join(f"{row.check_name}: {row.detail}" for row in failed)
    raise RuntimeError(f"MVP validation failed: {summary}")

print("All product acceptance checks passed.")
print(f"Dashboard source: {catalog}.{schema}.gold_executive_kpis")
print(f"Trend source:     {catalog}.{schema}.gold_trend_snapshot")
print(f"Challenge source: {catalog}.{schema}.gold_challenge_snapshot")
print(f"Brand source:     {catalog}.{schema}.gold_brand_daily")

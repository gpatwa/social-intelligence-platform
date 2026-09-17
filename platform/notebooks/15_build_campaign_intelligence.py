# Databricks notebook source
"""Materialize aggregate-only Campaign Intelligence v1 marts.

This job is intentionally unable to activate a campaign, resolve identities,
create an audience, or call an ad API. It exposes transparent observed
treatment/control comparisons and only marks sufficient aggregate results as
eligible inputs to a future offline reranker.
"""

import re


dbutils.widgets.text("catalog", "dev")
dbutils.widgets.text("schema", "social_intelligence_dev")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
for identifier in (catalog, schema):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", identifier):
        raise ValueError(f"Unsafe Unity Catalog identifier: {identifier!r}")

ns = f"`{catalog}`.`{schema}`"

spark.sql(
    f"""
    CREATE OR REPLACE TABLE {ns}.`gold_campaign_intelligence`
    COMMENT 'Aggregate campaign experiments and observed treatment/control lift; no identity or causal attribution'
    AS
    SELECT
      experiments.tenant_id,
      experiments.experiment_id,
      experiments.review_id,
      experiments.context_id,
      experiments.decision_id,
      experiments.candidate_id,
      experiments.campaign_name,
      experiments.channel,
      experiments.business_objective,
      experiments.primary_metric,
      experiments.comparison_method,
      experiments.target_lift_pct,
      experiments.status AS experiment_status,
      experiments.planned_start_at,
      experiments.planned_end_at,
      measurements.measurement_id,
      measurements.control_impressions,
      measurements.control_conversions,
      measurements.treatment_impressions,
      measurements.treatment_conversions,
      measurements.control_value,
      measurements.treatment_value,
      measurements.control_spend,
      measurements.treatment_spend,
      measurements.observed_conversion_rate_lift_pct,
      measurements.result,
      measurements.confidence,
      measurements.feedback_eligible,
      measurements.attribution,
      measurements.measurement_window_days,
      measurements.measurement_source,
      measurements.observed_at,
      CASE WHEN measurements.feedback_eligible
        THEN measurements.observed_conversion_rate_lift_pct END AS offline_reranking_signal_value,
      CASE WHEN measurements.feedback_eligible
        THEN 'observed_campaign_conversion_lift_pct' END AS offline_reranking_signal_metric,
      CURRENT_TIMESTAMP() AS evaluated_at
    FROM {ns}.`decision_campaign_experiments` experiments
    LEFT JOIN {ns}.`decision_campaign_measurements` measurements
      ON experiments.tenant_id = measurements.tenant_id
     AND experiments.experiment_id = measurements.experiment_id
    """
)

spark.sql(
    f"""
    CREATE OR REPLACE TABLE {ns}.`gold_campaign_intelligence_scorecard`
    COMMENT 'Tenant-level Campaign Intelligence adoption and aggregate measurement quality for internal pilot gating'
    AS
    SELECT
      tenant_id,
      COUNT(DISTINCT experiment_id) AS experiments_total,
      COUNT(DISTINCT measurement_id) AS measurements_total,
      COUNT(DISTINCT CASE WHEN result IN ('POSITIVE', 'NEGATIVE', 'INCONCLUSIVE') THEN measurement_id END) AS sufficient_measurements_total,
      COUNT(DISTINCT CASE WHEN feedback_eligible THEN measurement_id END) AS reranking_feedback_total,
      COUNT(DISTINCT CASE WHEN result = 'POSITIVE' THEN measurement_id END) AS positive_results_total,
      AVG(CASE WHEN feedback_eligible THEN observed_conversion_rate_lift_pct END) AS avg_observed_conversion_rate_lift_pct,
      CASE WHEN COUNT(DISTINCT experiment_id) > 0 THEN ROUND(
        COUNT(DISTINCT measurement_id) / COUNT(DISTINCT experiment_id), 4) ELSE 0.0 END AS measurement_coverage_rate,
      'INTERNAL_PILOT' AS stage,
      'DISABLED' AS automation_status,
      CURRENT_TIMESTAMP() AS evaluated_at
    FROM {ns}.`gold_campaign_intelligence`
    GROUP BY tenant_id
    """
)

for table_name in ("gold_campaign_intelligence", "gold_campaign_intelligence_scorecard"):
    print(f"{catalog}.{schema}.{table_name}: {spark.table(f'{catalog}.{schema}.{table_name}').count():,} rows")
